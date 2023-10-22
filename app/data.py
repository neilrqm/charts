import logging
import os
import random

from datetime import datetime as dt
from functools import cache
from model import Activity, StatsType

from google.oauth2 import service_account
from googleapiclient.discovery import build


logger = logging.getLogger("uvicorn.error")

cluster_groups = {
    "Abbotsford-Mission": "LM East",
    "Caribou North": "Interior North",
    "Central Interior": "Interior North",
    "Central Okanagan": "Interior South",
    "Chilliwack-Hope": "LM East",
    "Comox Valley": "Island North",
    "Cowichan Valley": "Island North",
    "Golden Ears": "LM East",
    "Langley": "LM East",
    "Mid Island": "Island North",
    "North Shore": "LM West",
    "SE Vic": "Island South",
    "Sooke": "Island South",
    "Strathcona": "Island North",
    "Surrey-Delta-White Rock": "LM East",
    "Tri Cities": "LM East",
    "Vancouver": "LM West",
    "West Shore": "Island South",
}


def _get_data(sheet_id: str, source_tab: str, range: str = "A1:ZZ") -> list[list[str]]:
    """Retrieve data from the source table.

    Args:
        sheet_id (str): The spreadsheet document ID (taken from the URL).
        source_tab (str): The name of the tab containing the source data.
        range (str): The range of data to retrieve.
    Return:
        The data table as a list of rows.
    """
    scopes: list = ["https://www.googleapis.com/auth/spreadsheets"]
    # keyfile on the host, specified in the .env file, is mapped to /sheets-key.json in the container
    creds = service_account.Credentials.from_service_account_file("/sheets-key.json", scopes=scopes)
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()
    return sheet.values().get(spreadsheetId=sheet_id, range=f"'{source_tab}'!{range}").execute()["values"]


def compute_neighbourhood_data_point(row: list, activities: set[Activity], type: StatsType) -> int | None:
    """Compute a data point for a neighbourhood based on a CGP-style table row as returned by
    get_neighbourhood_data.

    Args:
        row (list): a row from the table returned by get_neighbourhood_data.
        activities (set): the activities to sum up into this data point.
        type (StatsType): Indicate whether to sum up numbers of activities or participants.
    Return:
        The sum of activities or participants for the specified activities.  If the sum is 0 then 0 is returned,
        but if there are no data points for the given activities then None is returned.
    """
    cell_values = []
    if Activity.DG in activities:
        cell_values.append(row[4 + type])
    if Activity.CC in activities:
        cell_values.append(row[6 + type])
    if Activity.JY in activities:
        cell_values.append(row[8 + type])
    if Activity.SC in activities:
        cell_values.append(row[10 + type])
    values = [int(x) for x in cell_values if x != ""]
    if len(values) == 0:
        return None
    return sum(values)


@cache
def get_colour_from_name(name: str, offset: int = 0) -> tuple[str, str]:
    """Compute a background colour and a border colour from an arbitrary string.

    The colour is derived randomly using the `name` parameter as a seed.  This means that the colour assigned
    to a given area is random but consistent.  We do this because the default chart.js colour palette is limited.
    Each RGB channel in the bgColour is assigned a random value between 30 and 200; the borderColour is the same
    but with +50 added across all 3 channels---in other words, the effective line colours can range from
    rgb(80, 80, 80) to rgb(250, 250, 250).  An additional offset can be specified, e.g. to generate a line that
    matches a given area's hue but is brighter or darker than the default.  The PRNG is re-seeded with the current
    time after the colour is generated.

    Args:
        name (str): A cluster or neighbourhood name (or any string) used to seed the generation of a colour.
        offset (int): Apply an exra offset to both background and border colours.

    Return:
        A tuple containing string representations of two colours, (bgColour, borderColour).  These are meant
        to configure dataset colours returned to the Chart.js app.  The border colour is the line colour.
        The background colour is the dot/fill colour, and is slightly darker than the border colour.
    """
    # This is a little silly and might need some tweaking to get good colours.  There's also plugins for chart.js
    # that expand its default colour palette---might be worth exploring if this doesn't work out.
    random.seed(name)
    [r, g, b] = [random.randrange(30, 200) + offset for _ in range(0, 3)]
    random.seed()
    return (f"rgb({r}, {g}, {b})", f"rgb({r+50}, {g+50}, {b+50})")


@cache
def get_neighbourhood_data() -> list[list]:
    """Retrieve neighbourhood statistical data from the source spreadsheet and reformat it to look more like
    a cluster growth profile table.  Data rows with no activities are excluded, and empty cells have a value of "".

    Return:
        The reformatted data table.  Table headers look like this:

            Cluster Group, Cluster, Nbhd, Date, nDG, pDG, nCC, pCC, nJY, pJY, nSC, pSC

        (nDG is number of devotionals, pDG is devotional participants, etc.)
    """
    logger.info("Retrieving fresh neighbourhood data.")
    sheet_id = os.environ.get("NBHD_SHEET_ID")
    source_tab = os.environ.get("NBHD_SOURCE_TAB")
    if sheet_id is None or source_tab is None:
        logger.error("NBHD_SHEET_ID and/or NBHD_SOURCE_TAB is empty, both env variables must be set.")
        return []
    data = _get_data(sheet_id, source_tab)
    # pull dates out of the sheet and reformat to ISO format e.g. "Jan     2019" to "2019-01-01"
    dates = {}
    for i in range(0, len(data[2])):
        # build a map from dates to four column numbers for each date
        if data[2][i]:
            tokens = data[2][i].split()
            if len(tokens) != 2:
                # we're done with the main tables at this point
                break
            date = f"1 {tokens[0][0:3]} {tokens[1]}"
            date = dt.strptime(date, "%d %b %Y").isoformat().split("T")[0]
            if date not in dates:
                dates[date] = []
            dates[date].append(i)
    dates = {k: dates[k] for k in dates if len(dates[k]) >= 4}  # remove dates that aren't in the four CA subtables
    new_table = []
    for row in data[4:]:
        if not row[0]:
            # empty cluster name means the end of the data
            break
        for date in dates:
            cluster = row[0].strip()
            nbhd = row[1].strip()
            if cluster not in cluster_groups:
                logger.error(f"Cluster {cluster} is not in the mapping of clusters to cluster groups.")
                group = ""
            else:
                group = cluster_groups[cluster]
            new_row = [group, cluster, nbhd]
            new_row.append(date)
            for i in range(0, 4):
                new_row.append(row[dates[date][i]] if row[dates[date][i]].isdecimal() else "")
                new_row.append(row[dates[date][i] + 1] if row[dates[date][i] + 1].isdecimal() else "")
            if "".join(new_row[4:]):
                # only add the row if there's at least one data point
                new_table.append(new_row)
    return new_table
