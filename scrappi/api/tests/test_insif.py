"""Tests for scrappi.api.insif."""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
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

    def test_make_xarray_dataset_builds_from_dataframe_and_adds_err_corr(self):
        rows = [
            {
                "utc_time": "2024-01-01T00:00:00",
                "geometry": Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                "inc_rad": [1.0] * 1024,
                "refl_rad": [3.0] * 1024,
                "refl": [5.0] * 1024,
                "inc_rad_f": [7.0] * 1024,
                "refl_rad_f": [9.0] * 1024,
                "refl_f": [11.0] * 1024,
                "refl_wl": [500.0 + i for i in range(1024)],
                "refl_f_wl": [700.0 + i for i in range(1024)],
                "refl_unc_systematic": [0.1] * 1024,
                "refl_f_unc_systematic": [0.2] * 1024,
            },
            {
                "utc_time": "2024-01-01T00:05:00",
                "geometry": Polygon([(1, 0), (2, 0), (2, 1), (1, 1)]),
                "inc_rad": [2.0] * 1024,
                "refl_rad": [4.0] * 1024,
                "refl": [6.0] * 1024,
                "inc_rad_f": [8.0] * 1024,
                "refl_rad_f": [10.0] * 1024,
                "refl_f": [12.0] * 1024,
                "refl_wl": [500.0 + i for i in range(1024)],
                "refl_f_wl": [700.0 + i for i in range(1024)],
                "refl_unc_systematic": [0.3] * 1024,
                "refl_f_unc_systematic": [0.4] * 1024,
            },
        ]

        ds = self.handler.make_xarray_dataset(pd.DataFrame(rows))

        self.assertIn("inc_rad", ds.data_vars)
        self.assertIn("refl_rad", ds.data_vars)
        self.assertIn("refl", ds.data_vars)
        self.assertIn("inc_rad_f", ds.data_vars)
        self.assertIn("refl_rad_f", ds.data_vars)
        self.assertIn("refl_f", ds.data_vars)
        self.assertIn("err_corr_inc_rad_system_indeple", ds.data_vars)
        self.assertIn("err_corr_refl_rad_system_indeple", ds.data_vars)
        self.assertIn("err_corr_refl_systematic", ds.data_vars)
        self.assertTrue((ds["err_corr_refl_systematic"].values == 1.0).all())
        self.assertEqual(ds["inc_rad"].attrs["standard_name"], "incoming_radiance_fluo")

        self.assertEqual(ds["inc_rad"].shape, (1024, 2))
        self.assertEqual(ds["refl_rad"].shape, (1024, 2))
        self.assertEqual(ds["refl"].shape, (1024, 2))
        self.assertEqual(ds["utc_time"].size, 2)

    def test_make_xarray_dataset_keeps_template_variable_attributes(self):
        rows = [
            {
                "utc_time": "2024-01-01T00:00:00",
                "geometry": Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                "inc_rad": [1.0] * 1024,
                "refl_rad": [3.0] * 1024,
                "refl": [5.0] * 1024,
                "refl_wl": [500.0 + i for i in range(1024)],
                "refl_f_wl": [700.0 + i for i in range(1024)],
            }
        ]

        ds = self.handler.make_xarray_dataset(pd.DataFrame(rows))

        self.assertIn("long_name", ds["inc_rad"].attrs)
        self.assertEqual(ds["inc_rad"].attrs["long_name"], "Incoming (downwelling) radiance for FLUO sensor")
        self.assertIn("standard_name", ds["inc_rad"].attrs)
        self.assertEqual(ds["inc_rad"].attrs["standard_name"], "incoming_radiance_fluo")

    def test_make_xarray_dataset_keeps_err_corr_without_utc_dimension(self):
        rows = [
            {
                "utc_time": "2024-01-01T00:00:00",
                "geometry": Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                "inc_rad": [1.0] * 1024,
                "refl_rad": [2.0] * 1024,
                "refl": [3.0] * 1024,
                "refl_wl": [500.0 + i for i in range(1024)],
                "refl_f_wl": [700.0 + i for i in range(1024)],
                "refl_unc_systematic": [0.1] * 1024,
                "refl_f_unc_systematic": [0.2] * 1024,
            }
        ]

        ds = self.handler.make_xarray_dataset(pd.DataFrame(rows))

        self.assertIn("wavelength", ds["err_corr_refl_systematic"].dims)
        self.assertIn("refl_unc_systematic", ds.data_vars)
        self.assertEqual(ds["inc_rad"].sizes["wavelength"], 1024)
        self.assertEqual(ds["inc_rad_f"].sizes["wavelength_full"], 1024)

    def test_make_xarray_dataset_serializes_site_metadata_for_netcdf(self):
        import os
        import tempfile

        rows = [
            {
                "utc_time": "2024-01-01T00:00:00",
                "geometry": Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                "inc_rad": [1.0] * 1024,
                "refl_rad": [3.0] * 1024,
                "refl": [5.0] * 1024,
                "refl_wl": [500.0 + i for i in range(1024)],
                "refl_f_wl": [700.0 + i for i in range(1024)],
            }
        ]

        self.handler.current_site_meta = {
            "site_id": "TEST_SITE",
            "flox_sn": "TEST",
            "spatial_extent": [[0.0, 0.0, 1.0, 1.0]],
            "summaries": {"platform": "INSIF"},
        }

        ds = self.handler.make_xarray_dataset(pd.DataFrame(rows))
        self.assertIn("spatial_extent", ds.attrs)
        self.assertEqual(ds.attrs["site_id"], "TEST_SITE")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "insif.nc")
            ds.to_netcdf(path)
            self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
