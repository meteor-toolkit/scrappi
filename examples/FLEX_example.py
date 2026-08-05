from datetime import datetime

import requests
import os
from pathlib import Path
from urllib.parse import urlparse, unquote

THIS_DIRECTORY = os.path.dirname(__file__)
WORKING_DIR = os.path.join(THIS_DIRECTORY, "downloaded_data")
CP_STAC_ENDPOINT = "https://discover.flex.pal.maap.eo.esa.int/"
FLEX_L2_COLLECTION = "L2A_AtmCorr_DATA"

start = datetime(2019, 1, 1)
end = datetime(2026, 1, 31, 23, 59, 59)
time_period = f"{start.isoformat()}Z/{end.isoformat()}Z"
center_latlon = [44.87, 11.98]



# get token to retrieve data from the CP catalogue
request_token_response = None

my_keycloak_base_url = "https://iam.flex.pal.maap.eo.esa.int/"
client_id: str = "discover"
default_realm: str = 'Collaborative-Platform'

# Get User Code
user_code_response = getUserCode(my_keycloak_base_url, client_id, default_realm)

if request_token_response is None:
    request_token_response = getToken(my_keycloak_base_url, client_id, default_realm, user_code_response)
else: 
    print("Existing token, using it!") 

# Construct headers
headers = {"Authorization": f"{request_token_response.token_type} {request_token_response.access_token}"}

search_url = CP_STAC_ENDPOINT + "search"

query = {
    "collections": [FLEX_L2_COLLECTION],
    "datetime": time_period,
    "intersects": {
        "type": "Point",
        "coordinates": center_latlon[::-1]
    },
    "limit": 50
}

response = requests.post(search_url, json=query)
response.raise_for_status()

items = response.json()["features"]

print("Items found:", len(items))
for item in items:
    print(item["id"], "|", item["properties"].get("datetime", "N/A"))

selected_id = "flx_l2__flxsyn_20250727T085700_20250727T090000_20260410T090707_31TDG_100_036_01"

# [DON'T EDIT]: Find the item and download
selected_item = next((item for item in items if item["id"] == selected_id), None)

if selected_item:
    print("Selected item:", selected_item["id"])
else:
    print("Item ID not found. Check the list above.")

# Get download URL
aux_id = selected_item["id"]
item_url = f"{CP_STAC_ENDPOINT}/collections/{FLEX_L2_COLLECTION}/items/{aux_id}"
aux_item = getItem(item_url)
url = getDownloadURL(item_url)
print('Download URL:', url, item_url) 

# Download asset
print("Downloading asset:")
download_dir = Path(WORKING_DIR) / "pairing"
os.makedirs(download_dir, exist_ok=True)
downloadSignedItem_FLEX(aux_item, download_dir, url, headers)

flex_s3_filename = get_netcdf_asset_href(item)
FLEX_FILE = download_dir / Path(flex_s3_filename).name