#!/usr/bin/env python3

from dataclasses import dataclass
import logging
import os

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from data import (
    cluster_groups,
    compute_data_point,
    get_cluster_data,
    get_colour_from_name,
    get_neighbourhood_data,
    get_source_info,
)
from model import Dataset, StatsRequest, StatsResponse, StatsScope, StatsData

description: str = """Provides statistical data for charting"""

logger = logging.getLogger("uvicorn.error")
try:
    logger.setLevel(str(os.environ.get("LOG_LEVEL")))
except ValueError as e:
    logger.setLevel("INFO")
    logger.warning(f"Log level invalid, defaulting to 'INFO'.  Error: {str(e)}")

app = FastAPI(
    title="Stats API",
    version="0.2.0",
    description=description,
)

# Calling the functions to get data from the spreadsheets has the side effect of caching
# the data locally
get_neighbourhood_data()
get_cluster_data()

# Serve Javascript in a static mount
app.mount("/static", StaticFiles(directory="/app/static"), name="static")
# templates = Jinja2Templates(directory="app/static")

logger.info("Server setup complete.")


# Catch-all route for React routing
# @app.get("/{path:path}", response_class=HTMLResponse)
# async def catch_all(request: Request):
#     """
#     This catch-all route serves the index.html file for any route that is not matched by an API
#     endpoint.  It allows the react app to handle the routing.
#     """
#     return templates.TemplateResponse("index.html", {"request": request})


@app.get("/", response_class=HTMLResponse, tags=["Application"])
async def get_chart_application() -> HTMLResponse:
    """The root endpoint returns the content of index.html."""
    with open("static/index.html", "r") as f:
        html = f.read()
    return HTMLResponse(html)


@app.get("/list/neighbourhood", tags=["Lists"])
async def get_neighbourhood_list() -> dict[str, dict[str, set]]:
    """Get a mapping of cluster groups to mappings of clusters to lists of neighbourhoods
    in the cluster."""
    data = get_neighbourhood_data()
    cluster_groups = {}
    for row in data:
        if row[0] not in cluster_groups:
            # add a new cluster group
            cluster_groups[row[0]] = {}
        if row[1] not in cluster_groups[row[0]]:
            # add a new cluster to the group
            cluster_groups[row[0]][row[1]] = set()
        cluster_groups[row[0]][row[1]].add(row[2])
    return cluster_groups


@app.get("/list/cluster", tags=["Lists"])
async def get_cluster_list() -> dict[str, set]:
    """Get a mapping of cluster groups to a list of cluster names."""
    val = {}
    for cluster, group in cluster_groups.items():
        if group not in val:
            val[group] = set()
        val[group].add(cluster)
    return val


@app.post("/stats", tags=["Stats"])
async def request_stats(request: StatsRequest) -> StatsResponse:
    """Return stats and source spreadsheet info for the areas specified in the request object."""
    if request.scope == StatsScope.NEIGHBOURHOOD:
        data = get_neighbourhood_data()
    elif request.scope == StatsScope.CLUSTER:
        data = get_cluster_data()
    else:
        raise HTTPException(status_code=422, detail=f"Invalid scope specified: '{request.scope}'.")
    results = {}
    for row in data:
        name = row[2] if request.scope == StatsScope.NEIGHBOURHOOD else row[1]
        if name not in request.names:
            # ignore areas that weren't requested
            continue
        if name not in results:
            colours = get_colour_from_name(name)
            dataset = Dataset(
                label=name,
                data=[],
                backgroundColor=colours[0],
                borderColor=colours[1],
            )
            results[name] = StatsData(name=name, goal=0, dataset=dataset)
        results[name].dataset.data.append(
            {
                "x": row[3],
                "y": compute_data_point(row, request.activities, request.stats_type),
            }
        )
    return StatsResponse(source=get_source_info(request.scope), data=list(results.values()))


@app.delete("/stats", tags=["Stats"])
async def refresh_neighbourhood_cache():
    """Clear the neighbourhood data cache and retrieve a new copy from the source spreadsheet.
    This call will block until the new data have been retrieved."""
    get_neighbourhood_data.cache_clear()
    get_neighbourhood_data()
    get_cluster_data.cache_clear()
    get_cluster_data()


@dataclass
class LiveSession:
    """Contains a set of configuration parameters and a collection of websockets"""

    conf: int
    area: int
    clients: list[WebSocket]


class LiveSessionManager:
    # mapping of session IDs to objects consisting of current config strings and a list of
    # websockets in the session.
    sessions: dict[str, LiveSession] = {}

    @classmethod
    async def connect(cls, ws: WebSocket) -> str:
        """Wait for the given websocket to be accepted, receive an initialization message, and add
        the websocket to the session indicated in the init message (or create the session if it
        doesn't exist).

        Return: The session ID received."""
        await ws.accept()
        data = await ws.receive_json()
        if "sid" in data:
            if data["sid"] not in cls.sessions:
                cls.sessions[data["sid"]] = LiveSession(data["conf"], data["area"], [ws])
            else:
                cls.sessions[data["sid"]].clients.append(ws)
            await ws.send_json(
                {
                    "conf": cls.sessions[data["sid"]].conf,
                    "area": cls.sessions[data["sid"]].area,
                }
            )
        else:
            logger.error(f"Initial websocket connection didn't receive session ID.  Data: {data}")
        return data["sid"]

    @classmethod
    async def disconnect(cls, sid: str, ws: WebSocket):
        """Remove the given websocket from the session specified in `sid`.

        Args:
            sid (str): Session ID to remove the websocket from.
            ws (WebSocket): The websocket to remove from the session."""
        if sid in cls.sessions:
            num_clients = len(cls.sessions[sid].clients)
            cls.sessions[sid].clients.remove(ws)
            assert len(cls.sessions[sid].clients) < num_clients
        else:
            logger.error("Tried to remove socket from a session it wasn't in.")

    @classmethod
    async def publish(cls, sid: str, conf: int, area: int):
        """Publish updated config values to clients connected to a session.

        Stores the new configuration, and passes them to all the clients registered to the given
        session.

        Args:
            sid (str): The ID of the session to publish to.
            conf (int): The conf parameter.
            area (int): The area parameter"""
        clients = cls.sessions[sid].clients
        cls.sessions[sid] = LiveSession(conf, area, clients)
        for ws in clients:
            await ws.send_json(
                {
                    "conf": cls.sessions[sid].conf,
                    "area": cls.sessions[sid].area,
                    "num_clients": len(clients),
                }
            )


@app.websocket("/live")
async def live(websocket: WebSocket):
    """Open a websocket to a live session.  When a client connected to a given live session makes
    an update to the chart, the change will be reflected on other clients connected to the live
    session.

    Upon connection, the client must join the session by sending a JSON message with the following
    fields:

        {
            "sid": The session ID to join, an arbitrary string.
            "conf": Configuration integer to use when creating the session (ignored if the session
                already exists).
            "area": Area config integer to use when creating the session (ignored if the session
                already exists).
        }

    Once the client has joined the session, it will receive a message with the session's current
    config:

        {
            "conf": Integer representing configuration parameters
            "area": Integer representing which clusters/neighbourhoods are selected
            "num_clients": Number of clients connected to the session
        }

    When a client sends a message with the same schema, all clients in the same session will
    receive the message.  The configuration integers are the bitfields used in the web app,
    e.g. in its cookie.  The "config" integer holds the general configuration (e.g. which activies
    are included) and the "area" integer represents the neighbourhoods or clutsters that are
    included in the chart."""
    sid = await LiveSessionManager.connect(websocket)
    logger.debug("Client connected")
    while True:
        try:
            msg = await websocket.receive_json()
        except WebSocketDisconnect:
            await LiveSessionManager.disconnect(sid, websocket)
            break
        except Exception:
            logger.exception("Unexpected exception in websocket handler.")
            break
        await LiveSessionManager.publish(sid, msg["conf"], msg["area"])


if __name__ == "__main__":
    # This won't run as a script out of the box, it is built to run in the container.  It needs
    # the environment variables and poetry environment to be loaded.  Additionally, certain paths
    # are hardcoded including the path to the static mount defined above, and the path to the
    # service account key specified in data.py.  Run `docker compose run --service-ports app bash`
    # and then `python3 main.py` to run as a script in the container, e.g. to use `pdb` debugging.
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
