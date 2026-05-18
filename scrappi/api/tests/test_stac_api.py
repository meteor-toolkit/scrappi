import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from shapely.geometry import box

from scrappi.api.stac_api import STACAPICallHandler
from scrappi.product import ProductItem
from scrappi import ScrappiContext


class TestSTACAPICallHandler(unittest.TestCase):

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.base = Path(self.tmp.name)

        # filesystem layout
        self.stac_root = self.base / "stac"
        self.data_root = self.base / "data"
        self.stac_root.mkdir()
        self.data_root.mkdir()

        # context
        self.context = ScrappiContext()
        self.context["fs"]["path"] = str(self.base)

        # ---------------------------
        # Collection
        # ---------------------------
        coll_dir = self.stac_root / "LHYP_L2B_REF"
        coll_dir.mkdir(parents=True)

        collection = {
            "type": "Collection",
            "stac_version": "1.1.0",
            "id": "LHYP_L2B_REF",
            "description": "Collection LHYP_L2B_REF",
            "license": "other",
            "extent": {
                "spatial": {
                    "bbox": [[15.1250808, -23.6025008, 15.1266992, -23.6005592]]
                },
                "temporal": {
                    "interval": [["2025-11-01T10:33:35Z", "2025-11-01T14:39:51Z"]]
                },
            },
            "links": [
                {
                    "rel": "self",
                    "href": "stac://LHYP_L2B_REF/collection.json",
                    "type": "application/json",
                },
                {
                    "rel": "item",
                    "href": "stac://items/2025/11/01/item1.json",
                    "type": "application/geo+json",
                },
            ],
        }

        (coll_dir / "collection.json").write_text(json.dumps(collection, indent=2))

        # ---------------------------
        # Data file
        # ---------------------------
        data_file = self.data_root / "data" / "LHYP_L2B_REF" / "foo.nc"
        data_file.parent.mkdir(parents=True)
        data_file.write_text("dummy")

        # ---------------------------
        # Item
        # ---------------------------
        item_dir = self.stac_root / "items" / "2025" / "11" / "01"
        item_dir.mkdir(parents=True)

        item = {
            "type": "Feature",
            "stac_version": "1.1.0",
            "id": "item1",
            "collection": "LHYP_L2B_REF",
            "geometry": box(
                15.1250808, -23.6025008, 15.1266992, -23.6005592
            ).__geo_interface__,
            "bbox": [15.1250808, -23.6025008, 15.1266992, -23.6005592],
            "properties": {
                "datetime": "2025-11-01T10:33:35Z",
                "end_datetime": "2025-11-01T10:38:55Z",
            },
            "links": [
                {
                    "rel": "self",
                    "href": "stac://items/2025/11/01/item1.json",
                    "type": "application/json",
                }
            ],
            "assets": {
                "data": {
                    "href": "asset://data/LHYP_L2B_REF/foo.nc",
                    "type": "application/octet-stream",
                }
            },
        }

        (item_dir / "item1.json").write_text(json.dumps(item, indent=2))

        self.handler = STACAPICallHandler(context=self.context)

    def tearDown(self):
        self.tmp.cleanup()

    # ---------------------------------------------------------

    def test_list_collections(self):
        cols = self.handler.list_collections()
        self.assertEqual(cols, ["LHYP_L2B_REF"])

    def test_query_returns_matching_productitem(self):
        results = self.handler.perform_query(
            {
                "collection": "LHYP_L2B_REF",
                "start_time": "2025-01-01T00:00:00Z",
                "stop_time": "2025-12-31T00:00:00Z",
            }
        )

        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], ProductItem)
        self.assertEqual(results[0].id, "item1")

    def test_spatial_filtering(self):
        results = self.handler.perform_query(
            {
                "collection": "LHYP_L2B_REF",
                "geom": box(70, 70, 80, 80),
            }
        )
        self.assertEqual(len(results), 0)

    def test_download_product_resolves_asset(self):
        results = self.handler.perform_query({"collection": "LHYP_L2B_REF"})
        product = results[0]
        path = self.handler.download_product(product)

        expected = self.data_root / "data" / "LHYP_L2B_REF" / "foo.nc"
        self.assertEqual(Path(path), expected)

    def test_download_product_set(self):
        results = self.handler.perform_query({"collection": "LHYP_L2B_REF"})
        paths = self.handler.download_product(results)
        self.assertEqual(len(paths), 1)
