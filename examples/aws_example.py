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

