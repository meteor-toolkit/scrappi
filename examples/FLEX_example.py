from datetime import datetime

import requests
import os
from pathlib import Path
import os
from scrappi.interface import perform_query, download_product, make_fs, list_collections, set_credentials

from scrappi import ScrappiContext

THIS_DIRECTORY = os.path.dirname(__file__)
WORKING_DIR = os.path.join(THIS_DIRECTORY, "downloaded_data")
CP_STAC_ENDPOINT = "https://discover.flex.pal.maap.eo.esa.int/"
FLEX_L2_COLLECTION = "L2A_AtmCorr_DATA"

my_keycloak_base_url = "https://iam.flex.pal.maap.eo.esa.int/"
client_id: str = "discover"
default_realm: str = 'Collaborative-Platform'

start = datetime(2019, 1, 1)
end = datetime(2026, 1, 31, 23, 59, 59)
time_period = f"{start.isoformat()}Z/{end.isoformat()}Z"

example_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples", "downloaded_data")

# file_system = make_fs("t-drive")
file_system = make_fs(example_path)

context = ScrappiContext()

if __name__ == "__main__":
    start = "2020-05-01T00:00:00"
    end = "2026-05-05T00:00:00"

    query = {
        "collections": ["FLEX_L2"],
        "geom": {
            "latitude_minimum": 44.87,
            "longitude_minimum": 11.98,
            "latitude_maximum": 44.88,
            "longitude_maximum": 11.99,
        },
        "start_time": start,
        "stop_time": end,
    }

    products = perform_query(query, context)
    print(products)

    products.set_fs(file_system)
    path = download_product(products, context)
    print(path)








# items = response.json()["features"]

# print("Items found:", len(items))
# for item in items:
#     print(item["id"], "|", item["properties"].get("datetime", "N/A"))

# selected_id = "flx_l2__flxsyn_20250727T085700_20250727T090000_20260410T090707_31TDG_100_036_01"

# # [DON'T EDIT]: Find the item and download
# selected_item = next((item for item in items if item["id"] == selected_id), None)

# if selected_item:
#     print("Selected item:", selected_item["id"])
# else:
#     print("Item ID not found. Check the list above.")

