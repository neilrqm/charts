from datetime import datetime as dt
from enum import Enum

from pydantic import BaseModel, Field
from typing import Dict, List, Set


class Activity(str, Enum):
    DG = "dg"
    CC = "cc"
    JY = "jy"
    SC = "sc"


class StatsType(int, Enum):
    NUM_ACTIVITIES = 0
    NUM_PARTICIPANTS = 1


class StatsScope(str, Enum):
    CLUSTER = "Cluster"
    NEIGHBOURHOOD = "Neighbourhood"


class SourceInfo(BaseModel):
    title: str = Field(description="Title of the source spreadsheet.")
    url: str = Field(description="URL of the source spreadsheet.")
    last_pulled: dt = Field(
        description=(
            "Timestamp when data were last pulled from the source, in ISO format (UTC timezone)."
        ),
    )


class Dataset(BaseModel):
    label: str = Field(description="Data series label (i.e. the neighbourhood or cluster name).")
    data: List[Dict[str, str | int]] = Field(
        description="List of data points formatted suitably for charting with chart.js, "
        "i.e. [{'x': datestamp, 'y': data_point}, ...]"
    )
    backgroundColor: str = Field(
        description="String representation of the background colour to use for this dataset."
    )
    borderColor: str = Field(
        description="String representation of the border/line colour to use for this dataset."
    )


class StatsData(BaseModel):
    name: str = Field(description="Name of the cluster or neighbourhood.")
    goal: int | None = Field(description="Numerical goal for the requested activity (if available)")
    dataset: Dataset = Field(description="Dataset for the neighbourhood or cluster.")


class StatsRequest(BaseModel):
    names: List = Field(description="List of clusters/neighbourhoods to get stats for.")
    scope: StatsScope = Field(description="Request stats for 'Cluster's or 'Neighbourhood's")
    activities: Set[Activity] = Field(description="List of activity types to include in response.")
    stats_type: StatsType = Field(
        description="Type of statistics to query (number of activities or participants)."
    )
    start_date: dt = Field(description="Query records later than this date.", default=dt.min)


class StatsResponse(BaseModel):
    source: SourceInfo = Field(description="Object containing some info on the data source.")
    data: list[StatsData] = Field(
        description="List of data objects representing each of the requested areas."
    )
