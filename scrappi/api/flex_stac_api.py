"""
scrappi.api.flex_stac_api - FLEX STAC API call handler
"""

from pathlib import Path
from typing import Union, List

import json
import shapely.geometry
import shapely.wkt

import pystac

from scrappi.api.base import BaseAPICallHandler
from scrappi.product import ProductItem, ProductItemSet, product_item_from_stac
from scrappi.fs.stacfilesystem import STACFileSystem
from scrappi.fs.stac_href_resolver import StacHrefResolver

from datetime import datetime
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

class FLEXSTACAPICallHandler(BaseAPICallHandler):
    """
    FLEX STAC API handler 
    """

    name = "flex_stac"

    def __init__(self, context=None):
        super().__init__(context)

        fs_path = self.context["fs"]["path"]
        self.fs = STACFileSystem(path=fs_path, context=self.context)

        self.resolver = StacHrefResolver(
            stac_root=self.fs.stac_root,
            data_root=self.fs.data_root,
        )

        self.stac_root = Path(self.fs.stac_root)
        self.collections_dir = self.stac_root

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_collections(self) -> List[str]:
        if not self.collections_dir.exists():
            return []

        return [p.name for p in self.collections_dir.iterdir() if (p / "collection.json").exists()]

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def perform_query(self, query: dict) -> ProductItemSet:
        """
        Query local logical-HREF STAC catalog.

        Supported keys:
          - collection (str | list[str])
          - geom (WKT / shapely / bbox)
          - start_time
          - stop_time
        """

        # ---- collections to search ----
        if "collection" in query:
            if isinstance(query["collection"], (list, tuple)):
                collections = query["collection"]
            else:
                collections = [query["collection"]]
        else:
            collections = self.list_collections()

        # ---- filters ----
        geom_filter = query.get("geom")
        if geom_filter is not None:
            geom_filter = self._get_geom(geom_filter)

        start_time = self._get_datetime(query["start_time"]) if "start_time" in query else None
        stop_time = self._get_datetime(query["stop_time"]) if "stop_time" in query else None

        asset_state = query.get("asset_state")

        matches: List[ProductItem] = []

        # ------------------------------------------------------------------
        # Iterate collections
        # ------------------------------------------------------------------
        for coll_id in collections:
            coll_json = self.collections_dir / coll_id / "collection.json"
            if not coll_json.exists():
                continue

            collection = pystac.Collection.from_dict(json.loads(coll_json.read_text()))

            # ---- iterate item links only ----
            for link in collection.links:
                if link.rel != "item":
                    continue

                item_href = link.target
                item_path = self.resolver.resolve(item_href)

                if not item_path or not Path(item_path).exists():
                    continue

                item = pystac.Item.from_dict(json.loads(Path(item_path).read_text()))

                # ---- geometry filter ----
                if geom_filter is not None and item.geometry is not None:
                    item_geom = shapely.geometry.shape(item.geometry)
                    if not geom_filter.intersects(item_geom):
                        continue

                # ---- temporal filter ----
                item_start = item.datetime
                item_end = None
                if item.properties:
                    item_end = item.properties.get("end_datetime")
                    if isinstance(item_end, str):
                        item_end = self._get_datetime(item_end)

                if start_time and item_end and item_end < start_time:
                    continue
                if stop_time and item_start and item_start > stop_time:
                    continue

                if asset_state and asset_state != item.assets["data"].extra_fields["scrappi:asset_state"]:
                    continue

                # ---- convert to ProductItem ----
                try:
                    pi = product_item_from_stac(item, self.context)
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
        """
        Resolve asset paths for STAC products.

        For local catalogs, this returns a filesystem path.
        """

        if isinstance(product, ProductItemSet):
            return [self.download_product(p) for p in product]

        if not isinstance(product, ProductItem):
            raise NotImplementedError

        # ---- extract asset href from stored STAC dict ----
        api_prod = product.api_product or product.prod_dict
        if not api_prod:
            return None

        assets = api_prod.get("assets", {})
        if not assets:
            return None

        # Prefer "data" asset
        if "data" in assets:
            href = assets["data"].get("href")
        else:
            href = next(iter(assets.values())).get("href")

        if not href:
            return None

        # ---- HTTP asset ----
        if href.startswith("http://") or href.startswith("https://"):
            return href

        # ---- logical asset ----
        try:
            resolved = self.resolver.resolve(href)
            return str(resolved) if resolved else None
        except Exception:
            return None

    def getUserCode(self, my_keycloak_base_url, client_id, default_realm):
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

    def getToken(self, my_keycloak_base_url, client_id, default_realm, user_code_response):
        
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


    def downloadProduct(self, item, save_dir):
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


    def getProduct(self, url, headers):
        
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"Error - failed with status {response.status_code}: {response.reason}")
            return None
        else:
            print(f" EO Product accessed successfully")
            return pystac.read_dict(response.json())    

    def getItem(self, product_ID):
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

    def get_netcdf_asset_href(self, item):
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
