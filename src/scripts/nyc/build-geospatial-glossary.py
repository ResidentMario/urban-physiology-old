import os
import json
import pysocrata
import numpy as np

from pebble import ProcessPool
from concurrent.futures import TimeoutError
import datafy

DOMAIN = "data.cityofnewyork.us"
FILE_SLUG = "nyc"

# First check to see whether or not a geospatial.json file already exists. We won't recreate the file if it already
# exists. This means that:
# 1. To regenerate the information from scratch, the file must first be deleted.
# 2. Manual edits to the glossary will be preserved (this is a behavior that we want) and considered by the second part
#    of this script.
preexisting = os.path.isfile("../../../data/" + FILE_SLUG + "/glossaries/geospatial.json")


# If not, build out an initial list.
if not preexisting:
    # Obtain NYC open data portal credentials.
    with open("../../../auth/nyc-open-data.json", "r") as f:
        nyc_auth = json.load(f)

    # Use pysocrata to fetch portal metadata.
    nyc_datasets = pysocrata.get_datasets(**nyc_auth)
    nyc_datasets = [d for d in nyc_datasets if d['resource']['type'] != 'story']  # stories excluded manually

    # Get geospatial datasets.
    nyc_types = [d['resource']['type'] for d in nyc_datasets]
    volcab_map = {'dataset': 'table', 'href': 'link', 'map': 'geospatial dataset', 'file': 'blob'}
    nyc_types = list(map(lambda d: volcab_map[d], nyc_types))
    nyc_endpoints = [d['resource']['id'] for d in nyc_datasets]
    geospatial_indices = np.nonzero([t == 'geospatial dataset' for t in nyc_types])
    geospatial_endpoints = np.array(nyc_endpoints)[geospatial_indices]
    geospatial_datasets = np.array(nyc_datasets)[geospatial_indices]

    # Build the data representation.
    datasets = []
    for dataset in geospatial_datasets:
        endpoint = dataset['resource']['id']
        slug = "https://" + DOMAIN + "/api/geospatial/" + endpoint + "?method=export&format=GeoJSON"
        datasets.append(
            {
                'endpoint': endpoint,
                'resource': slug,
                'dataset': '.',
                'type': 'geojson',
                'rows': '?',
                'columns': '?',
                'filesize': '?',
                'flags': ''
             }
        )

    # Write to the file.
    with open("../../../data/" + FILE_SLUG + "/glossaries/geospatial.json", "w") as fp:
        json.dump(datasets, fp, indent=4)

    del datasets


# At this point we know that the file exists. But its contents may not contain the row and column size information that
# we need, because if it was just regenerated by the loop above that stuff will have been populated simply with "?" so
# far.

# Begin by loading in the data that we have.
with open("../../../data/" + FILE_SLUG + "/glossaries/geospatial.json", "r") as fp:
    datasets = json.loads(fp.read())
# datasets = [
#     {
#         "dataset": ".",
#         "rows": "?",
#         "columns": "?",
#         "flags": "",
#         "resource": "https://data.cityofnewyork.us/api/geospatial/u6su-4fpt?method=export&format=GeoJSON",
#         "type": "geojson",
#         "endpoint": "u6su-4fpt",
#         "filesize": 2768
#     },
#     {
#         "dataset": ".",
#         "rows": "?",
#         "columns": "?",
#         "flags": "",
#         "resource": "https://data.cityofnewyork.us/api/geospatial/fw3w-apxs?method=export&format=GeoJSON",
#         "type": "geojson",
#         "endpoint": "fw3w-apxs",
#         "filesize": 1216
#     },
#     {
#         "dataset": ".",
#         "rows": "?",
#         "columns": 2,
#         "flags": "",
#         "resource": "https://data.cityofnewyork.us/api/geospatial/xiyt-f6tz?method=export&format=GeoJSON",
#         "type": "geojson",
#         "endpoint": "xiyt-f6tz",
#         "filesize": 320
#     },
#     {
#         "dataset": ".",
#         "rows": "?",
#         "columns": 2,
#         "flags": "",
#         "resource": "https://data.cityofnewyork.us/api/geospatial/bpt7-i8t8?method=export&format=GeoJSON",
#         "type": "geojson",
#         "endpoint": "bpt7-i8t8",
#         "filesize": 704
#     },
#     {
#         "dataset": ".",
#         "rows": "?",
#         "columns": 2,
#         "flags": "",
#         "resource": "https://data.cityofnewyork.us/api/geospatial/58k2-kgtb?method=export&format=GeoJSON",
#         "type": "geojson",
#         "endpoint": "58k2-kgtb",
#         "filesize": 2928
#     },
#     {
#         "dataset": ".",
#         "rows": "?",
#         "columns": 2,
#         "flags": "",
#         "resource": "https://data.cityofnewyork.us/api/geospatial/7b32-6xny?method=export&format=GeoJSON",
#         "type": "geojson",
#         "endpoint": "7b32-6xny",
#         "filesize": 5248
#     }
# ]


# Build a tuple out of the URI, endpoint, and positional index of each entry.
# We'll use each of these later on, either as input to datify.get or to find where to store what we find.
# Ignore datasets which already have all of their size information defined.
datasets_needing_extraction = [d for d in datasets\
                               if (d['rows'] == "?") or (d['columns'] == "?") or (d['filesize'] == "?")]
indices = [i for i, d in enumerate(datasets)\
           if (d['rows'] == "?") or (d['columns'] == "?") or (d['filesize'] == "?")]
uris = [d['resource'] for d in datasets_needing_extraction]
endpoints = [d['endpoint'] for d in datasets_needing_extraction]
process_tuples = list(zip(uris, endpoints, indices))


# Wrap datafy.get for our purposes.
def get_data(tup):
    # Extract the data from the input tuple (couldn't seem to pass data through the map otherwise?)
    uri, endpoint, i = tup[0], tup[1], tup[2]

    print("Fetching {0}...".format(endpoint))

    # Get the data points.
    ret = datafy.get(uri)
    assert len(ret) == 1  # should be true; otherwise this is a ZIP of some kind.
    data, data_type = ret[0]

    # Fetch the size statistics that we need.
    columns = len(data.columns)
    rows = len(data)
    filesize = int(data.memory_usage().sum())  # must cast to int because json will not serialize np.int64

    # Assign those statistics to the data.
    ep = datasets[i]
    ep['rows'] = rows
    ep['columns'] = columns
    ep['filesize'] = filesize

    print("Done with {0}!".format(endpoint))

    # Return.
    return ep['rows'], ep['columns'], ep['filesize'], i


# pi5s-9p35 is a long-running endpoint, good for testing.
# Whether we succeeded or got caught on a fatal error, in either case save the output to file before exiting.
try:
    # Run our processing jobs asynchronously.
    with ProcessPool(max_workers=4) as pool:
        iterator = pool.map(get_data, process_tuples[3:6], timeout=10)  # cap data downloads at 60 seconds apiece.

        while True:
            try:
                rows, cols, filesize, i = next(iterator)
                datasets[i]['rows'] = rows
                datasets[i]['columns'] = cols
                datasets[i]['filesize'] = filesize
            except TimeoutError as error:
                # Unfortunately the error that gets thrown is a generic TimeoutError, so it's not possible to trace
                # the responsible endpoint inside of the log. You can inspect the output file afterwards to determine
                # this FWIW. It might be possible to add this feature by monkey-patching pebble, but it's probably more
                # effort than it's worth.
                print("Function took longer than %d seconds. Skipping responsible endpoint..." % error.args[1])
                rows, cols, filesize, i = next(iterator)
                datasets[i]['rows'] = rows
                datasets[i]['columns'] = cols
                datasets[i]['filesize'] = filesize
            except StopIteration:
                break
finally:
    import pdb; pdb.set_trace()
    # Whether we succeeded or got caught on a fatal error, in either case save the output to file before exiting.
    with open("../../../data/" + FILE_SLUG + "/glossaries/geospatial.json", "w") as fp:
        json.dump(datasets, fp, indent=4)
