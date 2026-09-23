"""scrappi.api.tests.test_base - tests for scrappi.api.base"""

import unittest
import datetime as dt

import shapely
from shapely.geometry import Polygon, Point

from scrappi.api.base import BaseAPICallHandler
from scrappi import ScrappiContext

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]

context = ScrappiContext()


class TestBaseAPICallHandler(unittest.TestCase):
    def setUp(self) -> None:
        # dummy helper class to test BaseAPICallHandler class
        class DummyAPICallHandler(BaseAPICallHandler):
            name = "dummy_api"

            def list_collections(self):
                return ["LANDSAT_C2L1", "S2_MSI_L1C"]

            def return_url(self, query):
                raise NotImplementedError

            def perform_query(self, query):
                return query

            def download_metadata(self, product, path):
                raise NotImplementedError

            def download_product(self, product, path):
                raise NotImplementedError

        self.DummyAPICallHandler = DummyAPICallHandler

    def test_subclass_builds(self) -> None:
        _dummy_api_call_handler = self.DummyAPICallHandler(context)

    def test_get_datetime_obj(self):
        input_dt = dt.datetime(2022, 10, 20)
        expected = input_dt.replace(tzinfo=dt.timezone.utc)
        self.assertEqual(self.DummyAPICallHandler._get_datetime(input_dt), expected)

    def test_get_datetime_date_obj(self):
        input_dt = dt.date(2022, 10, 20)
        self.assertEqual(
            self.DummyAPICallHandler._get_datetime(input_dt),
            dt.datetime(2022, 10, 20, 0, 0, 0, tzinfo=dt.timezone.utc),
        )

    def test_get_datetime_str_1(self):
        input_dt = "2022-09-10T20:23:47.111356Z"
        self.assertEqual(
            self.DummyAPICallHandler._get_datetime(input_dt),
            dt.datetime(2022, 9, 10, 20, 23, 47, 111356, tzinfo=dt.timezone.utc),
        )

    def test_get_datetime_str_2(self):
        input_dt = "2022-09-10T20:23:47.111356"
        self.assertEqual(
            self.DummyAPICallHandler._get_datetime(input_dt),
            dt.datetime(2022, 9, 10, 20, 23, 47, 111356, tzinfo=dt.timezone.utc),
        )

    def test_get_datetime_str_3(self):
        input_dt = "2022-09-10T20:23:47.11135"
        self.assertEqual(
            self.DummyAPICallHandler._get_datetime(input_dt),
            dt.datetime(2022, 9, 10, 20, 23, 47, 111350, tzinfo=dt.timezone.utc),
        )

    def test_get_datetime_str_4(self):
        input_dt = "2022-09-10 20:23:47.1113"
        self.assertEqual(
            self.DummyAPICallHandler._get_datetime(input_dt),
            dt.datetime(2022, 9, 10, 20, 23, 47, 111300, tzinfo=dt.timezone.utc),
        )

    def test_get_datetime_str_5(self):
        input_dt = "2022-09-10 20:23:47.111"
        self.assertEqual(
            self.DummyAPICallHandler._get_datetime(input_dt),
            dt.datetime(2022, 9, 10, 20, 23, 47, 111000, tzinfo=dt.timezone.utc),
        )

    def test_get_datetime_str_6(self):
        input_dt = "2022-09-10 20:23:47."
        self.assertEqual(
            self.DummyAPICallHandler._get_datetime(input_dt),
            dt.datetime(2022, 9, 10, 20, 23, 47, tzinfo=dt.timezone.utc),
        )

    def test_get_datetime_str_error(self):
        input_dt = "2022-09-10T20:23:47/11135"
        self.assertRaises(ValueError, self.DummyAPICallHandler._get_datetime, input_dt)

    def test_get_geom_list(
        self,
    ):  # longitude_minimum, latitude_minimum, longitude_maximum, longitude_maximum
        input_geom = [40, 120, 60, 140]
        output_geom = {
            "latitude_minimum": 40,
            "longitude_minimum": 120,
            "latitude_maximum": 60,
            "longitude_maximum": 140,
        }
        self.assertEqual(self.DummyAPICallHandler._get_geom(input_geom), output_geom)

    def test_get_geom_list_error(self):
        input_geom = [120, 40, 140, 60]
        self.assertRaises(ValueError, self.DummyAPICallHandler._get_geom, input_geom)

    def test_get_geom_dict(self):
        input_geom = {
            "latitude_minimum": 40,
            "longitude_minimum": 120,
            "latitude_maximum": 60,
            "longitude_maximum": 140,
        }
        self.assertEqual(self.DummyAPICallHandler._get_geom(input_geom), input_geom)

    def test_get_geom_dict_error(self):
        input_geom = {"LAT_AND_LON": 23498293}
        self.assertRaises(ValueError, self.DummyAPICallHandler._get_geom, input_geom)

    def test_get_geom_shapely(self):
        input_geom = Polygon([[120, 40], [160, 40], [160, 60], [140, 60]])
        output_geom = Polygon([[120, 40], [160, 40], [160, 60], [140, 60]])
        self.assertEqual(self.DummyAPICallHandler._get_geom(input_geom), output_geom)

    def test_get_geom_point(self):
        input_geom = Point(120, 40)
        self.assertEqual(self.DummyAPICallHandler._get_geom(input_geom), input_geom)

    def test_get_geom_wktstr(self):
        input_geom = "POLYGON ((120 40, 160 40, 160 60, 140 60, 120 40))"
        output_geom = shapely.wkt.loads("POLYGON ((120 40, 160 40, 160 60, 140 60, 120 40))")
        self.assertEqual(self.DummyAPICallHandler._get_geom(input_geom), output_geom)

    def test_get_geom_wktstr_error_1(self):
        input_geom = "POLY ((120 40, 160 40, 160 60, 140 60, 120 40))"
        self.assertRaises(ValueError, self.DummyAPICallHandler._get_geom, input_geom)

    def test_get_geom_wktstr_error_2(self):
        input_geom = "Random string of characters 468t52*&^*£)IWRbi"
        self.assertRaises(ValueError, self.DummyAPICallHandler._get_geom, input_geom)

    def test_get_product_type(self):
        dummy_api_call_handler = self.DummyAPICallHandler(context)
        self.assertEqual(dummy_api_call_handler._get_product_type("LANDSAT_C2L1"), "LANDSAT_C2L1")

    def test_parse_platform_from_name_sentinel2(self):
        dummy_api_call_handler = self.DummyAPICallHandler(context)
        for prefix in ["S2A", "S2B", "S2C"]:
            name = f"{prefix}_MSIL1C_20221001T084801_N0400_R107_T33KWP_20221001T123324"
            self.assertEqual(dummy_api_call_handler.parse_platform_from_name(name), prefix)

    def test_parse_platform_from_name_sentinel3(self):
        dummy_api_call_handler = self.DummyAPICallHandler(context)
        for prefix in ["S3A", "S3B"]:
            name = f"{prefix}_OL_1_EFR____20221001T084801_20221001T085101_20221001T104506"
            self.assertEqual(dummy_api_call_handler.parse_platform_from_name(name), prefix)

    def test_parse_platform_from_name_landsat8_returns_short_code(self):
        """LC08/LO08 product IDs return the short code 'LS8', not 'Landsat-8'.

        Regression test: previously this returned the long-form name 'Landsat-8',
        inconsistent with the short-code form used for every other mission
        (e.g. 'S2A') and with the satellite identifiers used by downstream
        consumers (e.g. orbitx's satellite short codes), so a client-side filter
        comparing this value against a configured platform identifier could
        never match.
        """
        dummy_api_call_handler = self.DummyAPICallHandler(context)
        for prefix in ["LC08", "LO08"]:
            name = f"{prefix}_L1TP_172030_20220120_20220127_02_T2A"
            self.assertEqual(dummy_api_call_handler.parse_platform_from_name(name), "LS8")

    def test_parse_platform_from_name_landsat9_returns_short_code(self):
        """LC09/LO09 product IDs return the short code 'LS9', not 'Landsat-9'."""
        dummy_api_call_handler = self.DummyAPICallHandler(context)
        for prefix in ["LC09", "LO09"]:
            name = f"{prefix}_L1TP_179076_20220926_20230327_02_T1"
            self.assertEqual(dummy_api_call_handler.parse_platform_from_name(name), "LS9")

    def test_parse_platform_from_name_ecmwf_passthrough(self):
        dummy_api_call_handler = self.DummyAPICallHandler(context)
        for prefix in ["CAMS", "ERA5", "REAN"]:
            self.assertEqual(dummy_api_call_handler.parse_platform_from_name(f"{prefix}_20220101"), prefix)

    def test_parse_platform_from_name_modis_terra(self):
        dummy_api_call_handler = self.DummyAPICallHandler(context)
        name = "MOD021KM.A2022001.0000.061.2022002123456.hdf"
        self.assertEqual(dummy_api_call_handler.parse_platform_from_name(name), "Terra")

    def test_parse_platform_from_name_modis_aqua(self):
        dummy_api_call_handler = self.DummyAPICallHandler(context)
        name = "MYD021KM.A2022001.0000.061.2022002123456.hdf"
        self.assertEqual(dummy_api_call_handler.parse_platform_from_name(name), "Aqua")

    def test_parse_platform_from_name_unrecognized_raises(self):
        dummy_api_call_handler = self.DummyAPICallHandler(context)
        self.assertRaises(
            NotImplementedError,
            dummy_api_call_handler.parse_platform_from_name,
            "UNKNOWN_PRODUCT_ID_12345",
        )

    def test_parse_platform_from_name_gistda_theos(self):
        """A real GISTDA THEOS-1 product ID (TH_CAT_<id>_1M_<site>_<date>) resolves
        to 'GISTDA' -- the value action's own PLATFORM_COLLECTIONS/--platform code
        uses, and so what Sat2InSituMUFinder's platform filter needs a harvested
        product's ProductItem.platform to equal."""
        dummy_api_call_handler = self.DummyAPICallHandler(context)
        name = "TH_CAT_22021001412034_1_1M_GOBABEB_20220209"
        self.assertEqual(dummy_api_call_handler.parse_platform_from_name(name), "GISTDA")

    def test_parse_constellation_from_name_gistda_theos(self):
        dummy_api_call_handler = self.DummyAPICallHandler(context)
        name = "TH_CAT_22021001412034_1_1M_GOBABEB_20220209"
        self.assertEqual(dummy_api_call_handler.parse_constellation_from_name(name), "GISTDA")


if __name__ == "__main__":
    unittest.main()
