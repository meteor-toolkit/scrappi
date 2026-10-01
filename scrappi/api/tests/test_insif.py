"""Tests for scrappi.api.insif."""

import sys
import types
import unittest
from unittest import mock

from shapely.geometry import Polygon

from scrappi import ScrappiContext
from scrappi.api.insif import INSIFCallHandler


class _FakeGeoDBClient:
    def __init__(self, *args, **kwargs):
        self.whoami = object()

    def get_my_collections(self, database):
        return {"collection": ["TEST-raw"]}

    def get_metadata(self, collection, database):
        return types.SimpleNamespace(
            site_id="TEST_SITE",
            site_name="Test site",
            spatial_extent=[[0.0, 0.0, 1.0, 1.0]],
        )


class TestINSIFCallHandler(unittest.TestCase):
    def setUp(self):
        fake_xcube_geodb = types.ModuleType("xcube_geodb")
        fake_core = types.ModuleType("xcube_geodb.core")
        fake_geodb = types.ModuleType("xcube_geodb.core.geodb")
        fake_geodb.GeoDBClient = _FakeGeoDBClient
        fake_core.geodb = fake_geodb
        fake_xcube_geodb.core = fake_core

        with mock.patch.dict(
            sys.modules,
            {
                "xcube_geodb": fake_xcube_geodb,
                "xcube_geodb.core": fake_core,
                "xcube_geodb.core.geodb": fake_geodb,
            },
        ):
            self._context = ScrappiContext()
            self._context["insif"] = {
                "credentials": {"username": "user", "password": "secret"},
                "include_uncertainty": False,
            }
            self.handler = INSIFCallHandler(self._context)

    def test_list_collections(self):
        self.assertEqual(self.handler.list_collections(), [
            "INSIF_RADIRRREF",
            "INSIF_RAD",
            "INSIF_IRR",
            "INSIF_REF",
            "INSIF_ALLIDX",
            "INSIF_FLUO",
            "INSIF_INDICES",
            "INSIF_RAW",
        ])

    def test_get_insif_collections_from_query_by_site(self):
        with mock.patch.object(self.handler, "get_flox_sn_from_site", return_value=["TEST"]):
            result = self.handler.get_insif_collections_from_query({
                "site": "TEST_SITE",
                "collection": "INSIF_RAW",
                "start_time": "2024-01-01T00:00:00",
                "stop_time": "2024-01-02T00:00:00",
            })
        self.assertEqual(result, ["TEST-raw"])

    def test_get_insif_collections_from_query_by_geom(self):
        roi = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        with mock.patch.object(self.handler, "get_flox_sn_from_roi", return_value=["TEST"]):
            result = self.handler.get_insif_collections_from_query({
                "geom": roi,
                "collection": "INSIF_ALLIDX",
            })
        self.assertEqual(result, ["TEST-idx"])

    def test_get_insif_collections_from_query_unknown_collection_raises(self):
        with mock.patch.object(self.handler, "get_flox_sn_from_site", return_value=["TEST"]):
            with self.assertRaises(ValueError):
                self.handler.get_insif_collections_from_query({
                    "site": "TEST_SITE",
                    "collection": "NOT_A_COLLECTION",
                })

    def test_generate_product_id(self):
        start = self.handler._get_datetime("2024-01-01T00:00:00")
        stop = self.handler._get_datetime("2024-01-02T03:00:00")
        product_id = self.handler.generate_product_id("INSIF_RAW", "TEST_SITE", start, stop)
        self.assertEqual(product_id, "INSIF_RAW_TEST_SITE_20240101T000000_20240102T030000.nc")


if __name__ == "__main__":
    unittest.main()
