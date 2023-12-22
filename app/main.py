#!/usr/bin/env python3

import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from data import (
    cluster_groups,
    compute_data_point,
    get_cluster_data,
    get_colour_from_name,
    get_neighbourhood_data,
    get_source_info,
)
from model import Dataset, SourceInfo, StatsRequest, StatsResponse, StatsScope, StatsData

description = """Provides statistical data for charting"""

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

# Calling the functions to get data from the spreadsheets has the side effect of caching the data locally
get_neighbourhood_data()
get_cluster_data()

# Serve Javascript in a static mount
app.mount("/static", StaticFiles(directory="/app/static"), name="static")

logger.info("Server setup complete.")


@app.get("/", response_class=HTMLResponse, tags=["Application"])
async def get_chart_application() -> HTMLResponse:
    """The root endpoint returns the content of index.html."""
    with open("static/index.html", "r") as f:
        html = f.read()
    return HTMLResponse(html)


@app.get("/list/neighbourhood", tags=["Lists"])
async def get_neighbourhood_list() -> dict[str, dict[str, set]]:
    """Get a mapping of cluster groups to mappings of clusters to lists of neighbourhoods in the cluster."""
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
    """Clear the neighbourhood data cache and retrieve a new copy from the source spreadsheet.  This call
    will block until the new data have been retrieved."""
    get_neighbourhood_data.cache_clear()
    get_neighbourhood_data()
    get_cluster_data.cache_clear()
    get_cluster_data()


if __name__ == "__main__":
    # This won't run as a script out of the box, it is built to run in the container.  It needs the environment
    # variables and poetry environment to be loaded.  Additionally, certain paths are hardcoded including the
    # path to the static mount defined above, and the path to the service account key specified in data.py.
    # Run `docker compose run --service-ports app bash` and then `python3 main.py` to run as a script in the
    # container, e.g. to use `pdb` debugging.
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
