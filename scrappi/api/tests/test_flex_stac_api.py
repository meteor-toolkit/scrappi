"""scrappi.api.tests.test_flex_stac_api - tests for scrappi.api.flex_stac_api"""

import unittest
from unittest import mock

from scrappi import ScrappiContext
from scrappi.api.flex_stac_api import FLEXSTACAPICallHandler
from scrappi.product import ProductItemSet

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk>",
]


class TestFLEXSTACAPICallHandler(unittest.TestCase):
    """Test suite for FLEXSTACAPICallHandler class"""

    def setUp(self):
        """Set up test fixtures."""
        self.context = ScrappiContext()
        self.context["flex_stac"] = {
            "cp_stac_endpoint": "https://discover.flex.example.com/",
            "keycloak_base_url": "https://auth.flex.example.com/",
            "realm": "Collaborative-Platform",
            "max_query_results": 7,
        }
        self.handler = FLEXSTACAPICallHandler(context=self.context)

    def test_list_collections(self):
        """Test list_collections returns the supported FLEX collection names."""
        self.assertEqual(self.handler.list_collections(), ["FLEX_L2", "FLEX_L1"])

    @mock.patch("scrappi.api.flex_stac_api.requests.post")
    def test_query_stac_builds_expected_request_payload(self, mock_post):
        """Test _query_stac maps the requested collection and query filters."""
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        self.handler._query_stac({
            "collection": "FLEX_L2",
            "start_time": "2024-01-01T00:00:00Z",
            "stop_time": "2024-01-02T00:00:00Z",
        })

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]

        self.assertEqual(payload["collections"], ["L2A_AtmCorr_DATA"])
        self.assertEqual(payload["limit"], 7)
        self.assertEqual(payload["datetime"], "2024-01-01T00:00:00Z/2024-01-02T00:00:00Z")
        self.assertIsNone(payload["intersects"])
        mock_response.raise_for_status.assert_called_once()

    @mock.patch("scrappi.api.flex_stac_api.product_item_from_stac")
    @mock.patch.object(FLEXSTACAPICallHandler, "authenticate")
    def test_perform_query_returns_product_item_set(self, mock_authenticate, mock_product_item_from_stac):
        """Test perform_query authenticates and converts STAC features into product items."""
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            "features": [
                {
                    "id": "item-1",
                    "collection": "FLEX_L2",
                    "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                    "properties": {"datetime": "2024-01-01T00:00:00Z"},
                }
            ]
        }

        item = mock.Mock()
        item.api = self.handler
        mock_product_item_from_stac.return_value = item

        with mock.patch.object(self.handler, "_query_stac", return_value=mock_response):
            results = self.handler.perform_query({"collection": "FLEX_L2"})

        self.assertIsInstance(results, ProductItemSet)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].api, self.handler)
        mock_authenticate.assert_called_once()
        mock_product_item_from_stac.assert_called_once()

    def test_get_netcdf_asset_href_prefers_netcdf_media_type(self):
        """Test NetCDF asset lookup prefers media-type detection before filename fallback."""
        item = {
            "id": "sample-item",
            "assets": {
                "aux": {"href": "https://example.com/aux.txt", "type": "text/plain"},
                "data": {"href": "https://example.com/data.nc", "type": "application/netcdf"},
            },
        }

        self.assertEqual(self.handler.get_netcdf_asset_href(item), "https://example.com/data.nc")

    def test_get_netcdf_asset_href_raises_when_missing(self):
        """Test missing NetCDF asset raises a ValueError."""
        item = {
            "id": "sample-item",
            "assets": {
                "aux": {"href": "https://example.com/aux.txt", "type": "text/plain"},
            },
        }

        with self.assertRaises(ValueError):
            self.handler.get_netcdf_asset_href(item)

    def test_get_download_url_for_product_id(self):
        """Test product IDs resolve to the expected download endpoint."""
        url = self.handler.getDownloadURL("S2A_TEST_PRODUCT")
        self.assertEqual(url, "https://download.flex.pal.maap.eo.esa.int/flex/collections/sentinel-2-l2a-cog/items/S2A_TEST_PRODUCT")

    def test_get_download_url_for_item_url(self):
        """Test item URLs are preserved when already fully qualified."""
        item_url = "https://discover.flex.example.com/collections/FLEX_L2/items/item-42"
        url = self.handler.getDownloadURL(item_url)
        self.assertEqual(url, "https://download.flex.pal.maap.eo.esa.int/flex/collections/FLEX_L2/items/item-42")

    def test_get_download_url_raises_for_unknown_product_prefix(self):
        """Test unsupported product prefixes raise a ValueError."""
        with self.assertRaises(ValueError):
            self.handler.getDownloadURL("UNKNOWN_PRODUCT")

    @mock.patch("scrappi.api.flex_stac_api.httpx.get")
    def test_download_signed_item_flex_downloads_redirected_assets(self, mock_httpx_get):
        """Test signed asset downloads write each redirected file to disk."""
        mock_item = mock.Mock()
        mock_item.get_assets.return_value = {"data": object()}

        redirect_response = mock.Mock()
        redirect_response.status_code = 302
        redirect_response.headers = {"Location": "https://example.com/downloads/data.nc?token=abc"}

        file_response = mock.Mock()
        file_response.status_code = 200
        file_response.content = b"payload"

        mock_httpx_get.side_effect = [redirect_response, file_response]

        target_dir = self.context["fs"]["path"] if isinstance(self.context["fs"], dict) else None
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            paths = self.handler.downloadSignedItem_FLEX(mock_item, tmp_path, "https://example.com/base", {"Authorization": "Bearer token"})

            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].name, "data.nc")
            self.assertEqual(paths[0].read_bytes(), b"payload")

    @mock.patch("scrappi.api.flex_stac_api.httpx.get")
    def test_download_signed_item_flex_raises_when_requested(self, mock_httpx_get):
        """Test raise_on_error triggers a RuntimeError on non-redirect responses."""
        mock_item = mock.Mock()
        mock_item.get_assets.return_value = {"data": object()}

        response = mock.Mock()
        response.status_code = 500
        response.text = "server error"
        mock_httpx_get.return_value = response

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(RuntimeError):
                self.handler.downloadSignedItem_FLEX(
                    mock_item,
                    Path(tmpdir),
                    "https://example.com/base",
                    {"Authorization": "Bearer token"},
                    raise_on_error=True,
                )

    def test_get_netcdf_asset_href_falls_back_to_common_names(self):
        """Test the common asset-name fallback is used when no media type is present."""
        item = {"id": "sample-item", "assets": {"product": {"href": "https://example.com/product.nc"}}}
        self.assertEqual(self.handler.get_netcdf_asset_href(item), "https://example.com/product.nc")


if __name__ == "__main__":
    unittest.main()
