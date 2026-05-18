import os
from datetime import datetime as dt
from scrappi.interface import (
    perform_query,
    download_product,
    make_fs,
    list_collections,
)

from scrappi.utils import utils
import matplotlib.pyplot as plt
import pickle
from shapely.geometry import Polygon
from scrappi import ScrappiContext

site_def = {
    "GONA": {
        "latitude_minimum": -23.60472105,
        "longitude_minimum": 15.11465119,
        "latitude_maximum": -23.59568076,
        "longitude_maximum": 15.12446109,
    },
    # "LCFR": [43.55829168, 4.863345627, 43.55948632, 4.86498836],  #same order as dict keys above
    # "RVUS": [38.48687306, -115.7028871, 38.50712799, -115.6771133],
}
example_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "examples", "downloaded_data"
)
file_system = make_fs(example_path)

context = ScrappiContext()
context.set_preferred_api("earthaccess")

if __name__ == "__main__":
    start = "2025-05-01T00:00:00"
    end = "2025-05-05T00:00:00"

    for site in site_def.keys():
        query = {
            "collections": [
                "MOD02HKM",
            ],
            "geom": site_def[site],
            "start_time": start,
            "stop_time": end,
            "version": "7"
        }

        products = perform_query(query, context)
        print(products)
        products.set_fs(file_system)
        path = download_product(products, context)
        print(path)
