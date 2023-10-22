#!/usr/bin/env python3

import logging
import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from data import (
    get_neighbourhood_data,
    compute_neighbourhood_data_point,
    get_colour_from_name,
)
from model import StatsRequest, StatsResponse, Dataset

description = """Provides statistical data for charting"""

logger = logging.getLogger("uvicorn.error")
try:
    logger.setLevel(str(os.environ.get("LOG_LEVEL")))
except ValueError as e:
    logger.setLevel("INFO")
    logger.warning(f"Log level invalid, defaulting to 'INFO'.  Error: {str(e)}")

app = FastAPI(
    title="Stats API",
    version="0.1.0",
    description=description,
)

# Serve Javascript in a static mount
app.mount("/static", StaticFiles(directory="/app/static"), name="static")


@app.get("/", response_class=HTMLResponse, tags=["Application"])
async def get_chart_application() -> HTMLResponse:
    """The root endpoint returns the content of index.html."""
    with open("static/index.html", "r") as f:
        html = f.read()
    return HTMLResponse(html)


@app.get("/stats/neighbourhood", tags=["Stats"])
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


@app.post("/stats/neighbourhood", tags=["Stats"])
async def request_neighbourhood_stats(request: StatsRequest) -> list[StatsResponse]:
    """Return stats for the given neighbourhoods."""
    data = get_neighbourhood_data()
    results = {}
    for row in data:
        if row[2] not in request.names:
            # ignore neighbourhoods that weren't requested
            continue
        if row[2] not in results:
            colours = get_colour_from_name(row[2])
            dataset = Dataset(
                label=row[2],
                data=[],
                backgroundColor=colours[0],
                borderColor=colours[1],
            )
            results[row[2]] = StatsResponse(name=row[2], goal=0, dataset=dataset)
        results[row[2]].dataset.data.append(
            {
                "x": row[3],
                "y": compute_neighbourhood_data_point(row, request.activities, request.stats_type),
            }
        )
    return list(results.values())


@app.delete("/stats/neighbourhood", tags=["Stats"])
async def refresh_neighbourhood_cache():
    """Clear the neighbourhood data cache and retrieve a new copy from the source spreadsheet.  This call
    will block until the new data have been retrieved."""
    get_neighbourhood_data.cache_clear()
    get_neighbourhood_data()
