"""Tests for scrappi.api.offline_query."""

import math
import unittest
import unittest.mock
from datetime import datetime

from shapely.geometry import Polygon

from scrappi.api import offline_query
from scrappi.api.offline_query import CompiledQuery, compile_query, product_matches_query, query_collections
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


class TestCompiledQuery(unittest.TestCase):
    def test_compile_parses_geom_and_time_once_then_reuses(self):
        q = {
            "collection": "S2_MSI_L1C",
            "start_time": "2023-06-01",
            "stop_time": "2023-06-30",
            "geom": {"latitude_minimum": 1, "longitude_minimum": 1, "latitude_maximum": 3, "longitude_maximum": 3},
        }
        with unittest.mock.patch.object(
            offline_query, "convert_geom_shapely", wraps=offline_query.convert_geom_shapely
        ) as geom:
            cq = compile_query(q)
            for _ in range(5):
                cq.matches(_product())
        geom.assert_called_once()  # not once per product

    def test_compiled_matches_agrees_with_product_matches_query(self):
        q = {"collection": "S2_MSI_L1C", "platform": "S2A"}
        self.assertEqual(compile_query(q).matches(_product()), product_matches_query(_product(), q))

    def test_empty_query_compiles_to_all_none(self):
        cq = compile_query({})
        self.assertEqual(cq.collections, frozenset())
        self.assertIsNone(cq.start_time)
        self.assertIsNone(cq.geom)
        self.assertTrue(cq.matches(_product()))

    def test_compile_returns_a_compiled_query(self):
        self.assertIsInstance(compile_query({}), CompiledQuery)

    def test_unparseable_start_time_warns_and_is_dropped_not_silently_ignored(self):
        """Regression test: a malformed query field used to be swallowed with no
        signal anything was wrong, silently widening the query to "no time filter"
        instead of surfacing the caller's mistake."""
        with self.assertWarns(UserWarning):
            cq = compile_query({"start_time": "2024-13-45 not a date"})
        self.assertIsNone(cq.start_time)

    def test_unparseable_geom_warns_and_is_dropped_not_silently_ignored(self):
        with self.assertWarns(UserWarning):
            cq = compile_query({"geom": "NOT WKT AT ALL"})
        self.assertIsNone(cq.geom)

    def test_a_products_own_unparseable_time_is_not_warned_about(self):
        """Unlike the query side, a malformed value on the *product* (e.g. from a
        broken archived record) is tolerated silently -- see _as_datetime's
        docstring for why (kept, not excluded, matching the NaN-cloud-fraction
        precedent)."""
        import warnings as _warnings

        p = _product()
        p.start_time = "also not a date"  # as if set directly from a malformed archived record
        with _warnings.catch_warnings():
            _warnings.simplefilter("error")
            self.assertTrue(compile_query({}).matches(p))


if __name__ == "__main__":
    unittest.main()
