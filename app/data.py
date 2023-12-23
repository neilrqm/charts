import logging
import os
import random

from datetime import datetime as dt
from datetime import timezone as tz
from functools import cache
from model import Activity, SourceInfo, StatsScope, StatsType

from google.oauth2 import service_account
from googleapiclient.discovery import build


logger = logging.getLogger("uvicorn.error")

cluster_sheet_id = os.environ.get("CLUSTER_SHEET_ID")
nbhd_sheet_id = os.environ.get("NBHD_SHEET_ID")
nbhd_source_tab = os.environ.get("NBHD_SOURCE_TAB")
last_cluster_data_dt = dt.min
last_nbhd_data_dt = dt.min

nbhd_cluster_groups = {
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

cluster_groups = {
    "BC01 - Sooke": "Island South",
    "BC02 - West Shore": "Island South",
    "BC03 - Southeast Victoria": "Island South",
    "BC04 - Saanich Peninsula": "Island South",
    "BC05 - Gulf Islands": "Island South",
    "BC06 - Cowichan Valley": "Island North",
    "BC07 - Mid-Island": "Island North",
    "BC08 - Pacific Rim Oceanside": "Island North",
    "BC10 - Comox Valley": "Island North",
    "BC11 - Strathcona": "Island North",
    "BC12 - North Island": "Island North",
    "BC13 - Vancouver": "LM West",
    "BC15 - North Shore": "LM West",
    "BC16 - Squamish-Pemberton": "LM West",
    "BC17 - Sunshine Coast": "LM West",
    "BC14 - Surrey-Delta-White Rock": "LM East",
    "BC18 - Langley": "LM East",
    "BC19 - Tri-Cities": "LM East",
    "BC20 - Golden Ears": "LM East",
    "BC21 - Abbotsford Mission": "LM East",
    "BC22 - Hope Chilliwack": "LM East",
    "BC23 - South Okanagan": "Interior South",
    "BC24 - Central Okanagan": "Interior South",
    "BC25 - North Okanagan": "Interior South",
    "BC26 - Lower Thompson-Nicola": "Interior South",
    "BC27 - Upper Thompson-Nicola": "Interior South",
    "BC28 - Columbia-Shuswap": "Interior South",
    "BC29 - Upper Columbia": "Interior South",
    "BC30 - East Kootenay": "Interior South",
    "BC31 - West Kootenay": "Interior South",
    "BC32 - Boundary": "Interior South",
    "BC33 - Chilcotin-Cariboo": "Interior North",
    "BC34 - Cariboo North": "Interior North",
    "BC35 - Central Interior": "Interior North",
    "BC36 - Northern Rockies": "Interior North",
    "BC37 - Kitimat Stikine": "Interior North",
    "BC38 - Bulkely Nechako": "Interior North",
    "BC39 - North Coast": "Interior North",
    "BC40 - Central Coast": "Interior North",
    "BC41 - Haida Gwaii": "Interior North",
}

# This object maps tab names in the cluster spreadsheet to column indexes representing the start of the table 2 data.
# For example, the value at index 46 corresponds to column AU in the spreadsheet, which represents the start of
# table 2.  So in that table, data[46] is nDG, data[47] is pDG, data[49] is nCC, data[50] is pCC, ..., where
# nDG is number of devotionals and pDG is participants in devotionals and so on.  In this case data[48] would be
# friends of the Faith participating in devotionals, which we are not using.
cluster_source_tabs = {
    "Oct 2023": 46,  # column AU
    "May 2023": 44,  # column AS
    "Jan 2023": 44,
    "Sep 2022": 44,
    "Apr 2022": 44,
    "Feb 2022": 44,
    "Jan 2022": 44,
    "Oct 2021": 44,
    "Apr 2021": 44,
    "Dec 2020": 44,
    "Aug 2020": 25,  # column Z
    "Apr 2020": 25,
    "Jan 2020": 25,
}


def _get_data(sheet_id: str, source_tab: str, range: str = "A1:ZZ") -> list[list[str]]:
    """Retrieve data from a source spreadsheet.

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


def compute_data_point(row: list, activities: set[Activity], type: StatsType) -> int | None:
    """Compute a data point for an area based on a CGP-style table row as returned by
    get_neighbourhood_data and get_cluster_data.

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
    values = [int(x.replace(",", "")) for x in cell_values if x != ""]
    if len(values) == 0:
        return None
    return sum(values)


@cache
def get_source_info(scope: StatsScope) -> SourceInfo:
    """Get the title, URL, and last update timestamp of the spreadsheet used as a data source for the given scope.

    The cache for this function needs to be cleared any time the source data get updated."""
    global last_cluster_data_dt, last_nbhd_data_dt
    sheet_id = cluster_sheet_id if scope == StatsScope.CLUSTER else nbhd_sheet_id
    scopes: list = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = service_account.Credentials.from_service_account_file("/sheets-key.json", scopes=scopes)
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    title = sheet.get("properties").get("title")
    url = sheet.get("spreadsheetUrl")
    last_pulled_dt = last_cluster_data_dt if scope == StatsScope.CLUSTER else last_nbhd_data_dt
    return SourceInfo(title=title, url=url, last_pulled=last_pulled_dt)


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
def get_cluster_data() -> list[list[str]]:
    """Retrieve cluster statistical data from the source spreadsheet and reformat it to look more like the output
    of `get_neighbourhood_data`.  Data rows with no activities are excluded, and empty cells have a value of "".
    While the spreadsheets indicate dates (presumably corresponding to )

    Return:
        The reformatted data table.  Table headers look like this:

            Cluster Group, Cluster, Nbhd, Date, nDG, pDG, nCC, pCC, nJY, pJY, nSC, pSC

        (nDG is number of devotionals, pDG is devotional participants, etc.  Nbhd is always blank.)
    """
    global last_cluster_data_dt
    logger.info("Retrieving fresh cluster data.")
    last_cluster_data_dt = dt.now(tz=tz.utc)
    get_source_info.cache_clear()
    if cluster_sheet_id is None:
        logger.error("CLUSTER_SHEET_ID is empty, the env variables must be set.")
        return []
    new_rows = []
    for tab_name in cluster_source_tabs:
        tokens = tab_name.split()
        date = f"1 {tokens[0][0:3]} {tokens[1]}"
        date = dt.strptime(date, "%d %b %Y").isoformat().split("T")[0]
        start_column = cluster_source_tabs[tab_name]
        data = _get_data(cluster_sheet_id, tab_name)
        for row in data[3:]:
            if len(row) < start_column or not row[1].startswith("BC"):
                # this row doesn't hold cluster data
                continue
            # some older tables have "R" included in the cluster names to indicate a reservoir cluster--remove it.
            cluster = row[1].replace('"R"', "").strip()
            if cluster not in cluster_groups:
                logger.error(f"Cluster '{cluster}' listed in tab `{tab_name}` was not in the list of known clusters.")
                continue
            cluster_group = cluster_groups[cluster]
            new_row = [cluster_group, cluster, "", date]  # third entry is nbhd, which we ignore in this view.
            for i in range(0, 11, 3):
                # Assumes the source data is structured like table 2 from the CGP.  Each core activity has three
                # columns, starting at `start_column` which is specified on a tab-by-tab basis above.  For each core
                # activity, we extract the first two of its columns (number of the activity and number of participants)
                # into the new row.
                new_row.append(row[start_column + i])
                new_row.append(row[start_column + i + 1])
            if "".join(new_row[4:]):
                # only add the row if there's at least one data point
                new_rows.append(new_row)
    return new_rows


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
    global last_nbhd_data_dt
    last_nbhd_data_dt = dt.now(tz=tz.utc)
    get_source_info.cache_clear()
    if nbhd_sheet_id is None or nbhd_source_tab is None:
        logger.error("NBHD_SHEET_ID and/or NBHD_SOURCE_TAB is empty, both env variables must be set.")
        return []
    data = _get_data(nbhd_sheet_id, nbhd_source_tab)

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
            if cluster not in nbhd_cluster_groups:
                logger.error(f"Cluster {cluster} is not in the mapping of clusters to cluster groups.")
                group = ""
            else:
                group = nbhd_cluster_groups[cluster]
            new_row = [group, cluster, nbhd]
            new_row.append(date)
            for i in range(0, 4):
                new_row.append(row[dates[date][i]] if row[dates[date][i]].isdecimal() else "")
                new_row.append(row[dates[date][i] + 1] if row[dates[date][i] + 1].isdecimal() else "")
            if "".join(new_row[4:]):
                # only add the row if there's at least one data point
                new_table.append(new_row)
    return new_table
