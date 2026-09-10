"""Tests for scrappi.api.offline_query.product_matches_query."""

import math
import unittest
from datetime import datetime

from shapely.geometry import Polygon

from scrappi.api.offline_query import product_matches_query, query_collections
from scrappi.product import ProductItem


def _product(**over):
    kw = dict(
        constellation="Sentinel-2",
        platform="S2A",
        collection="S2_MSI_L1C",
        id="S2A_MSIL1C_20230607T104621",
        geometry=Polygon([(0, 0), (2, 0), (2, 2), (0, 2)]),
        start_time=datetime(2023, 6, 7, 10, 46, 21),
        stop_time=datetime(2023, 6, 7, 10, 46, 21),
        url="",
    )
    kw.update(over)
    return ProductItem(**kw)


class TestQueryCollections(unittest.TestCase):
    def test_single(self):
        self.assertEqual(query_collections({"collection": "X"}), ["X"])

    def test_plural_str_and_list(self):
        self.assertEqual(query_collections({"collections": "X"}), ["X"])
        self.assertEqual(query_collections({"collections": ["X", "Y"]}), ["X", "Y"])

    def test_none(self):
        self.assertEqual(query_collections({}), [])


class TestProductMatchesQuery(unittest.TestCase):
    def test_empty_query_matches(self):
        self.assertTrue(product_matches_query(_product(), {}))

    def test_collection_filter(self):
        self.assertTrue(product_matches_query(_product(), {"collection": "S2_MSI_L1C"}))
        self.assertFalse(product_matches_query(_product(), {"collection": "LANDSAT_C2L1"}))

    def test_time_window_overlap(self):
        q = {"start_time": datetime(2023, 6, 1), "stop_time": datetime(2023, 6, 30)}
        self.assertTrue(product_matches_query(_product(), q))
        self.assertFalse(
            product_matches_query(_product(), {"start_time": datetime(2024, 1, 1), "stop_time": datetime(2024, 2, 1)})
        )

    def test_geometry_intersection(self):
        self.assertTrue(product_matches_query(_product(), {"geom": Polygon([(1, 1), (3, 1), (3, 3), (1, 3)])}))
        self.assertFalse(product_matches_query(_product(), {"geom": Polygon([(10, 10), (11, 10), (11, 11), (10, 11)])}))

    def test_geometry_as_bbox_dict(self):
        bbox = {
            "latitude_minimum": 1,
            "longitude_minimum": 1,
            "latitude_maximum": 3,
            "longitude_maximum": 3,
        }
        self.assertTrue(product_matches_query(_product(), {"geom": bbox}))

    def test_platform_filter(self):
        self.assertTrue(product_matches_query(_product(), {"platform": "S2A"}))
        self.assertFalse(product_matches_query(_product(), {"platform": "S2B"}))

    def test_cloud_cover_max(self):
        self.assertFalse(product_matches_query(_product(cloud_fraction=80.0), {"cloud_cover_max": 20}))
        self.assertTrue(product_matches_query(_product(cloud_fraction=5.0), {"cloud_cover_max": 20}))

    def test_unknown_cloud_fraction_is_kept(self):
        self.assertTrue(product_matches_query(_product(cloud_fraction=math.nan), {"cloud_cover_max": 20}))
        self.assertTrue(product_matches_query(_product(cloud_fraction=None), {"cloud_cover_max": 20}))


if __name__ == "__main__":
    unittest.main()
