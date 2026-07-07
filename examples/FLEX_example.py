
import datetime
import time
import webbrowser

from keycloak_oidc_api_client.api.default.generate_user_code import sync as generate_user_code
from keycloak_oidc_api_client.models.user_code_request import UserCodeRequest
from keycloak_oidc_api_client.models.user_code_response import UserCodeResponse
from keycloak_oidc_api_client.models.error import Error
from keycloak_oidc_api_client import Client

from keycloak_oidc_api_client.api.default.request_token import sync as request_token
from keycloak_oidc_api_client.models.request_token import RequestToken
from keycloak_oidc_api_client.models.request_token_response import RequestTokenResponse
import pystac
import requests
import httpx
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

def getUserCode(my_keycloak_base_url, client_id, default_realm):
    
    with Client(base_url=my_keycloak_base_url) as keykoack_client:
        user_code_response: UserCodeResponse | Error | None = generate_user_code(
            realm=default_realm,
            client=keykoack_client,
            body=UserCodeRequest(client_id=client_id, scope="openid profile email"),
        )
    
        if isinstance(user_code_response, UserCodeResponse):
            print("Open this URL in your browser to authorize:")
            print(user_code_response.verification_uri_complete or user_code_response.verification_uri)
            webbrowser.open(user_code_response.verification_uri_complete)
        else:
            print("Error generating user code:", user_code_response)
    return user_code_response

def getToken(my_keycloak_base_url, client_id, default_realm, user_code_response):
    
    request_token_response: RequestTokenResponse | Error | None = None
    
    if not request_token_response and isinstance(user_code_response, UserCodeResponse):
        start_time = time.time()
    
        with Client(base_url=my_keycloak_base_url) as keykoack_client:
            while time.time() - start_time < user_code_response.expires_in:
                request_token_response = request_token(
                    realm=default_realm,
                    client=keykoack_client,
                    body=RequestToken(
                        client_id=client_id,
                        grant_type="urn:ietf:params:oauth:grant-type:device_code",
                        device_code=user_code_response.device_code,
                    ),
                )
    
                if isinstance(request_token_response, RequestTokenResponse):
                    print("Found it!")
                    break
                else:
                    print(f"User hasn't confirmed yet, sleeping for {user_code_response.interval} seconds")
                    time.sleep(user_code_response.interval)
    return request_token_response


def downloadProduct(item, save_dir):
    product_dir = save_dir / item.id
    product_dir.mkdir(exist_ok=True)
    print(f'Downloading product in:', product_dir) 
    
    for asset_name in item.get_assets().keys():
        print(f'  - Downloading asset {asset_name}', end=' ')
        try:
            # Get asset href and filename
            asset_href = item.get_assets()[asset_name].href 
            parsed_url = urlparse(asset_href)
            filename = Path(unquote(parsed_url.path)).name 
    
            save_path = Path(product_dir) / filename
            
            # Download and save
            response = requests.get(asset_href)
            response.raise_for_status()  # Raises HTTPError for bad responses
    
            with open(save_path, 'wb') as f:
                f.write(response.content)
            
            print('--> Done')
        
        except requests.exceptions.HTTPError as http_err:
            if response.status_code == 403:
                print(f"⚠️ Access forbidden (403) when accessing: {asset_href}")
                print(f"--> The access token might have expired, simply re-run the Notebook from the start.")
            else:
                print(f"HTTP error occurred: {http_err}")
        except Exception as err:
            print(f"Unexpected error: {err}") 
   
    print('Product saved successfully')


def getDownloadURL(string, collection_id=None, download_base_url=None):
    """
    Extracts download URL from a product ID or product URL.
    
    Args:
        string (str): Either a product ID (e.g. "S2A_MSIL2A_...")
                      or a product URL 
                      (e.g. "https://discover.flex.pal.maap.eo.esa.int/...").
        collection_id (str, optional): Collection id to use when a product ID
                      is provided. If omitted, the original prefix-based
                      collection mapping is used.
        download_base_url (str, optional): Base download endpoint. If omitted,
                      the original FLEX Collaborative Platform endpoint is used.
    
    Returns:
        url
    """

    if string.startswith("https:") and "items/" in string: 
        # URL provided
        try:
            _, _, col_id, _, item_id = string.rstrip('/').rsplit('/', 4)
        except (ValueError, IndexError):
            raise ValueError(f"URL format not recognized: {string}")

    else:
        # ID provided
        item_id = string
        if collection_id is not None:
            col_id = collection_id
        else:
            if string.startswith('S2'): col_id = 'sentinel-2-l2a-cog'
            elif string.startswith('S3'): col_id = 'sentinel-3-slstr-1-rbt-ntc-cog'
            elif string.startswith('floris'): col_id = 'flex-l2-cog'
            elif string.startswith('FLX'): col_id = 'flex-floris-l1c'
            else:
                raise ValueError(f"Unknown product prefix in ID: {string}")
        
    base_url = (download_base_url or 'https://download.flex.pal.maap.eo.esa.int/flex').rstrip('/')
    url = f'{base_url}/collections/{col_id}/items/{item_id}'
        
    return url


def getProduct(url, headers):
    
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Error - failed with status {response.status_code}: {response.reason}")
        return None
    else:
        print(f" EO Product accessed successfully")
        return pystac.read_dict(response.json())    

def getItem(product_ID):
    if product_ID.startswith("https:"): 
        # URL provided
        item = pystac.read_file(product_ID)
    else: 
        # Item ID provided
        if product_ID.startswith('S2'): item = pystac.read_file(f"https://discover.flex.pal.maap.eo.esa.int/collections/sentinel-2-l2a-cog/items/{product_ID}")
        elif product_ID.startswith('S3'): item = pystac.read_file(f"https://discover.flex.pal.maap.eo.esa.int/collections/sentinel-3-slstr-1-rbt-ntc-cog/items/{product_ID}")
        elif product_ID.startswith('floris'): item = pystac.read_file(f"https://discover.flex.pal.maap.eo.esa.int/collections/flex-l2-cog/items/{product_ID}")
        else: item = pystac.read_file(f"https://discover.flex.pal.maap.eo.esa.int/collections/flex-floris-l1c/items/{product_ID}")
    return item


def downloadSignedItem_FLEX(item, item_dir, url, headers, raise_on_error=False):
    downloaded_paths = []

    for asset_key, asset in item.get_assets().items():
                
        print(f"* {asset_key}")
        
        download_asset_url = f'{url}/assets/{asset_key}'
        # print(f'Asset name "{asset_name}" and download URL (to be signed) {download_asset_url}')
        
        # Sign asset
        r = httpx.get(download_asset_url, headers=headers, timeout=300.0, follow_redirects=False)

        if r.status_code in (302, 303, 307, 308):
            signed_asset_url = r.headers.get("Location") or r.headers.get("location")
            print("  - SIGNED URL:", signed_asset_url)
            
            # Download asset
            r = httpx.get(signed_asset_url, headers=headers, follow_redirects=True)
            r.raise_for_status()
            out_name = item_dir / os.path.basename(signed_asset_url.split('?')[0])

            with open(out_name, "wb") as f:
                f.write(r.content)
            downloaded_paths.append(out_name)
            print("  - Downloaded:", out_name)
        
        else:
            message = f"  - Status: {r.status_code}, Body {r.text}"
            print(message)
            if raise_on_error:
                raise RuntimeError(message)
            continue

    return downloaded_paths

def get_netcdf_asset_href(item):
    """
    Return the href of the best matching NetCDF asset from a STAC item.
    Works even when asset keys differ (data, source_netcdf, product, etc.).
    """
    assets = item.get("assets", {})

    # detect from media type
    for key, asset in assets.items():
        media_type = (
            asset.get("type")
            or asset.get("media_type")
            or ""
        ).lower()

        href = asset.get("href", "")

        if "netcdf" in media_type:
            return href

    # Fallback: detect from file extension
    for key, asset in assets.items():
        href = asset.get("href", "")
        if href.lower().endswith((".nc", ".nc4", ".netcdf")):
            return href

    # Fallback: common known asset names
    for key in ["data", "source_netcdf", "enclosure_nc", "product", "file"]:
        if key in assets:
            return assets[key]["href"]

    # Nothing found
    raise ValueError(
        f"No NetCDF asset found for item {item.get('id', '<unknown>')}. "
        f"Available assets: {list(assets.keys())}"
    )

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