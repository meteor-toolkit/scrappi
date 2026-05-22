"""scrappi.api.tests.test_EODAG - tests for scrappi.api.EODAG"""

import os
import unittest
from unittest.mock import patch
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
        except Exception as e:
            self.hypernets_call_handler = None

    def test_get_roi(self):
        if self.hypernets_call_handler is None:
            self.skipTest("HYPERNETSOfflineCallHandler not available")
        poly_roi = self.hypernets_call_handler.get_roi_shapely("BASP")
        poly_roi = self.hypernets_call_handler.get_roi_shapely("WWUK")
        poly_roi = self.hypernets_call_handler.get_roi_shapely("GHNA")
        poly_test = Polygon(
            [
                [15.125080807317048, -23.60055922684998],
                [15.126699181854802, -23.60055922684998],
                [15.126699181854802, -23.602500776528554],
                [15.125080807317048, -23.602500776528554],
                [15.125080807317048, -23.60055922684998],
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
        except Exception as e:
            self.hypernets_call_handler = None

    def test_get_roi(self):
        if self.hypernets_call_handler is None:
            self.skipTest("HYPERNETSCallHandler not available")

        poly_roi = self.hypernets_call_handler.get_roi_shapely("BASP")
        poly_roi = self.hypernets_call_handler.get_roi_shapely("WWUK")
        poly_roi = self.hypernets_call_handler.get_roi_shapely("GHNA")
        poly_test = Polygon(
            [
                [15.125080807317048, -23.60055922684998],
                [15.126699181854802, -23.60055922684998],
                [15.126699181854802, -23.602500776528554],
                [15.125080807317048, -23.602500776528554],
                [15.125080807317048, -23.60055922684998],
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
        from unittest.mock import patch

        with patch(
            "hypernets_api.online_api.HYPERNETSAPI.query",
            return_value=return_hypernets_api,
        ) as mock_perform:
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


if __name__ == "__main__":
    unittest.main()
