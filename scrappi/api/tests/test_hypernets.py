"""scrappi.api.tests.test_EODAG - tests for scrappi.api.EODAG"""

import os
import sys
import types
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from scrappi.api.hypernets import HYPERNETSOfflineCallHandler, HYPERNETSCallHandler
from scrappi import ScrappiContext
from shapely.geometry import Polygon
from pathlib import Path

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk>",
]

example_download_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "examples",
    "downloaded_data",
)

return_hypernets_api = {
    "context": {"limit": 100, "returned": 4},
    "features": [
        {
            "assets": {
                "data": {
                    "href": "http://landhypernet.org.uk/downloads/GHNA/2023/10/31/SEQ20231031T093131/HYPERNETS_L_GHNA_L2A_REF_20231031T0931_20240125T2037_v2.0.nc",
                    "roles": [...],
                    "title": "HYPERNETS_L_GHNA_L2A_REF_20231031T0931_20240125T2037_v2.0 NetCDF file",
                    "type": "application/netcdf",
                }
            },
            "bbox": [...],
            "collection": "L2A_REF",
            "description": "L2A Surface Reflectance (HCRF) product for sequence SEQ20231031T093131 at site GHNA",
            "geometry": {...},
            "id": "GHNA_SEQ20231031T093131_L2A_REF",
            "links": [...],
            "properties": {
                "datetime": "2023-10-31 09:34:09.000000T00:00:00Z",
                "end_datetime": "2023-10-31 09:41:59.000000T00:00:00Z",
                "eo:bands": [{...}, {...}],
                "latitude": -23.60153,
                "longitude": 15.12589,
                "measurand": "Surface Reflectance (HCRF)",
                "product_level": "L2A_REF",
                "proj:epsg": 4326,
                "sequence_name": "SEQ20231031T093131",
                "site_id": "GHNA",
                "start_datetime": "2023-10-31 09:34:09.000000T00:00:00Z",
            },
            "stac_extensions": [...],
            "stac_version": "1.0.0",
            "type": "Feature",
        },
    ],
    "type": "FeatureCollection",
}


class TestOfflineHYPERNETSCallHandler(unittest.TestCase):
    def setUp(self):
        try:
            self.hypernets_call_handler = HYPERNETSOfflineCallHandler(
                archive_path=os.path.join(os.path.dirname(__file__), "archive.db")
            )
        except Exception:
            self.hypernets_call_handler = None

    def test_get_roi(self):
        if self.hypernets_call_handler is None:
            self.skipTest("HYPERNETSOfflineCallHandler not available")
        poly_roi = self.hypernets_call_handler.get_roi_shapely("BASP")
        poly_roi = self.hypernets_call_handler.get_roi_shapely("WWUK")
        poly_roi = self.hypernets_call_handler.get_roi_shapely("GHNA")
        # GHNA's ROI is generated via generate_bounding_lat_lon, whose default
        # local Azimuthal Equidistant projection produces a true 200m x 200m
        # square (verified geodesically) -- these coordinates differ from
        # values computed under the old fixed-CRS (EPSG:32630) default by
        # ~17m/~207m, not a rounding difference; see that function's docstring.
        poly_test = Polygon(
            [
                [15.124910202637997, -23.60243291100309],
                [15.1268697839455, -23.60243291100309],
                [15.1268697839455, -23.600627082710055],
                [15.124910202637997, -23.600627082710055],
                [15.124910202637997, -23.60243291100309],
            ]
        )
        assert poly_roi.equals(poly_test)
        poly_roi = self.hypernets_call_handler.get_roi_shapely("PEAN")
        poly_test = Polygon(
            [
                [23.3038867960562, -71.93894657967229],
                [23.30663303562398, -71.93894657967229],
                [23.30663303562398, -71.94130941393267],
                [23.3038867960562, -71.94130941393267],
                [23.3038867960562, -71.93894657967229],
            ]
        )
        assert poly_roi.equals(poly_test)

    def test_perform_query(self):
        if self.hypernets_call_handler is None:
            self.skipTest("HYPERNETSOfflineCallHandler not available")
        query = {
            "collection": "L2A_REF",
            "site": "GHNA",
            "start_time": "2023-10-31T08:00:00",
            "stop_time": "2023-11-02T08:00:00",
        }

        products = self.hypernets_call_handler.perform_query(query)
        path = products.get_path()
        expected_path = (
            Path(__file__).parent
            / "GHNA"
            / "2023"
            / "10"
            / "31"
            / "SEQ20231031T093131"
            / "HYPERNETS_L_GHNA_L2A_REF_20231031T0931_20240410T1602_v2.0.nc"
        )

        assert len(path) == 2
        assert Path(path[0]) == expected_path


class TestHYPERNETSCallHandler(unittest.TestCase):
    def setUp(self):
        context = ScrappiContext()
        context["fs"]["path"] = example_download_path
        try:
            self.hypernets_call_handler = HYPERNETSCallHandler(context)
        except Exception:
            self.hypernets_call_handler = None

    def test_get_roi(self):
        if self.hypernets_call_handler is None:
            self.skipTest("HYPERNETSCallHandler not available")

        poly_roi = self.hypernets_call_handler.get_roi_shapely("BASP")
        poly_roi = self.hypernets_call_handler.get_roi_shapely("WWUK")
        poly_roi = self.hypernets_call_handler.get_roi_shapely("GHNA")
        # GHNA's ROI is generated via generate_bounding_lat_lon, whose default
        # local Azimuthal Equidistant projection produces a true 200m x 200m
        # square (verified geodesically) -- these coordinates differ from
        # values computed under the old fixed-CRS (EPSG:32630) default by
        # ~17m/~207m, not a rounding difference; see that function's docstring.
        poly_test = Polygon(
            [
                [15.124910202637997, -23.60243291100309],
                [15.1268697839455, -23.60243291100309],
                [15.1268697839455, -23.600627082710055],
                [15.124910202637997, -23.600627082710055],
                [15.124910202637997, -23.60243291100309],
            ]
        )
        assert poly_roi.equals(poly_test)
        poly_roi = self.hypernets_call_handler.get_roi_shapely("PEAN")
        poly_test = Polygon(
            [
                [23.3038867960562, -71.93894657967229],
                [23.30663303562398, -71.93894657967229],
                [23.30663303562398, -71.94130941393267],
                [23.3038867960562, -71.94130941393267],
                [23.3038867960562, -71.93894657967229],
            ]
        )
        assert poly_roi.equals(poly_test)

    def test_perform_query(self):
        if self.hypernets_call_handler is None:
            self.skipTest("HYPERNETSCallHandler not available")

        query = {
            "collection": "LHYP_L2A_REF",
            "site": "GHNA",
            "start_time": "2023-10-31T08:00:00",
            "stop_time": "2023-10-31T10:00:00",
        }

        # apply mocking only after skipping check to avoid importing optional
        # `hypernets_api` at module load time on environments where it's absent

        with patch(
            "hypernets_api.online_api.HYPERNETSAPI.query",
            return_value=return_hypernets_api,
        ) as _mock_perform:
            products = self.hypernets_call_handler.perform_query(query)
            path = products.get_path()
            expected_path = os.path.join(
                example_download_path,
                "data",
                "HYPERNETS",
                "GHNA",
                "LHYP_L2A_REF",
                "2023",
                "10",
                "31",
                "HYPERNETS_L_GHNA_L2A_REF_20231031T0931_20240125T2037_v2.0.nc",
            )

            assert len(path) == 1
            assert Path(path[0]) == Path(expected_path)


class TestOfflineHYPERNETSCallHandlerRegression(unittest.TestCase):
    """Regression coverage for HYPERNETSOfflineCallHandler that doesn't need the
    real (private, GitLab-hosted) hypernets_api package installed -- a fake module
    is injected into sys.modules for each test, exercising the same __init__ /
    perform_query code paths a real install would."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.archive_path = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

        fake_module = types.ModuleType("hypernets_api")
        self.fake_api = MagicMock()
        self.fake_api.archive_path = self.archive_path
        fake_module.OfflineHYPERNETSAPI = MagicMock(return_value=self.fake_api)
        modules_patcher = patch.dict(sys.modules, {"hypernets_api": fake_module})
        modules_patcher.start()
        self.addCleanup(modules_patcher.stop)

    def _write(self, *path_parts):
        """Create an empty file at os.path.join(self.archive_path, *path_parts),
        creating any intermediate directories -- content is irrelevant, perform_query
        only inspects the filename."""
        full_path = os.path.join(self.archive_path, *path_parts)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w"):
            pass
        return full_path

    def test_offline_product_can_be_converted_to_a_stac_item(self):
        """Regression test: adding an offline-archive HYPERNETS matchup to a
        catalogue calls ProductItem.to_stac_item(), which needs the product's
        filesystem to expose return_stac_item_path (a STACFileSystem method).
        perform_query used to give each product a plain LocalFileSystem, which
        raised AttributeError -- see the identical fix for
        RadcalnetOfflineCallHandler."""
        rel_dir = os.path.join("GHNA", "2023", "10", "31", "SEQ20231031T093131")
        product_name = "HYPERNETS_L_GHNA_L2A_REF_20231031T0931_20240125T2037_v2.0"
        file_path = self._write(rel_dir, product_name + ".nc")

        handler = HYPERNETSOfflineCallHandler(archive_path=self.archive_path)
        self.fake_api.query.return_value = [
            {
                "site_id": "GHNA",
                "product_name": product_name,
                "rel_product_dir": rel_dir,
                "datetime_start": "2023-10-31T09:34:09",
                "datetime_end": "2023-10-31T09:41:59",
                "sequence_name": "SEQ20231031T093131",
            }
        ]

        products = handler.perform_query(
            {
                "collection": "L2A_REF",
                "site": "GHNA",
                "start_time": "2023-10-31T08:00:00",
                "stop_time": "2023-11-02T08:00:00",
            }
        )
        self.assertEqual(len(products), 1)

        item = products[0].to_stac_item()

        self.assertEqual(item.id, product_name + ".nc")
        # the on-disk file still resolves for a (networkless) download
        self.assertEqual(os.path.normpath(products[0].get_path()), os.path.normpath(file_path))
        # the archive isn't ours to write to
        self.assertTrue(products[0].filesystem.read_only)


if __name__ == "__main__":
    unittest.main()
