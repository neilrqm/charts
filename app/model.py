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


class StatsRequest(BaseModel):
    names: List = Field(description="List of clusters/neighbourhoods to get stats for.")
    scope: StatsScope = Field(description="Request stats for 'Cluster's or 'Neighbourhood's")
    activities: Set[Activity] = Field(description="List of activity types to include in response.")
    stats_type: StatsType = Field(description="Type of statistics to query (number of activities or participants).")
    start_date: dt = Field(description="Query records later than this date.", default=dt.min)


class Dataset(BaseModel):
    label: str = Field(description="Data series label (i.e. the neighbourhood or cluster name).")
    data: List[Dict[str, str | int]] = Field(
        description="List of data points formatted suitably for charting with chart.js, "
        "i.e. [{'x': datestamp, 'y': data_point}, ...]"
    )
    backgroundColor: str = Field(description="String representation of the background colour to use for this dataset.")
    borderColor: str = Field(description="String representation of the border/line colour to use for this dataset.")


class StatsResponse(BaseModel):
    name: str = Field(description="Name of the cluster or neighbourhood.")
    goal: int | None = Field(description="Numerical goal for the requested activity (if available)")
    dataset: Dataset = Field(description="Dataset for the neighbourhood or cluster.")
