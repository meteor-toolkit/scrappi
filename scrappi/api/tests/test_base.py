"""scrappi.api.tests.test_base - tests for scrappi.api.base"""

import unittest
import unittest.mock as mock
import datetime as dt

import shapely
from shapely.geometry import Polygon, Point

from scrappi.api.base import BaseAPICallHandler
from scrappi.product import ProductItemSet
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
        dummy_api_call_handler = self.DummyAPICallHandler(context)

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


if __name__ == "__main__":
    unittest.main()
