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
        "latitude_minimum": 9,
        "longitude_minimum": 10.11465119,
        "latitude_maximum": 12,
        "longitude_maximum": 12,
    },}

example_path = os.path.join(r"C:\Users\wp2\Documents\projects\region_segmentation", "examples", "downloaded_data")
file_system = make_fs(example_path)

context = ScrappiContext()
context.set_preferred_api("aws")

if __name__ == "__main__":
    start = "2025-05-01T00:00:00"
    end = "2025-05-05T00:00:00"
    for site in site_def.keys():
        query = {
            "collections": [
                "ESA_WorldCover",
            ],
            "geom": site_def[site],
            "version": 200,
        }

        products = perform_query(query, context)
        print(products)
        products.set_fs(file_system)
        path = download_product(products, context)
        print(path)
    for site in site_def.keys():
        query = {
            "collections": [
                "Copernicus-dem-30m",
            ],
            "geom": site_def[site],
            #"start_time": start,
            #"stop_time": end,
            #"version": "7",
        }

        products = perform_query(query, context)
        print(products)
        products.set_fs(file_system)
        path = download_product(products, context)
        print(path)

