"""FLEX STAC API handler integration for scrappi.

This module provides `FLEXSTACAPICallHandler`, an implementation of
`BaseAPICallHandler` that uses the FLEX Collaborative Platform STAC API to
search for products and download assets after authenticating with Keycloak.
"""

from pathlib import Path
from typing import Union, List

import json
import shapely.geometry
import shapely.wkt

import pystac
import requests
import warnings
import shutil

from scrappi.api.base import BaseAPICallHandler
from scrappi.product import ProductItem, ProductItemSet, product_item_from_stac
from scrappi.fs.stacfilesystem import STACFileSystem
from scrappi.fs.stac_href_resolver import StacHrefResolver
from scrappi.utils.utils import convert_geom_shapely, validate_product_download

from datetime import datetime, timezone
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


COLLECTIONS = {"FLEX_L2": "L2A_AtmCorr_DATA", "FLEX_L1": "FLORIS_L1C_DATA"}


class FLEXSTACAPICallHandler(BaseAPICallHandler):
    """FLEX STAC API call handler.

    Use this handler to search the FLEX STAC catalogue, map collection names to
    their platform identifiers and download signed assets after user
    authentication.

    :param context: scrappi `Context` or equivalent mapping of configuration
    """

    name = "flex_stac"

    def __init__(self, context=None):
        """Initialise the FLEX STAC handler and load the configured endpoints.

        :param context: scrappi `Context` or equivalent mapping of configuration
        """
        super().__init__(context)

        self.cp_stac_endpoint = self.context["flex_stac"]["cp_stac_endpoint"]
        self.search_url = self.cp_stac_endpoint + "search"
        self.keycloak_base_url = self.context["flex_stac"]["keycloak_base_url"]
        self.client_id: str = "discover"
        self.default_realm: str = self.context["flex_stac"]["realm"]
        self.request_token_response = None

    def authenticate(self):
        """Authenticate with the FLEX platform using the Keycloak device flow.

        The first call requests a user code and device login, while subsequent
        calls re-use the stored token for API access.
        """
        if self.request_token_response is None:
            # Get User Code

            user_code_response = self.getUserCode()
            self.request_token_response = self.getToken(user_code_response)
        else: 
            print("Existing token, using it!") 

        # Construct headers
        self.headers = {"Authorization": f"{self.request_token_response.token_type} {self.request_token_response.access_token}"}


    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_collections(self) -> List[str]:
        """List supported FLEX collection names.

        :returns: the collection names exposed by the FLEX STAC API
        """
        return list(COLLECTIONS.keys())

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def _query_stac(self, query: dict) -> ProductItemSet:
        """Return the raw STAC search response for a given query.

        :param query: catalogue query containing optional collection, geometry,
            start and stop time filters
        :returns: response object from the FLEX STAC search endpoint
        """
        if "collection" in query:
            if isinstance(query["collection"], (list, tuple)):
                collections = query["collection"]
            else:
                collections = [query["collection"]]
        else:
            collections = self.list_collections()

        # Map collection names to their actual IDs
        collections = [COLLECTIONS.get(c, c) for c in collections]

        start_time = self._get_datetime(query["start_time"]) if "start_time" in query else None
        stop_time = self._get_datetime(query["stop_time"]) if "stop_time" in query else None
        # produce UTC ISO timestamps with trailing 'Z' (no +00:00)
        if start_time and stop_time:
            s_str = start_time.replace(tzinfo=None).isoformat()
            e_str = stop_time.replace(tzinfo=None).isoformat()
            time_period = f"{s_str}Z/{e_str}Z"
        else:
            time_period = None

        geom_filter = query.get("geom")
        if geom_filter is not None:
            geom_filter = convert_geom_shapely(geom_filter)

        roi = {"type": "Polygon", "coordinates": [list(geom_filter.exterior.coords)]} if geom_filter else None
        
        stac_query = {
            "collections": collections,
            "datetime": time_period,
            "intersects": roi,
            "limit": self.context["flex_stac"]["max_query_results"],
        }
        
        response = requests.post(self.search_url, json=stac_query)
        response.raise_for_status()
        return response
    

    def perform_query(self, query: dict) -> ProductItemSet:
        """Return catalogue products that satisfy a FLEX STAC query.

        :param query: catalogue query with collection, geometry and time filters
        :returns: `ProductItemSet` of matching catalogue products
        """

        self.authenticate()
        response = self._query_stac(query)

        matches = []
        for item in response.json()["features"]:
            item["collection"] = query["collection"]  # Add collection to item for consistency

            # ---- convert to ProductItem ----
            try:
                pi = product_item_from_stac(item, self.context)
                pi.api = self
                matches.append(pi)
            except Exception:
                continue

        return ProductItemSet(matches)

    # ------------------------------------------------------------------
    # Download / resolve product
    # ------------------------------------------------------------------

    def download_product(
        self,
        product: Union[str, ProductItem, ProductItemSet],
    ):
        """Download one or more FLEX products to a local path.

        :param product: `ProductItem` or `ProductItemSet` returned by a search
        :returns: downloaded path or list of paths on the local filesystem
        """

        if isinstance(product, ProductItemSet):
            return [self.download_product(p) for p in product]

        # next perform download based on type of product provided
        if product is None:
            warnings.warn("no product was provided to download")
            return None

        elif isinstance(product, ProductItem):
            path, exists = product.filesystem.return_path(product, check_exists=True)
            product_title = product.id

            if exists:
                print(f"{path} exists")
                valid_download = validate_product_download(Path(path))
                if not valid_download:
                    warnings.warn(
                        f"Existing file {path} is not a valid download. Removing the partial download and redownloading product."
                    )
                    try:
                        if Path(path).is_dir():
                            shutil.rmtree(path)
                        else:
                            Path(path).unlink()
                    except Exception as e:
                        print(f"Error removing invalid download {path}: {e}")
                        raise e
                else:
                    return path

            paths = self.download_flex(product, Path(path))

            if len(paths) == 1:
                return str(paths[0])
            else:
                return [str(p) for p in paths]

        else:
            raise NotImplementedError


    def download_flex(self, product, download_dir):
        """Fetch a FLEX product item and save its signed assets to a directory.

        :param product: product item to download
        :param download_dir: directory in which the product assets are stored
        :returns: list of downloaded file paths
        """
        # Get download URL
        self.authenticate()  # Ensure we have a valid token

        aux_id = product.id
        item_url = f"{self.cp_stac_endpoint}/collections/{COLLECTIONS[product.collection]}/items/{aux_id}"
        aux_item = self.getItem(item_url)
        url = self.getDownloadURL(item_url)
        #print('Download URL:', url, item_url) 

        # Download asset
        
        os.makedirs(download_dir, exist_ok=True)
        return self.downloadSignedItem_FLEX(aux_item, download_dir, url, self.headers)

    def getUserCode(self):
        """Request a Keycloak user code for the device authorisation flow.

        The verification URL is opened in the default browser so the user can
        complete the FLEX sign-in flow.
        """
        with Client(base_url=self.keycloak_base_url) as keykoack_client:
            user_code_response: UserCodeResponse | Error | None = generate_user_code(
                realm=self.default_realm,
                client=keykoack_client,
                body=UserCodeRequest(client_id=self.client_id, scope="openid profile email"),
            )
        
            if isinstance(user_code_response, UserCodeResponse):
                print("Open this URL in your browser to authorize:")
                print(user_code_response.verification_uri_complete or user_code_response.verification_uri)
                webbrowser.open(user_code_response.verification_uri_complete)
            else:
                print("Error generating user code:", user_code_response)
        return user_code_response

    def getToken(self, user_code_response):
        """Poll Keycloak until the user confirms the device login.

        :param user_code_response: Keycloak response containing the device code
            and polling interval
        :returns: token response received from the auth endpoint
        """
        request_token_response: RequestTokenResponse | Error | None = None
        
        if not request_token_response and isinstance(user_code_response, UserCodeResponse):
            start_time = time.time()
        
            with Client(base_url=self.keycloak_base_url) as keykoack_client:
                while time.time() - start_time < user_code_response.expires_in:
                    request_token_response = request_token(
                        realm=self.default_realm,
                        client=keykoack_client,
                        body=RequestToken(
                            client_id=self.client_id,
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


    def downloadProduct(self, item, save_dir):
        """Download all assets for a single FLEX STAC item into a directory.

        :param item: STAC item containing downloadable assets
        :param save_dir: root directory used to save the product payload
        """
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


    def getDownloadURL(self, string, collection_id=None, download_base_url=None):
        """Build the download URL for a FLEX product ID or item URL.

        :param string: product identifier or STAC item URL
        :param collection_id: explicit collection identifier for product IDs
        :param download_base_url: base URL used when constructing the signed
            asset endpoint
        :returns: resolved download URL for the item
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


    def getProduct(self, url, headers):
        """Fetch and parse a single FLEX STAC item from a product URL.

        :param url: URL pointing to a product or item metadata document
        :param headers: HTTP headers used for the request
        :returns: parsed STAC item object, or `None` when the request fails
        """
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"Error - failed with status {response.status_code}: {response.reason}")
            return None
        else:
            print(f" EO Product accessed successfully")
            return pystac.read_dict(response.json())    

    def getItem(self, product_ID):
        """Load a STAC item from either a URL or a FLEX product identifier.

        :param product_ID: product identifier or item URL
        :returns: parsed `pystac.Item` object
        """
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


    def downloadSignedItem_FLEX(self,item, item_dir, url, headers, raise_on_error=False):
        """Download all assets for a FLEX item after resolving signed URLs.

        :param item: STAC item containing downloadable assets
        :param item_dir: local directory used to store downloaded files
        :param url: signed item download base URL
        :param headers: HTTP headers used for authenticated requests
        :param raise_on_error: if `True`, raise on failed asset downloads
        :returns: list of downloaded asset paths
        """
        downloaded_paths = []

        for asset_key, asset in item.get_assets().items():
                    
            print(f"* {asset_key}")
            
            download_asset_url = f'{url}/assets/{asset_key}'
            # print(f'Asset name "{asset_name}" and download URL (to be signed) {download_asset_url}')
            
            # Sign asset
            r = httpx.get(download_asset_url, headers=headers, timeout=300.0, follow_redirects=False)

            if r.status_code in (302, 303, 307, 308):
                signed_asset_url = r.headers.get("Location") or r.headers.get("location")
                print("Starting download  - SIGNED URL:", signed_asset_url)
                
                # Download asset
                r = httpx.get(signed_asset_url, headers=headers, follow_redirects=True)
                r.raise_for_status()
                out_name = item_dir / os.path.basename(signed_asset_url.split('?')[0])

                with open(out_name, "wb") as f:
                    f.write(r.content)
                downloaded_paths.append(out_name)
                print("  - Download completed:", out_name)
            
            else:
                message = f"  - Status: {r.status_code}, Body {r.text}"
                print(message)
                if raise_on_error:
                    raise RuntimeError(message)
                continue

        return downloaded_paths

    def get_netcdf_asset_href(self, item):
        """Return the best matching NetCDF asset href from a STAC item.

        The method searches asset media types first, then file extensions and a
        set of common NetCDF asset names.

        :param item: STAC item dictionary containing asset metadata
        :returns: href of the best NetCDF asset
        :raises ValueError: if no NetCDF asset can be identified
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
