"""
scrappi.api.stac_api - STAC API call handler for local logical-HREF STAC catalogs
"""

from pathlib import Path
from typing import Optional, Union, List

import json
import shapely.geometry
import shapely.wkt
import datetime as dt

import pystac

from scrappi.api.base import BaseAPICallHandler
from scrappi.product import ProductItem, ProductItemSet
from scrappi.fs.stacfilesystem import STACFileSystem
from scrappi.fs.stac_href_resolver import StacHrefResolver


class STACAPICallHandler(BaseAPICallHandler):
    """
    STAC API handler for locally stored STAC catalogs using logical HREFs
    (stac://, asset://).
    """

    name = "stac"

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
                    pi = ProductItem.from_stac(item, self.context)
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
