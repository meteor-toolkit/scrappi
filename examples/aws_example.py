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

example_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples", "downloaded_data")
file_system = make_fs(example_path)

context = ScrappiContext()
context.set_preferred_api("aws")

if __name__ == "__main__":
    for site in site_def.keys():
        world_cover_query = {
            "collections": [
                "ESA_WorldCover",
            ],
            "geom": site_def[site],
            "version": 200,
        }

        world_cover_products = perform_query(world_cover_query, context)
        print(world_cover_products)
        world_cover_products.set_fs(file_system)
        world_cover_path = download_product(world_cover_products, context)
        print(world_cover_path)


        dem_30_query = {
            "collections": [
                "Copernicus-dem-30m",
            ],
            "geom": site_def[site],
        }

        dem_products = perform_query(dem_30_query, context)
        print(dem_products)
        dem_products.set_fs(file_system)
        dem_path = download_product(dem_products, context)
        print(dem_path)

