"""scrappi.api.tests.test_eumdac - tests for scrappi.api.eumdac"""

import os
import unittest
import datetime as dt
from unittest import mock

from shapely.geometry import Polygon, MultiPolygon

from scrappi.api.eumdac import EUMDACCallHandler
from scrappi.product import ProductItem, ProductItemSet
from scrappi import ScrappiContext


__author__ = [
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
]

example_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "examples",
)


class TestEUMDACCallHandler(unittest.TestCase):
    """Test suite for EUMDACCallHandler class"""

    def setUp(self):
        """Set up test fixtures"""
        self.access_token_patcher = mock.patch("scrappi.api.eumdac.eumdac.AccessToken", return_value=mock.Mock())
        self.data_store_patcher = mock.patch("scrappi.api.eumdac.eumdac.DataStore", return_value=mock.Mock())
        self.access_token_patcher.start()
        self.data_store_patcher.start()
        self.addCleanup(self.access_token_patcher.stop)
        self.addCleanup(self.data_store_patcher.stop)

        self.context = ScrappiContext()
        self.context["eumdac"] = {"credentials": {"key": "key", "secret": "secret"}}
        self.handler = EUMDACCallHandler(self.context)

    def test_set_product_type(self):
        """Test _set_product_type method"""
        with mock.patch.object(self.handler, "_get_product_type", return_value="EO:EUM:DAT:TEST") as mock_get_product:
            result = self.handler._set_product_type("TEST")
            self.assertEqual(result, "EO:EUM:DAT:TEST")
            mock_get_product.assert_called_with("TEST")

    def test_set_datetime_with_string(self):
        """Test _set_datetime with string input"""
        with mock.patch.object(self.handler, "_get_datetime", return_value=dt.datetime(2022, 6, 7, 23, 30)):
            result = self.handler._set_datetime("2022-06-07T23:30:00")
            self.assertEqual(result, dt.datetime(2022, 6, 7, 23, 30))

    def test_set_datetime_with_datetime_object(self):
        """Test _set_datetime with datetime object input"""
        input_dt = dt.datetime(2022, 6, 7, 23, 30)
        with mock.patch.object(self.handler, "_get_datetime", return_value=input_dt):
            result = self.handler._set_datetime(input_dt)
            self.assertEqual(result, input_dt)

    def test_set_geom_dict(self):
        """Test _set_geom with dictionary geometry"""
        input_geom = {
            "latitude_minimum": 40,
            "longitude_minimum": 120,
            "latitude_maximum": 60,
            "longitude_maximum": 160,
        }
        expected_output = "120, 40, 160, 60"

        with mock.patch.object(self.handler, "_get_geom", return_value=input_geom):
            result = self.handler._set_geom(input_geom)
            self.assertEqual(result, expected_output)

    def test_set_geom_shapely_polygon(self):
        """Test _set_geom with shapely Polygon geometry"""
        input_geom = Polygon([[120, 40], [160, 40], [160, 60], [140, 60]])

        with mock.patch.object(self.handler, "_get_geom", return_value=input_geom):
            result = self.handler._set_geom(input_geom)
            self.assertEqual(result, input_geom)

    def test_set_geom_wkt_string(self):
        """Test _set_geom with WKT string geometry"""
        input_geom = "POLYGON ((120 40, 160 40, 160 60, 140 60, 120 40))"

        with mock.patch.object(self.handler, "_get_geom", return_value=input_geom):
            result = self.handler._set_geom(input_geom)
            self.assertIsInstance(result, Polygon)

    def test_format_query(self):
        """Test _format_query method"""
        input_query = {
            "collection": "EO:EUM:DAT:TEST",
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
            mock.patch.object(self.handler, "_set_product_type", return_value="EO:EUM:DAT:TEST"),
            mock.patch.object(
                self.handler,
                "_set_datetime",
                side_effect=lambda d: d.strftime("%Y-%m-%dT%H:%M:%S") if hasattr(d, "strftime") else d,
            ),
            mock.patch.object(self.handler, "_set_geom", return_value="145, -38, 150, -36"),
        ):
            result = self.handler._format_query(input_query)

            self.assertIn("selected_collection", result)
            self.assertEqual(result["selected_collection"], "EO:EUM:DAT:TEST")
            self.assertIn("dtstart", result)
            self.assertIn("dtend", result)
            self.assertIn("bbox", result)
            self.assertNotIn("collection", result)
            self.assertNotIn("geom", result)

    def test_list_collections(self):
        """Test list_collections method"""
        self.handler.api.collections = [mock.Mock(_id="COLL_A"), mock.Mock(_id="COLL_B")]

        result = self.handler.list_collections()

        self.assertEqual(result, ["COLL_A", "COLL_B"])

    def test_perform_query_internal(self):
        """Test _perform_query method"""
        input_query = {
            "collection": "EO:EUM:DAT:TEST",
            "start_time": dt.datetime(2022, 6, 7, 23, 30),
            "stop_time": dt.datetime(2022, 6, 7, 23, 50),
            "geom": {
                "latitude_minimum": -38,
                "longitude_minimum": 145,
                "latitude_maximum": -36,
                "longitude_maximum": 150,
            },
        }

        mock_product = mock.Mock()
        mock_collection = mock.Mock()
        mock_collection.search.return_value = [mock_product]
        self.handler.api.get_collection.return_value = mock_collection

        with mock.patch.object(
            self.handler,
            "_format_query",
            return_value={
                "selected_collection": "EO:EUM:DAT:TEST",
                "dtstart": "2022-06-07T23:30:00",
                "dtend": "2022-06-07T23:50:00",
                "bbox": "145, -38, 150, -36",
            },
        ):
            result = self.handler._perform_query(input_query)

            self.assertEqual(result, [mock_product])
            self.handler.api.get_collection.assert_called_with("EO:EUM:DAT:TEST")

    def test_perform_query(self):
        """Test perform_query builds ProductItemSet from query results"""
        mock_product = mock.Mock()
        mock_product._browse_properties = {
            "identifier": "prod-1",
            "links": {"data": [{"href": "https://example.com/data"}]},
            "acquisitionInformation": [{"platform": {"platformShortName": "Metop-B"}}],
            "productInformation": {"productVersion": "1.0"},
            "date": "2022-06-07T23:30:00Z/2022-06-07T23:50:00Z",
        }
        mock_product._geometry = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        mock_product.collection = "EO:EUM:DAT:TEST"

        with (
            mock.patch.object(self.handler, "_perform_query", return_value=[mock_product]),
            mock.patch.object(self.handler, "convert_geom", return_value=mock_product._geometry),
            mock.patch.object(self.handler, "get_platform", return_value="Metop-B"),
            mock.patch.object(self.handler, "get_constellation", return_value="Metop"),
            mock.patch.object(self.handler, "find_start_time", return_value=dt.datetime(2022, 6, 7, 23, 30)),
            mock.patch.object(self.handler, "find_stop_time", return_value=dt.datetime(2022, 6, 7, 23, 50)),
            mock.patch.object(self.handler, "find_version", return_value="1.0"),
        ):
            result = self.handler.perform_query({"collection": "EO:EUM:DAT:TEST"})

            self.assertIsInstance(result, ProductItemSet)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].id, "prod-1")
            self.assertEqual(result[0].collection, "EO:EUM:DAT:TEST")

    def test_convert_geom(self):
        """Test convert_geom with MultiPolygon geometry"""
        geometry = MultiPolygon([Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])])
        output = self.handler.convert_geom(geometry)
        self.assertIsInstance(output, Polygon)

    def test_get_platform(self):
        """Test get_platform method"""
        prod_dict = {"acquisitionInformation": [{"platform": {"platformShortName": "Metop-B"}}]}
        self.assertEqual(self.handler.get_platform(prod_dict), "Metop-B")

    def test_get_constellation(self):
        """Test get_constellation method"""
        prod_dict = {"acquisitionInformation": [{"platform": {"platformShortName": "Metop-B"}}]}
        with mock.patch.object(self.handler, "parse_constellation_from_name", return_value="Metop"):
            self.assertEqual(self.handler.get_constellation(prod_dict), "Metop")

    def test_find_version(self):
        """Test find_version method"""
        prod_dict = {"productInformation": {"productVersion": "1.0"}}
        self.assertEqual(self.handler.find_version(prod_dict), "1.0")

    def test_find_start_time(self):
        """Test find_start_time method"""
        prod_dict = {"date": "2022-06-07T23:30:00Z/2022-06-07T23:50:00Z"}
        result = self.handler.find_start_time(prod_dict)
        self.assertEqual(result, dt.datetime(2022, 6, 7, 23, 30, tzinfo=dt.timezone.utc))

    def test_find_stop_time(self):
        """Test find_stop_time method"""
        prod_dict = {"date": "2022-06-07T23:30:00Z/2022-06-07T23:50:00Z"}
        result = self.handler.find_stop_time(prod_dict)
        self.assertEqual(result, dt.datetime(2022, 6, 7, 23, 50, tzinfo=dt.timezone.utc))

    def test_extract_filter_attributes(self):
        """Test extract_filter_attributes method"""
        self.assertEqual(self.handler.extract_filter_attributes({}), {})

    def test_download_product_ProductItemSet(self):
        """Test download_product with ProductItemSet"""
        product1 = mock.Mock(spec=ProductItem)
        product2 = mock.Mock(spec=ProductItem)
        product_set = ProductItemSet([product1, product2])

        with mock.patch.object(self.handler, "download_product", return_value=["/path/to/prod1", "/path/to/prod2"]):
            result = self.handler.download_product(product_set)
            self.assertEqual(result, ["/path/to/prod1", "/path/to/prod2"])

    def test_download_product_None(self):
        """Test download_product with None product"""
        with self.assertWarns(UserWarning):
            result = self.handler.download_product(None)
            self.assertIsNone(result)

    def test_download_product_ProductItem(self):
        """Test download_product with ProductItem"""
        product = ProductItem(
            constellation="Metop",
            platform="Metop-B",
            collection="EO:EUM:DAT:TEST",
            id="prod-1",
            url="",
            geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            start_time=dt.datetime(2022, 6, 7),
            stop_time=dt.datetime(2022, 6, 8),
            prod_dict={"links": {"data": [{"href": "https://example.com/data"}]}},
            filesystem=example_path,
        )
        product.filesystem = product.set_fs(product.filesystem_init)  # ensure it's a LocalFileSystem, not None

        with (
            mock.patch.object(product.filesystem, "return_path", return_value=("/path/to/prod", True)),
            mock.patch.object(self.handler, "_download_product", return_value="/path/to/prod"),
        ):
            result = self.handler.download_product(product)
            self.assertEqual(result, "/path/to/prod")

    def test_download_product_invalid_type(self):
        """Test download_product with invalid product type"""
        with self.assertRaises(ValueError):
            self.handler.download_product(123)

    def test_download_product_filename(self):
        """Test download_product_filename with a filename"""
        with (
            mock.patch("scrappi.api.eumdac.eumdac.AccessToken", return_value=mock.Mock()),
            mock.patch("scrappi.api.eumdac.eumdac.DataStore", return_value=mock.Mock()),
            mock.patch("scrappi.make_fs") as mock_make_fs,
        ):
            mock_fs = mock.Mock()
            mock_fs.directory = example_path
            mock_make_fs.return_value = mock_fs

            mock_api = mock.Mock()
            self.handler.api = mock_api
            self.handler.api.get_product.return_value = [mock.Mock(_id="prod-1")]

            with mock.patch.object(self.handler, "_download_product", return_value="/path/to/prod"):
                result = self.handler.download_product_filename("prod-1", "EO:EUM:DAT:TEST", fs=mock_fs)
                self.assertEqual(result, "/path/to/prod")

    def test_download_product_filename_not_found(self):
        """Test download_product_filename when product not found"""
        self.handler.api.get_product.return_value = []

        with mock.patch("scrappi.make_fs") as mock_make_fs:
            mock_fs = mock.Mock()
            mock_fs.directory = example_path
            mock_make_fs.return_value = mock_fs

            with self.assertWarns(UserWarning):
                result = self.handler.download_product_filename("missing", "EO:EUM:DAT:TEST", fs=mock_fs)
                self.assertIsNone(result)

    def test_download_product_filename_list(self):
        """Test download_product_filename with a list of filenames"""
        with mock.patch.object(
            self.handler, "download_product_filename", return_value=["/path/to/prod1", "/path/to/prod2"]
        ):
            result = self.handler.download_product_filename(["prod-1", "prod-2"], "EO:EUM:DAT:TEST")
            self.assertEqual(result, ["/path/to/prod1", "/path/to/prod2"])


if __name__ == "__main__":
    unittest.main()
