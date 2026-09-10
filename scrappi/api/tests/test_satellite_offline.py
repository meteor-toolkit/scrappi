"""Tests for scrappi.api.satellite_offline.SatelliteOfflineCallHandler (skeleton).

These build a minimal version of the archive layout the handler expects -- a
per-collection subdirectory holding scrappi's ``stac/`` tree plus the data
product -- and check the query/download/to_stac_item flow end to end.
"""

import json
import os
import unittest
from datetime import datetime
from tempfile import TemporaryDirectory

from scrappi import ScrappiContext
from scrappi.api.satellite_offline import SatelliteOfflineCallHandler
from scrappi.fs.stacfilesystem import STACFileSystem

_ITEM_ID = "S2A_MSIL1C_20230607T104621_N0509_R051_T31UDQ_20230607T142522"


def _stac_item(item_id: str = _ITEM_ID) -> dict:
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": item_id,
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]},
        "bbox": [0, 0, 2, 2],
        "properties": {
            "datetime": "2023-06-07T10:46:21Z",
            "start_datetime": "2023-06-07T10:46:21Z",
            "end_datetime": "2023-06-07T10:46:21Z",
            "platform": "S2A",
            "constellation": "Sentinel-2",
            "eo:cloud_cover": 12.0,
        },
        "links": [],
        "assets": {"data": {"href": f"./{item_id}.SAFE"}},
        "collection": "S2_MSI_L1C",
    }


class TestSatelliteOfflineCallHandler(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.coll_dir = os.path.join(self.root, "S2_MSI_L1C")

        # data product: an extracted .SAFE directory
        safe = os.path.join(self.coll_dir, "data", f"{_ITEM_ID}.SAFE")
        os.makedirs(safe)
        open(os.path.join(safe, "MTD_MSIL1C.xml"), "w").close()

        # scrappi's stac tree
        items_dir = os.path.join(self.coll_dir, "stac", "S2_MSI_L1C", "items", "2023", "06", "07")
        os.makedirs(items_dir)
        with open(os.path.join(items_dir, f"{_ITEM_ID}.json"), "w") as f:
            json.dump(_stac_item(), f)
        with open(os.path.join(self.coll_dir, "stac", "S2_MSI_L1C", "collection.json"), "w") as f:
            json.dump({"type": "Collection", "id": "S2_MSI_L1C", "stac_version": "1.0.0",
                       "description": "", "license": "other",
                       "extent": {"spatial": {"bbox": [[0, 0, 2, 2]]},
                                  "temporal": {"interval": [["2023-06-07T00:00:00Z", None]]}},
                       "links": []}, f)

        self.handler = SatelliteOfflineCallHandler(ScrappiContext(), archive_path=self.root)

    def _query(self, **over):
        q = {
            "collection": "S2_MSI_L1C",
            "start_time": datetime(2023, 6, 1),
            "stop_time": datetime(2023, 6, 30),
            "geom": {"latitude_minimum": 0, "longitude_minimum": 0,
                     "latitude_maximum": 3, "longitude_maximum": 3},
        }
        q.update(over)
        return q

    # ---- discovery ----
    def test_list_collections_reads_collection_json(self):
        self.assertEqual(self.handler.list_collections(), ["S2_MSI_L1C"])

    def test_collection_root_prefers_the_named_subdirectory(self):
        self.assertEqual(
            os.path.normpath(self.handler._collection_root("S2_MSI_L1C")),
            os.path.normpath(self.coll_dir),
        )

    def test_collection_root_context_override_wins(self):
        ctx = ScrappiContext()
        ctx["api"]["offline_archive_paths"] = {"S2_MSI_L1C": "/explicit/path"}
        h = SatelliteOfflineCallHandler(ctx, archive_path=self.root)
        self.assertEqual(h._collection_root("S2_MSI_L1C"), "/explicit/path")

    # ---- query ----
    def test_perform_query_returns_the_matching_product(self):
        products = self.handler.perform_query(self._query())
        self.assertEqual(len(products), 1)
        p = products[0]
        self.assertEqual(p.id, _ITEM_ID)
        self.assertEqual(p.collection, "S2_MSI_L1C")
        self.assertEqual(p.platform, "S2A")

    def test_perform_query_applies_the_geometry_filter(self):
        far = self._query(geom={"latitude_minimum": 40, "longitude_minimum": 40,
                                "latitude_maximum": 41, "longitude_maximum": 41})
        self.assertEqual(len(self.handler.perform_query(far)), 0)

    def test_perform_query_applies_the_time_filter(self):
        self.assertEqual(
            len(self.handler.perform_query(self._query(start_time=datetime(2024, 1, 1),
                                                       stop_time=datetime(2024, 2, 1)))),
            0,
        )

    def test_product_filesystem_is_read_only_stac_pinned_to_the_data_dir(self):
        p = self.handler.perform_query(self._query())[0]
        self.assertIsInstance(p.filesystem, STACFileSystem)
        self.assertTrue(p.filesystem.read_only)
        self.assertEqual(
            os.path.normpath(p.filesystem.directory),
            os.path.normpath(os.path.join(self.coll_dir, "data")),
        )

    def test_product_can_be_converted_to_a_stac_item(self):
        p = self.handler.perform_query(self._query())[0]
        item = p.to_stac_item()
        self.assertEqual(item.id, _ITEM_ID)

    # ---- download ----
    def test_download_product_resolves_the_safe_directory(self):
        p = self.handler.perform_query(self._query())[0]
        path = self.handler.download_product(p)
        self.assertEqual(
            os.path.normpath(path),
            os.path.normpath(os.path.join(self.coll_dir, "data", f"{_ITEM_ID}.SAFE")),
        )

    # ---- unconfigured handler is inert, not fatal ----
    def test_unconfigured_handler_lists_nothing_and_queries_empty(self):
        h = SatelliteOfflineCallHandler(ScrappiContext())  # no archive_path anywhere
        self.assertEqual(h.list_collections(), [])
        with self.assertWarns(UserWarning):
            self.assertEqual(len(h.perform_query(self._query())), 0)

    def test_archive_without_a_stac_tree_warns(self):
        bare = TemporaryDirectory()
        self.addCleanup(bare.cleanup)
        os.makedirs(os.path.join(bare.name, "S2_MSI_L1C"))
        open(os.path.join(bare.name, "S2_MSI_L1C", f"{_ITEM_ID}.zip"), "w").close()
        h = SatelliteOfflineCallHandler(ScrappiContext(), archive_path=bare.name)
        with self.assertWarns(UserWarning):
            self.assertEqual(len(h.perform_query(self._query())), 0)


if __name__ == "__main__":
    unittest.main()
