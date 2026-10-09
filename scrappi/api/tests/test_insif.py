"""Tests for scrappi.api.insif."""

import sys
import types
import unittest
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
                "inc_rad": [1.0, 2.0],
                "refl_rad": [3.0, 4.0],
                "refl": [5.0, 6.0],
                "inc_rad_f": [7.0, 8.0],
                "refl_rad_f": [9.0, 10.0],
                "refl_f": [11.0, 12.0],
            },
            {
                "utc_time": "2024-01-01T00:05:00",
                "geometry": Polygon([(1, 0), (2, 0), (2, 1), (1, 1)]),
                "inc_rad": [2.0, 3.0],
                "refl_rad": [4.0, 5.0],
                "refl": [6.0, 7.0],
                "inc_rad_f": [8.0, 9.0],
                "refl_rad_f": [10.0, 11.0],
                "refl_f": [12.0, 13.0],
            },
        ]

        ds = self.handler.make_xarray_dataset(pd.DataFrame(rows))

        self.assertIn("inc_rad", ds.data_vars)
        self.assertIn("refl_rad", ds.data_vars)
        self.assertIn("refl", ds.data_vars)
        self.assertIn("inc_rad_f", ds.data_vars)
        self.assertIn("refl_rad_f", ds.data_vars)
        self.assertIn("refl_f", ds.data_vars)
        self.assertIn("err_corr_inc_rad_systematic_indepLE", ds.data_vars)
        self.assertIn("err_corr_refl_rad_systematic_indepLE", ds.data_vars)
        self.assertIn("err_corr_refl_systematic", ds.data_vars)
        self.assertTrue((ds["err_corr_inc_rad_systematic_indepLE"].values == 1.0).all())
        self.assertEqual(ds["inc_rad"].attrs["standard_name"], "downwelling_irradiance")

        self.assertEqual(ds["inc_rad"].shape, (1024, 2))
        self.assertEqual(ds["refl_rad"].shape, (1024, 2))
        self.assertEqual(ds["refl"].shape, (1024, 2))
        self.assertEqual(ds["UTC_time"].size, 2)

    def test_make_xarray_dataset_keeps_template_variable_attributes(self):
        import xarray as xr
        from pathlib import Path

        rows = [
            {
                "utc_time": "2024-01-01T00:00:00",
                "geometry": Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                "inc_rad": [1.0, 2.0],
                "refl_rad": [3.0, 4.0],
                "refl": [5.0, 6.0],
            }
        ]

        ds = self.handler.make_xarray_dataset(pd.DataFrame(rows))
        template = xr.open_dataset(Path(__file__).resolve().parents[2] / "data" / "RadIrrRef_FLOX_TEMPLATE.nc")

        self.assertIn("long_name", ds["inc_rad"].attrs)
        self.assertEqual(ds["inc_rad"].attrs["long_name"], template["inc_rad"].attrs["long_name"])
        self.assertIn("standard_name", ds["inc_rad"].attrs)
        self.assertEqual(ds["inc_rad"].attrs["standard_name"], template["inc_rad"].attrs["standard_name"])

    def test_make_xarray_dataset_keeps_err_corr_without_utc_dimension(self):
        rows = [
            {
                "utc_time": "2024-01-01T00:00:00",
                "geometry": Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                "inc_rad": [1.0] * 1024,
                "refl_rad": [2.0] * 1024,
                "refl": [3.0] * 1024,
                "err_corr_E_systematic_indepLE": [4.0] * 1024,
                "err_corr_E_systematic_indepLE_full": [5.0] * 1024,
            }
        ]

        ds = self.handler.make_xarray_dataset(pd.DataFrame(rows))

        self.assertNotIn("UTC_time", ds["err_corr_E_systematic_indepLE"].dims)
        self.assertNotIn("UTC_time", ds["err_corr_E_systematic_indepLE_full"].dims)
        self.assertEqual(ds["inc_rad"].sizes["wavelength"], 1024)
        self.assertEqual(ds["inc_rad_f"].sizes["wavelength_full"], 1024)

    def test_template_metadata_keeps_attribute_strings_unchanged(self):
        import xarray as xr
        from pathlib import Path

        template = xr.open_dataset(Path(__file__).resolve().parents[2] / "data" / "RadIrrRef_FLOX_TEMPLATE.nc")

        self.assertEqual(template["inc_rad"].attrs["standard_name"], "downwelling_irradiance")
        self.assertIn("u_E_random", template["inc_rad"].attrs["unc_comps"])
        self.assertNotIn("inc_rad_unc_random", template["inc_rad"].attrs["unc_comps"])
        self.assertIn("err_corr_inc_rad_systematic_indepLE", list(template.data_vars))


class TestStandaloneINSIFClient(unittest.TestCase):
    def test_query_and_export_netcdf(self):
        from scrappi.api.insif_standalone import StandaloneINSIFDatabaseClient

        class FakeGeoDB:
            def __init__(self, *args, **kwargs):
                self._calls = []

            def get_collection_pg(self, collection, select=None, where=None, database=None):
                self._calls.append((collection, select, where, database))
                rows = [
                    {
                        "utc_time": "2024-01-01T00:00:00",
                        "geometry": Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
                        "refl": [1.0, 2.0],
                        "refl_f": [3.0, 4.0],
                    },
                    {
                        "utc_time": "2024-01-01T00:05:00",
                        "geometry": Polygon([(1, 0), (2, 0), (2, 1), (1, 1)]),
                        "refl": [5.0, 6.0],
                        "refl_f": [7.0, 8.0],
                    },
                ]
                import pandas as pd
                return pd.DataFrame(rows)

        with mock.patch.dict(
            sys.modules,
            {
                "xcube_geodb": types.ModuleType("xcube_geodb"),
                "xcube_geodb.core": types.ModuleType("xcube_geodb.core"),
                "xcube_geodb.core.geodb": types.ModuleType("xcube_geodb.core.geodb"),
            },
        ):
            sys.modules["xcube_geodb.core.geodb"].GeoDBClient = FakeGeoDB

            client = StandaloneINSIFDatabaseClient(
                username="user",
                password="secret",
                include_uncertainty=True,
            )
            with mock.patch.object(client, "_get_collection_for_query", return_value="TEST-proc"):
                out = client.query_and_save_netcdf(
                    flox_sn="TEST",
                    collection="INSIF_RADIRRREF",
                    variables=["utc_time", "geometry", "refl", "refl_f"],
                    start_time="2024-01-01T00:00:00",
                    stop_time="2024-01-02T00:00:00",
                    destin="/tmp/test_insif.nc",
                )

            self.assertTrue(out.endswith(".nc"))
            self.assertIn("utc_time", client.last_dataset.coords)

    def test_query_and_export_netcdf_keeps_coordinate_attributes(self):
        import tempfile
        import xarray as xr

        from scrappi.api.insif_standalone import StandaloneINSIFDatabaseClient

        class FakeGeoDB:
            def __init__(self, *args, **kwargs):
                self._calls = []

            def get_collection_pg(self, collection, select=None, where=None, database=None):
                self._calls.append((collection, select, where, database))
                return pd.DataFrame([
                    {
                        "utc_time": "2024-01-01T00:00:00",
                        "refl": [1.0, 2.0],
                        "refl_f": [3.0, 4.0],
                    },
                    {
                        "utc_time": "2024-01-01T00:05:00",
                        "refl": [5.0, 6.0],
                        "refl_f": [7.0, 8.0],
                    },
                ])

        with mock.patch.dict(
            sys.modules,
            {
                "xcube_geodb": types.ModuleType("xcube_geodb"),
                "xcube_geodb.core": types.ModuleType("xcube_geodb.core"),
                "xcube_geodb.core.geodb": types.ModuleType("xcube_geodb.core.geodb"),
            },
        ):
            sys.modules["xcube_geodb.core.geodb"].GeoDBClient = FakeGeoDB
            client = StandaloneINSIFDatabaseClient(
                username="user",
                password="secret",
                include_uncertainty=False,
            )
            with tempfile.NamedTemporaryFile(suffix=".nc") as tmp:
                client.query_and_save_netcdf(
                    flox_sn="TEST",
                    collection="INSIF_RADIRRREF",
                    variables=["utc_time", "refl", "refl_f"],
                    start_time="2024-01-01T00:00:00",
                    stop_time="2024-01-02T00:00:00",
                    destin=tmp.name,
                )
                with xr.open_dataset(tmp.name) as reopened:
                    self.assertIn("long_name", reopened["UTC_time"].attrs)
                    self.assertEqual(reopened["UTC_time"].attrs["units"], "seconds since 1970-01-01 00:00:00")
                    self.assertEqual(reopened["utc_time"].attrs["units"], "seconds since 1970-01-01 00:00:00")
                    self.assertIn("long_name", reopened["wavelength"].attrs)
                    self.assertIn("standard_name", reopened["wavelength"].attrs)


if __name__ == "__main__":
    unittest.main()
