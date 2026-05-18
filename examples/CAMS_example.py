import os
from datetime import datetime as dt
from scrappi.interface import (
    perform_query,
    download_product,
    make_fs,
    list_satellite_products_api,
)
from scrappi import ScrappiContext
import matplotlib.pyplot as plt
import pickle
from shapely.geometry import Polygon
from scrappi import ProductItem

lat, lon = -23.60153, 15.12589  # GHNA location
example_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples")

context = ScrappiContext()
context["fs"]["path"] = example_path
file_system = make_fs(context=context)

if __name__ == "__main__":

    api_name = "eodag"
    start = "2025-01-01T00:00:00"
    end = "2025-03-01T00:00:00"

    print(list_satellite_products_api(guess="CAMS"))

    query = {
        "collections": ["CAMS_EAC4"],
        "geom": [lat - 0.75, lon - 0.75, lat + 0.75, lon + 0.75],
        "start_time": start,
        "stop_time": end,
        "variable": ["total_aerosol_optical_depth_550nm"],
        # "total_aerosol_optical_depth_469nm","total_aerosol_optical_depth_670nm","total_aerosol_optical_depth_865nm","total_aerosol_optical_depth_1240nm","total_column_water_vapour", "total_column_ozone"
        "data_format": "netcdf_zip",
        "time": [
            # '00:00', '03:00',
            "06:00",
            "09:00",
            "12:00",
            "15:00",
            "18:00",  # '21:00',
        ],
    }

    products = perform_query(query, context)

    products.set_fs(file_system)

    path = download_product(products, context)
    print(path)
