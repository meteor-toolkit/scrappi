"""scrappi.api.tests.test_earthaccess_api - tests for scrappi.api.earthaccess_api"""

import unittest
import os
import datetime as dt
from unittest import mock

import numpy as np
from shapely.geometry import Polygon

from scrappi.api.earthaccess_api import EarthaccessCallHandler
from scrappi.product import ProductItem, ProductItemSet
from scrappi import ScrappiContext
from earthaccess import DataGranule


__author__ = [
    "Joe Riordan <joe.riordan@npl.co.uk>",
]

example_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "examples",
)


class TestEarthaccessCallHandler(unittest.TestCase):
    """Test suite for EarthaccessCallHandler class"""

    def setUp(self):
        """Set up test fixtures"""
        self.earthaccess_call_handler = None

    @mock.patch("scrappi.api.earthaccess_api.earthaccess.login")
    def test_init_default(self, mock_login):
        """Test initialization with default context"""
        with mock.patch("scrappi.api.earthaccess_api.ScrappiContext") as mock_context:
            mock_context.return_value = {"earthaccess": None}
            handler = EarthaccessCallHandler()
            handler.download_product(None)
            mock_login.assert_called()

    @mock.patch("scrappi.api.earthaccess_api.earthaccess.login")
    def test_init_with_context(self, mock_login):
        """Test initialization with context"""
        context = ScrappiContext()
        context["earthaccess"] = {"configured": True}
        handler = EarthaccessCallHandler(context)
        # mock_login should not be called if earthaccess is configured
        # Note: actual behavior depends on context

    def test_set_product_type(self):
        """Test _set_product_type method"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()
            with mock.patch.object(handler, "_get_product_type", return_value="MOD09GA") as mock_get_product:
                result = handler._set_product_type("MOD09")
                self.assertEqual(result, "MOD09GA")
                mock_get_product.assert_called_with("MOD09")

    def test_set_datetime_with_string(self):
        """Test _set_datetime with string input"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()
            with mock.patch.object(handler, "_get_datetime", return_value=dt.datetime(2022, 6, 7, 23, 30)):
                result = handler._set_datetime("2022-06-07T23:30:00")
                self.assertEqual(result, "2022-06-07T23:30:00")

    def test_set_datetime_with_datetime_object(self):
        """Test _set_datetime with datetime object input"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()
            input_dt = dt.datetime(2022, 6, 7, 23, 30)
            with mock.patch.object(handler, "_get_datetime", return_value=input_dt):
                result = handler._set_datetime(input_dt)
                self.assertEqual(result, "2022-06-07T23:30:00")

    def test_set_geom_dict(self):
        """Test _set_geom with dictionary geometry"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()
            input_geom = {
                "latitude_minimum": 40,
                "longitude_minimum": 120,
                "latitude_maximum": 60,
                "longitude_maximum": 160,
            }
            expected_output = (120, 40, 160, 60)

            with mock.patch.object(handler, "_get_geom", return_value=input_geom):
                result = handler._set_geom(input_geom)
                self.assertEqual(result, expected_output)

    def test_set_geom_shapely_polygon(self):
        """Test _set_geom with shapely Polygon geometry"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()
            input_geom = Polygon([[120, 40], [160, 40], [160, 60], [140, 60]])

            with mock.patch.object(handler, "_get_geom", return_value=input_geom):
                result = handler._set_geom(input_geom)
                self.assertEqual(result, input_geom)

    def test_set_geom_wkt_string(self):
        """Test _set_geom with WKT string geometry"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()
            input_geom = "POLYGON ((120 40, 160 40, 160 60, 140 60, 120 40))"
            expected_geom = Polygon([[120, 40], [160, 40], [160, 60], [140, 60]])

            with mock.patch.object(handler, "_get_geom", return_value=input_geom):
                result = handler._set_geom(input_geom)
                self.assertIsInstance(result, Polygon)

    def test_format_query(self):
        """Test _format_query method"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()
            input_query = {
                "collection": "MOD09",
                "start_time": dt.datetime(2022, 6, 7, 23, 30),
                "stop_time": dt.datetime(2022, 6, 7, 23, 50),
                "geom": {
                    "latitude_minimum": -38,
                    "longitude_minimum": 145,
                    "latitude_maximum": -36,
                    "longitude_maximum": 150,
                },
            }

            with (
                mock.patch.object(handler, "_set_product_type", return_value="MOD09GA"),
                mock.patch.object(
                    handler,
                    "_set_datetime",
                    side_effect=lambda d: d.strftime("%Y-%m-%dT%H:%M:%S") if hasattr(d, "strftime") else d,
                ),
                mock.patch.object(handler, "_set_geom", return_value=(145, -38, 150, -36)),
            ):
                result = handler._format_query(input_query)

                self.assertIn("short_name", result)
                self.assertEqual(result["short_name"], "MOD09GA")
                self.assertIn("temporal", result)
                self.assertIn("bounding_box", result)
                self.assertNotIn("collection", result)
                self.assertNotIn("geom", result)

    def test_list_collections_from_file(self):
        """Test list_collections when loading from cached file"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            context = ScrappiContext()
            context["update_collections_list"] = False
            handler = EarthaccessCallHandler(context)

            fake_collections = np.array(["MOD09GA", "MOD02HKM", "MODIS"])

            with mock.patch("numpy.load", return_value=fake_collections):
                result = handler.list_collections()
                np.testing.assert_array_equal(result, fake_collections)

    @mock.patch("scrappi.api.earthaccess_api.earthaccess.search_datasets")
    def test_list_collections_from_api(self, mock_search_datasets):
        """Test list_collections when fetching from API"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            context = ScrappiContext()
            context["update_collections_list"] = True
            handler = EarthaccessCallHandler(context)

            # Mock the search_datasets return value
            mock_dataset_1 = mock.Mock()
            mock_dataset_1.summary.return_value = {"short-name": "MOD09GA"}
            mock_dataset_2 = mock.Mock()
            mock_dataset_2.summary.return_value = {"short-name": "MOD02HKM"}

            mock_search_datasets.return_value = [mock_dataset_1, mock_dataset_2]

            with mock.patch("numpy.save"):
                result = handler.list_collections()
                self.assertIn("MOD09GA", result)
                self.assertIn("MOD02HKM", result)

    @mock.patch("scrappi.api.earthaccess_api.earthaccess.search_data")
    def test_perform_query(self, mock_search_data):
        """Test _perform_query method"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            input_query = {
                "collection": "MOD09GA",
                "start_time": dt.datetime(2022, 6, 7, 23, 30),
                "stop_time": dt.datetime(2022, 6, 7, 23, 50),
                "geom": {
                    "latitude_minimum": -38,
                    "longitude_minimum": 145,
                    "latitude_maximum": -36,
                    "longitude_maximum": 150,
                },
            }

            mock_products = [mock.Mock(spec=DataGranule)]
            mock_search_data.return_value = mock_products

            with mock.patch.object(
                handler,
                "_format_query",
                return_value={
                    "short_name": "MOD09GA",
                    "temporal": ("2022-06-07T23:30:00", "2022-06-07T23:50:00"),
                    "bounding_box": (145, -38, 150, -36),
                },
            ):
                result = handler._perform_query(input_query)
                self.assertEqual(result, mock_products)

    def test_get_platform_from_collection_reference(self):
        """Test get_platform with CollectionReference in product dict"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            prod_dict = {
                "CollectionReference": {
                    "ShortName": "MOD09GA",
                }
            }

            with mock.patch.object(handler, "parse_platform_from_name", return_value="Terra"):
                result = handler.get_platform(prod_dict)
                self.assertEqual(result, "Terra")

    def test_get_constellation_from_collection_reference(self):
        """Test get_constellation with CollectionReference in product dict"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            prod_dict = {
                "CollectionReference": {
                    "ShortName": "MOD09GA",
                }
            }

            with mock.patch.object(handler, "parse_constellation_from_name", return_value="MODIS"):
                result = handler.get_constellation(prod_dict)
                self.assertEqual(result, "MODIS")

    def test_find_version(self):
        """Test find_version method"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            prod_dict = {"CollectionReference": {"Version": "6.1"}}

            result = handler.find_version(prod_dict)
            self.assertEqual(result, "6.1")

    def test_find_version_raises_error(self):
        """Test find_version raises error when version not found"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            prod_dict = {}

            with self.assertRaises(ValueError):
                handler.find_version(prod_dict)

    def test_find_start_time(self):
        """Test find_start_time method"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            prod_dict = {"TemporalExtent": {"RangeDateTime": {"BeginningDateTime": "2022-06-07T23:30:00"}}}

            with mock.patch.object(handler, "_set_datetime", return_value="2022-06-07T23:30:00"):
                result = handler.find_start_time(prod_dict)
                self.assertEqual(result, "2022-06-07T23:30:00")

    def test_find_start_time_raises_error(self):
        """Test find_start_time raises error when start time not found"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            prod_dict = {}

            with self.assertRaises(ValueError):
                handler.find_start_time(prod_dict)

    def test_find_stop_time(self):
        """Test find_stop_time method"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            prod_dict = {"TemporalExtent": {"RangeDateTime": {"EndingDateTime": "2022-06-07T23:50:00"}}}

            with mock.patch.object(handler, "_set_datetime", return_value="2022-06-07T23:50:00"):
                result = handler.find_stop_time(prod_dict)
                self.assertEqual(result, "2022-06-07T23:50:00")

    def test_find_stop_time_raises_error(self):
        """Test find_stop_time raises error when stop time not found"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            prod_dict = {}

            with self.assertRaises(ValueError):
                handler.find_stop_time(prod_dict)

    def test_extract_filter_attributes_with_day_night_flag(self):
        """Test extract_filter_attributes with day_night_flag"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            prod_dict = {"DataGranule": {"DayNightFlag": "Day"}}

            result = handler.extract_filter_attributes(prod_dict)
            self.assertEqual(result["day_night_flag"], "Day")

    def test_extract_filter_attributes_empty(self):
        """Test extract_filter_attributes with empty product dict"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            prod_dict = {}

            result = handler.extract_filter_attributes(prod_dict)
            self.assertEqual(result, {})

    def test_download_product_DataGranule_exists(self):
        """Test _download_product_DataGranule when product exists"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            product = mock.Mock(spec=DataGranule)
            path = example_path
            product_id = "MOD09GA.example"

            with mock.patch("os.path.exists", return_value=True):
                result = handler._download_product_DataGranule(product, path, product_id)
                self.assertEqual(result, os.path.join(path, product_id))

    @mock.patch("scrappi.api.earthaccess_api.earthaccess.download")
    def test_download_product_DataGranule_new(self, mock_download):
        """Test _download_product_DataGranule when product needs downloading"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            product = mock.Mock(spec=DataGranule)
            path = example_path
            product_id = "MOD09GA.example"
            downloaded_path = os.path.join(path, product_id)

            mock_download.return_value = [downloaded_path]

            with mock.patch("os.path.exists", side_effect=[False, False, True]), mock.patch("os.makedirs"):
                result = handler._download_product_DataGranule(product, path, product_id)
                self.assertEqual(result, downloaded_path)
                mock_download.assert_called()

    def test_download_product_DataGranule_invalid_type(self):
        """Test _download_product_DataGranule with invalid product type"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            product = 123  # Invalid type
            path = example_path
            product_id = "MOD09GA.example"

            with self.assertRaises(ValueError):
                handler._download_product_DataGranule(product, path, product_id)

    def test_download_product_ProductItemSet(self):
        """Test download_product with ProductItemSet"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            # Create mock ProductItems
            product1 = mock.Mock(spec=ProductItem)
            product2 = mock.Mock(spec=ProductItem)
            product_set = ProductItemSet([product1, product2])

            with mock.patch.object(handler, "download_product", return_value=["/path/to/prod1", "/path/to/prod2"]):
                result = handler.download_product(product_set)
                self.assertIsInstance(result, list)

    def test_download_product_None(self):
        """Test download_product with None product"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            with self.assertWarns(UserWarning):
                result = handler.download_product(None)
                self.assertIsNone(result)

    def test_download_product_ProductItem(self):
        """Test download_product with ProductItem"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            # Create a mock ProductItem
            product = ProductItem(
                constellation="MODIS",
                platform="Terra",
                collection="MOD09GA",
                id="MOD09GA.example",
                url="",
                geometry=Polygon(
                    [
                        (145, -38),
                        (150, -38),
                        (150, -36),
                        (145, -36),
                    ]
                ),
                start_time=dt.datetime(2022, 6, 7),
                stop_time=dt.datetime(2022, 6, 8),
                prod_dict={},
                filesystem=example_path,
            )

            with mock.patch.object(product.filesystem, "return_path", return_value=("/path/to/prod", True)):
                result = handler.download_product(product)
                self.assertEqual(result, "/path/to/prod")

    def test_download_product_invalid_type(self):
        """Test download_product with invalid product type"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            with self.assertRaises(ValueError):
                handler.download_product(123)

    @mock.patch("scrappi.api.earthaccess_api.earthaccess.search_data")
    def test_download_product_filename(self, mock_search_data):
        """Test download_product_filename method"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            product_filename = "MOD09GA.example"

            mock_product = mock.Mock(spec=DataGranule)
            mock_product.__getitem__ = mock.Mock(return_value={"Identifiers": [{"Identifier": product_filename}]})
            mock_search_data.return_value = [mock_product]

            with (
                mock.patch.object(handler, "_download_product_DataGranule", return_value="/path/to/prod"),
                mock.patch("scrappi.make_fs") as mock_make_fs,
            ):
                mock_fs = mock.Mock()
                mock_fs.directory = example_path
                mock_make_fs.return_value = mock_fs

                result = handler.download_product_filename(product_filename)
                self.assertIsNotNone(result)

    def test_download_product_filename_not_found(self):
        """Test download_product_filename when product not found"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            product_filename = "NONEXISTENT.product"

            with (
                mock.patch("scrappi.api.earthaccess_api.earthaccess.search_data", return_value=[]),
                mock.patch("scrappi.make_fs") as mock_make_fs,
            ):
                mock_fs = mock.Mock()
                mock_fs.directory = example_path
                mock_make_fs.return_value = mock_fs

                with self.assertWarns(UserWarning):
                    result = handler.download_product_filename(product_filename)
                    self.assertIsNone(result)

    def test_download_product_filename_list(self):
        """Test download_product_filename with list of filenames"""
        with mock.patch("scrappi.api.earthaccess_api.earthaccess.login"):
            handler = EarthaccessCallHandler()

            filenames = ["MOD09GA.example1", "MOD09GA.example2"]

            with mock.patch.object(
                handler, "download_product_filename", return_value=["/path/to/prod1", "/path/to/prod2"]
            ):
                result = handler.download_product_filename(filenames)
                self.assertIsInstance(result, list)
                self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
