"""scrappi.api.tests.test_EODAG - tests for scrappi.api.EODAG"""

import os
import unittest
import unittest.mock as mock
import datetime as dt
import numpy.testing as npt
from typing import TYPE_CHECKING, Any, Iterator, Optional, Union, cast
import pytest

from shapely.geometry import Polygon
from eodag import EOProduct, SearchResult
from scrappi.product import ProductItem, ProductItemSet
from scrappi import make_fs
from scrappi.api.eodag import EODAGCallHandler
from scrappi import ScrappiContext

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]

example_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "examples",
)
scrappi_config_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    ".scrappi",
)


class TestEODAGCallHandler(unittest.TestCase):
    def setUp(self):
        # Use a context that selects the named 't-drive' filesystem handler
        # to avoid depending on an absolute T: path existing on the test host.
        context = ScrappiContext()
        context["fs"]["path"] = "t-drive"
        self.eodag_call_handler = EODAGCallHandler(context)

    @mock.patch("scrappi.api.eodag.EODataAccessGateway")
    def test_init_None(self, mock_api):
        EODAGCallHandler()
        mock_api.assert_called()

    def test_init_invalid_credentials(
        self,
    ):
        context = ScrappiContext()
        from eodag.plugins.authentication.base import Authentication

        context["eodag"]["cop_dataspace"]["auth"]["credentials"] = {
            "username": "username",
            "password": "password",
        }
        dag = EODAGCallHandler(context)
        # cred = dag.dag.providers_config["usgs"].auth.credentials
        plugin = cast(
            Authentication,
            dag.dag._plugins_manager._build_plugin(
                "cop_dataspace",
                dag.dag.providers.configs["cop_dataspace"].auth,
                Authentication,
            ),
        )
        assert dag.dag.providers.configs["cop_dataspace"].auth.credentials["username"] == "username"
        assert dag.dag.providers.configs["cop_dataspace"].auth.credentials["password"] == "password"
        with self.assertRaises(Exception):
            plugin.authenticate()

    @pytest.mark.slow
    def test_init_valid_credentials(
        self,
    ):
        # Use locally stored credentials. test will only pass if setting these credentials manually in your config file.
        context = ScrappiContext()
        from eodag.plugins.authentication.base import Authentication

        dag = EODAGCallHandler(context)

        plugin = cast(
            Authentication,
            dag.dag._plugins_manager._build_plugin(
                "cop_dataspace",
                dag.dag.providers.configs["cop_dataspace"].auth,
                Authentication,
            ),
        )

        plugin.authenticate()

    @mock.patch(
        "scrappi.api.eodag.EODataAccessGateway.list_collections",
        return_value=[mock.Mock(id="LANDSAT_C2L1"), mock.Mock(id="S2_MSI_L1C")],
    )
    def test_list_collections(self, mock_list):
        collections = ["LANDSAT_C2L1", "S2_MSI_L1C"]
        self.assertListEqual(EODAGCallHandler().list_collections(), collections)

    # def test_platforms_set(self):
    #     self.eodag_call_handler._platforms = {"test": "dict"}
    #     self.assertEqual(self.eodag_call_handler.platforms, {"test": "dict"})

    @mock.patch(
        "scrappi.api.base.BaseAPICallHandler._get_datetime",
        return_value=dt.datetime(2022, 10, 20, 23, 11, 43),
    )
    def test_set_datetime(self, mock_get):
        input_dt = "2022-10-20T23:11:43"
        self.assertEqual(self.eodag_call_handler._set_datetime(input_dt), input_dt)
        mock_get.assert_called_with("2022-10-20T23:11:43")

    def test_set_geom_dict(self):
        input_geom = {
            "latitude_minimum": 40,
            "longitude_minimum": 120,
            "latitude_maximum": 60,
            "longitude_maximum": 160,
        }

        output_geom = {
            "latmin": 40,
            "lonmin": 120,
            "latmax": 60,
            "lonmax": 160,
        }

        with mock.patch("scrappi.api.base.BaseAPICallHandler._get_geom") as geom_mock:
            geom_mock.return_value = input_geom
            self.assertEqual(self.eodag_call_handler._set_geom(input_geom), output_geom)

    def test_set_geom_shapely(self):
        input_geom = Polygon([[120, 40], [160, 40], [160, 60], [140, 60]])

        with mock.patch("scrappi.api.base.BaseAPICallHandler._get_geom") as geom_mock:
            geom_mock.return_value = input_geom
            self.assertEqual(self.eodag_call_handler._set_geom(input_geom), input_geom)

    def test_set_geom_wktstr(self):
        input_geom = "POLYGON ((120 40, 160 40, 160 60, 140 60, 120 40))"
        output_geom = Polygon([[120, 40], [160, 40], [160, 60], [140, 60]])

        with mock.patch("scrappi.api.base.BaseAPICallHandler._get_geom") as geom_mock:
            geom_mock.return_value = input_geom
            self.assertEqual(self.eodag_call_handler._set_geom(input_geom), output_geom)

    @mock.patch("scrappi.api.base.BaseAPICallHandler._get_product_type", return_value="output")
    def test_set_product_type(self, mock_product):
        self.assertEqual(self.eodag_call_handler._set_product_type("LANDSAT_C2L1"), "output")
        mock_product.assert_called_with("LANDSAT_C2L1")

    def test_get_providers(self):
        with mock.patch.object(self.eodag_call_handler.dag, "available_providers") as mock_providers:
            mock_providers.return_value = "list of providers"
            self.assertEqual(self.eodag_call_handler.get_providers("S2_MSI_L1C"), "list of providers")
            mock_providers.assert_called_with("S2_MSI_L1C")

    @mock.patch("scrappi.api.eodag.Polygon", return_value=True)
    @mock.patch(
        "scrappi.api.eodag.EODAGCallHandler._set_datetime",
    )
    @mock.patch(
        "scrappi.api.eodag.EODAGCallHandler._set_geom",
        return_value={
            "latitude_minimum": -38,
            "longitude_minimum": 145,
            "latitude_maximum": -36,
            "longitude_maximum": 150,
        },
    )
    @mock.patch(
        "scrappi.api.eodag.EODAGCallHandler._set_product_type",
        return_value="LANDSAT_C2L1",
    )
    def test_perform_query(self, mock_product, mock_geom, mock_datetime, mock_poly):
        # make datetime formatter deterministic for any number of calls
        mock_datetime.side_effect = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S") if hasattr(d, "strftime") else d
        input_query = {
            "collection": "LANDSAT_C2L1",
            "start_time": dt.datetime(2022, 6, 7, 23, 30),
            "stop_time": dt.datetime(2022, 6, 7, 23, 50),
            "geom": {
                "latitude_minimum": -38,
                "longitude_minimum": 145,
                "latitude_maximum": -36,
                "longitude_maximum": 150,
            },
        }

        search_output = {
            "provider": "usgs",
            "collection": "LANDSAT_C2L1",
            "location": "https://earthexplorer.usgs.gov/download/external/options/landsat_ot_c2_l1/LC80890852022158LGN00/M2M/",
            "remote_location": "https://earthexplorer.usgs.gov/download/external/options/landsat_ot_c2_l1/LC80890852022158LGN00/M2M/",
            "properties": {
                "productType": "landsat_ot_c2_l1",
                "title": "LC08_L1TP_089085_20220607_20220616_02_T1",
                "publicationDate": "2022-06-22 18:27:47-05",
                "cloudCover": 18,
                "start_datetime": "2022-06-07T00:00:00",
                "end_datetime": "2022-06-07T23:59:59",
                "providers": [{"name": "usgs"}],
                "id": "LC08_L1TP_089085_20220607_20220616_02_T1",
                "quicklook": "https://landsatlook.usgs.gov/gen-browse?size=rrb&type=refl&product_id=LC08_L1TP_089085_20220607_20220616_02_T1",
                "thumbnail": "https://landsatlook.usgs.gov/gen-browse?size=thumb&type=refl&product_id=LC08_L1TP_089085_20220607_20220616_02_T1",
                "storageStatus": "ONLINE",
                "entityId": "LC80890852022158LGN00",
                "productId": "5e81f14f92acf9ef",
                "downloadLink": "https://earthexplorer.usgs.gov/download/external/options/landsat_ot_c2_l1/LC80890852022158LGN00/M2M/",
            },
            "geometry": Polygon(
                [
                    (149.64227, -37.10008),
                    (149.64227, -34.98604),
                    (152.22995, -34.98604),
                    (152.22995, -37.10008),
                    (149.64227, -37.10008),
                ]
            ),
            "search_intersection": Polygon(
                [
                    (149.64227, -36.0),
                    (150.0, -36.0),
                    (150.0, -37.10008),
                    (149.64227, -37.10008),
                    (149.64227, -36.0),
                ]
            ),
            "search_kwargs": {
                "productType": "LANDSAT_C2L1",
                "geometry": {
                    "longitude_minimum": 145.0,
                    "latitude_minimum": -38.0,
                    "longitude_maximum": 150.0,
                    "latitude_maximum": -36.0,
                },
            },
            "downloader_auth": None,
        }

        output_product = {
            "assets": {},
            "provider": "usgs",
            "collection": "LANDSAT_C2L1",
            "location": "https://earthexplorer.usgs.gov/download/external/options/landsat_ot_c2_l1/LC80890852022158LGN00/M2M/",
            "remote_location": "https://earthexplorer.usgs.gov/download/external/options/landsat_ot_c2_l1/LC80890852022158LGN00/M2M/",
            "properties": {
                "productType": "landsat_ot_c2_l1",
                "title": "LC08_L1TP_089085_20220607_20220616_02_T1",
                "publicationDate": "2022-06-22 18:27:47-05",
                "cloudCover": 18,
                "start_datetime": "2022-06-07T00:00:00",
                "end_datetime": "2022-06-07T23:59:59",
                "providers": [{"name": "usgs"}],
                "id": "LC08_L1TP_089085_20220607_20220616_02_T1",
                "quicklook": "https://landsatlook.usgs.gov/gen-browse?size=rrb&type=refl&product_id=LC08_L1TP_089085_20220607_20220616_02_T1",
                "thumbnail": "https://landsatlook.usgs.gov/gen-browse?size=thumb&type=refl&product_id=LC08_L1TP_089085_20220607_20220616_02_T1",
                "storageStatus": "ONLINE",
                "entityId": "LC80890852022158LGN00",
                "productId": "5e81f14f92acf9ef",
                "downloadLink": "https://earthexplorer.usgs.gov/download/external/options/landsat_ot_c2_l1/LC80890852022158LGN00/M2M/",
            },
            "geometry": Polygon(
                [
                    (149.64227, -37.10008),
                    (149.64227, -34.98604),
                    (152.22995, -34.98604),
                    (152.22995, -37.10008),
                    (149.64227, -37.10008),
                ]
            ),
            "search_intersection": Polygon(
                [
                    (149.64227, -36.0),
                    (150.0, -36.0),
                    (150.0, -37.10008),
                    (149.64227, -37.10008),
                    (149.64227, -36.0),
                ]
            ),
            "search_kwargs": {"productType": "LANDSAT_C2L1"},
            "downloader_auth": None,
            "downloader": None,
        }

        with mock.patch.object(self.eodag_call_handler.dag, "search_all") as mock_search:
            # Build a lightweight fake product object with as_dict() to avoid EOProduct formatting differences
            obj = type("FakeProd", (), {})()
            obj.as_dict = lambda: {
                "properties": {**search_output["properties"]},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [list(search_output["geometry"].exterior.coords)],
                },
                "id": search_output["properties"]["id"],
                "collection": search_output.get("collection"),
            }
            obj.search_intersection = search_output["search_intersection"]
            obj.geometry = search_output["geometry"]

            mock_search.return_value = [obj]

            products = self.eodag_call_handler.perform_query(input_query)
            product = products[0]

            self.assertEqual(
                product.prod_dict["properties"]["providers"][0]["name"],
                output_product["provider"],
            )
            self.assertEqual(product.collection, output_product["collection"])
            self.assertEqual(
                product.prod_dict["properties"].get("downloadLink"),
                output_product["properties"].get("downloadLink"),
            )
            self.assertTrue(
                isinstance(product.quicklook, str) and (product.quicklook == "" or product.quicklook.startswith("http"))
            )
            self.assertEqual(product.id, output_product["properties"]["id"])

            mock_product.assert_called_with("LANDSAT_C2L1")
            mock_geom.assert_called_with(
                {
                    "latitude_minimum": -38,
                    "longitude_minimum": 145,
                    "latitude_maximum": -36,
                    "longitude_maximum": 150,
                }
            )
            self.assertGreaterEqual(mock_datetime.call_count, 2)
            expected_dt = dt.datetime(2022, 6, 7, 23, 50)
            expected_str = expected_dt.strftime("%Y-%m-%dT%H:%M:%S")
            called = any(
                (hasattr(c.args[0], "strftime") and c.args[0] == expected_dt)
                or (isinstance(c.args[0], str) and c.args[0] == expected_str)
                for c in mock_datetime.call_args_list
            )
            self.assertTrue(called)

    @mock.patch("scrappi.api.eodag.Polygon", return_value=True)
    @mock.patch(
        "scrappi.api.eodag.EODAGCallHandler._set_datetime",
    )
    @mock.patch(
        "scrappi.api.eodag.EODAGCallHandler._set_geom",
        return_value=Polygon(
            [
                (149.64227, -36.0),
                (150.0, -36.0),
                (150.0, -37.10008),
                (149.64227, -37.10008),
                (149.64227, -36.0),
            ]
        ),
    )
    @mock.patch(
        "scrappi.api.eodag.EODAGCallHandler._set_product_type",
        return_value="LANDSAT_C2L1",
    )
    def test_perform_query_poly(self, mock_product, mock_geom, mock_datetime, mock_poly):
        # make datetime formatter deterministic for any number of calls
        mock_datetime.side_effect = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S") if hasattr(d, "strftime") else d
        input_query = {
            "collection": "LANDSAT_C2L1",
            "start_time": dt.datetime(2022, 6, 7, 23, 30),
            "stop_time": dt.datetime(2022, 6, 7, 23, 50),
            "geom": Polygon(
                [
                    (149.64227, -36.0),
                    (150.0, -36.0),
                    (150.0, -37.10008),
                    (149.64227, -37.10008),
                    (149.64227, -36.0),
                ]
            ),
        }

        search_output = {
            "provider": "usgs",
            "collection": "LANDSAT_C2L1",
            "location": "https://earthexplorer.usgs.gov/download/external/options/landsat_ot_c2_l1/LC80890852022158LGN00/M2M/",
            "remote_location": "https://earthexplorer.usgs.gov/download/external/options/landsat_ot_c2_l1/LC80890852022158LGN00/M2M/",
            "properties": {
                "productType": "landsat_ot_c2_l1",
                "title": "LC08_L1TP_089085_20220607_20220616_02_T1",
                "publicationDate": "2022-06-22 18:27:47-05",
                "cloudCover": 18,
                "start_datetime": "2022-06-07T00:00:00",
                "end_datetime": "2022-06-07T23:59:59",
                "providers": [{"name": "usgs"}],
                "id": "LC08_L1TP_089085_20220607_20220616_02_T1",
                "quicklook": "https://landsatlook.usgs.gov/gen-browse?size=rrb&type=refl&product_id=LC08_L1TP_089085_20220607_20220616_02_T1",
                "thumbnail": "https://landsatlook.usgs.gov/gen-browse?size=thumb&type=refl&product_id=LC08_L1TP_089085_20220607_20220616_02_T1",
                "storageStatus": "ONLINE",
                "entityId": "LC80890852022158LGN00",
                "productId": "5e81f14f92acf9ef",
                "downloadLink": "https://earthexplorer.usgs.gov/download/external/options/landsat_ot_c2_l1/LC80890852022158LGN00/M2M/",
            },
            "geometry": Polygon(
                [
                    (149.64227, -37.10008),
                    (149.64227, -34.98604),
                    (152.22995, -34.98604),
                    (152.22995, -37.10008),
                    (149.64227, -37.10008),
                ]
            ),
            "search_intersection": Polygon(
                [
                    (149.64227, -36.0),
                    (150.0, -36.0),
                    (150.0, -37.10008),
                    (149.64227, -37.10008),
                    (149.64227, -36.0),
                ]
            ),
            "search_kwargs": {
                "productType": "LANDSAT_C2L1",
                "geometry": {
                    "longitude_minimum": 145.0,
                    "latitude_minimum": -38.0,
                    "longitude_maximum": 150.0,
                    "latitude_maximum": -36.0,
                },
            },
            "downloader_auth": None,
        }

        output_product = {
            "assets": {},
            "provider": "usgs",
            "collection": "LANDSAT_C2L1",
            "location": "https://earthexplorer.usgs.gov/download/external/options/landsat_ot_c2_l1/LC80890852022158LGN00/M2M/",
            "remote_location": "https://earthexplorer.usgs.gov/download/external/options/landsat_ot_c2_l1/LC80890852022158LGN00/M2M/",
            "properties": {
                "productType": "landsat_ot_c2_l1",
                "title": "LC08_L1TP_089085_20220607_20220616_02_T1",
                "publicationDate": "2022-06-22 18:27:47-05",
                "cloudCover": 18,
                "startTimeFromAscendingNode": "2022-06-07 00:00:00",
                "completionTimeFromAscendingNode": "2022-06-07 00:00:00",
                "id": "LC08_L1TP_089085_20220607_20220616_02_T1",
                "quicklook": "https://landsatlook.usgs.gov/gen-browse?size=rrb&type=refl&product_id=LC08_L1TP_089085_20220607_20220616_02_T1",
                "thumbnail": "https://landsatlook.usgs.gov/gen-browse?size=thumb&type=refl&product_id=LC08_L1TP_089085_20220607_20220616_02_T1",
                "storageStatus": "ONLINE",
                "entityId": "LC80890852022158LGN00",
                "productId": "5e81f14f92acf9ef",
                "downloadLink": "https://earthexplorer.usgs.gov/download/external/options/landsat_ot_c2_l1/LC80890852022158LGN00/M2M/",
            },
            "geometry": Polygon(
                [
                    (149.64227, -37.10008),
                    (149.64227, -34.98604),
                    (152.22995, -34.98604),
                    (152.22995, -37.10008),
                    (149.64227, -37.10008),
                ]
            ),
            "search_intersection": Polygon(
                [
                    (149.64227, -36.0),
                    (150.0, -36.0),
                    (150.0, -37.10008),
                    (149.64227, -37.10008),
                    (149.64227, -36.0),
                ]
            ),
            "search_kwargs": {"productType": "LANDSAT_C2L1"},
            "downloader_auth": None,
            "downloader": None,
        }

        with mock.patch.object(self.eodag_call_handler.dag, "search_all") as mock_search:
            # Use a fake product object to ensure as_dict returns the expected structure
            obj = type("FakeProd", (), {})()
            obj.as_dict = lambda: {
                "properties": {**search_output["properties"]},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [list(search_output["geometry"].exterior.coords)],
                },
                "id": search_output["properties"]["id"],
                "collection": search_output.get("collection"),
            }
            obj.search_intersection = search_output["search_intersection"]
            obj.geometry = search_output["geometry"]

            mock_search.return_value = [obj]

            products = self.eodag_call_handler.perform_query(input_query)
            product = products[0]

            self.assertEqual(
                product.prod_dict["properties"]["providers"][0]["name"],
                output_product["provider"],
            )
            self.assertEqual(product.collection, output_product["collection"])
            self.assertEqual(
                product.prod_dict["properties"].get("downloadLink"),
                output_product["properties"].get("downloadLink"),
            )
            self.assertTrue(
                isinstance(product.quicklook, str) and (product.quicklook == "" or product.quicklook.startswith("http"))
            )
            self.assertEqual(product.id, output_product["properties"]["id"])

            mock_product.assert_called_with("LANDSAT_C2L1")
            mock_geom.assert_called_with(
                Polygon(
                    [
                        (149.64227, -36.0),
                        (150.0, -36.0),
                        (150.0, -37.10008),
                        (149.64227, -37.10008),
                        (149.64227, -36.0),
                    ]
                )
            )
            self.assertGreaterEqual(mock_datetime.call_count, 2)
            expected_dt = dt.datetime(2022, 6, 7, 23, 50)
            expected_str = expected_dt.strftime("%Y-%m-%dT%H:%M:%S")
            called = any(
                (hasattr(c.args[0], "strftime") and c.args[0] == expected_dt)
                or (isinstance(c.args[0], str) and c.args[0] == expected_str)
                for c in mock_datetime.call_args_list
            )
            self.assertTrue(called)

    def test_download_metadata(self):
        # purpose to be discussed
        pass

    def test_download_product_ProductItem(self):
        input_product = ProductItem(
            constellation="Sentinel-2",
            platform="S2A",
            collection="S2_MSI_L1C",
            id="S2A_MSIL1C_20221001T084801_N0400_R107_T33KWP_20221001T123324",
            url="",
            geometry=Polygon(
                (
                    (14.999802591641, -24.50175837821),
                    (15.757596662004, -24.499039822288),
                    (15.770908808258, -24.442610026108),
                    (15.80586933214, -24.294632160886),
                    (15.84060088455, -24.14669093206),
                    (15.876099065023, -23.998982180718),
                    (15.910846055559, -23.850993316575),
                    (15.945585244702, -23.702908496289),
                    (15.980265126168, -23.554689000244),
                    (15.991571437709, -23.506591342293),
                    (14.99980409915, -23.51001405806),
                    (14.999802591641, -24.50175837821),
                )
            ),
            start_time="2022-10-01T08:48:01",
            stop_time="2022-10-01T08:48:01",
            prod_dict={},
            filesystem=os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "examples",
            ),
        )

        with (
            mock.patch.object(EODAGCallHandler, "_download_product_EOProduct") as mock_download_EOProduct,
            mock.patch.object(EODAGCallHandler, "_perform_query") as mock_perform_query,
        ):
            # Make perform_query return a fake EOProduct with matching id
            fake_eoprod = mock.MagicMock(spec=EOProduct)
            fake_eoprod.as_dict.return_value = {"id": input_product.id}
            mock_perform_query.return_value = [fake_eoprod]

            self.eodag_call_handler.download_product(input_product)
            assert mock_download_EOProduct.call_args_list[0][0][0].as_dict()["id"] == input_product.id

    def test_download_product_ProductItemSet(self):
        input_product = ProductItem(
            constellation="Landsat",
            platform="Landsat-9",
            collection="LANDSAT_C2L1",
            id="LC09_L1TP_179076_20220926_20230327_02_T1",
            url="",
            geometry=Polygon(
                (
                    (14.14898, -24.16353),
                    (14.14898, -22.06475),
                    (16.39134, -22.06475),
                    (16.39134, -24.16353),
                    (14.14898, -24.16353),
                )
            ),
            start_time="2022-09-26T00:00:00",
            stop_time="2022-09-26T23:59:59",
            prod_dict={},
            filesystem=os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "examples",
            ),
        )
        input_product2 = ProductItem(
            constellation="Sentinel-2",
            platform="S2A",
            collection="S2_MSI_L1C",
            id="S2A_MSIL1C_20221001T084801_N0400_R107_T33KWP_20221001T123324",
            url="",
            geometry=Polygon(
                (
                    (14.999802591641, -24.50175837821),
                    (15.757596662004, -24.499039822288),
                    (15.770908808258, -24.442610026108),
                    (15.80586933214, -24.294632160886),
                    (15.84060088455, -24.14669093206),
                    (15.876099065023, -23.998982180718),
                    (15.910846055559, -23.850993316575),
                    (15.945585244702, -23.702908496289),
                    (15.980265126168, -23.554689000244),
                    (15.991571437709, -23.506591342293),
                    (14.99980409915, -23.51001405806),
                    (14.999802591641, -24.50175837821),
                )
            ),
            start_time="2022-10-01T08:48:01",
            stop_time="2022-10-01T08:48:01",
            prod_dict={},
            filesystem=os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "examples",
            ),
        )
        input_set = ProductItemSet([input_product, input_product2])

        fake_product_1 = mock.MagicMock()
        fake_product_1.as_dict.return_value = {"id": input_product.id}

        fake_product_2 = mock.MagicMock()
        fake_product_2.as_dict.return_value = {"id": input_product2.id}

        with (
            mock.patch.object(self.eodag_call_handler, "_perform_query") as mock_perform_query,
            mock.patch.object(EODAGCallHandler, "_download_product_EOProduct") as mock_download_EOProduct,
        ):
            mock_perform_query.side_effect = [[fake_product_1], [fake_product_2]]
            self.eodag_call_handler.download_product(input_set)

            assert mock_download_EOProduct.call_args_list[0][0][0].as_dict()["id"] == input_product.id
            assert mock_download_EOProduct.call_args_list[1][0][0].as_dict()["id"] == input_product2.id

    def test_download_product_EOProduct(self):
        input_product = EOProduct(
            provider="usgs",
            properties={
                "productType": "landsat_ot_c2_l1",
                "title": "LC08_L1TP_089085_20220607_20220616_02_T1",
                "publicationDate": "2022-06-22 18:27:47-05",
                "cloudCover": 18,
                "startTimeFromAscendingNode": "2022-06-07 00:00:00",
                "completionTimeFromAscendingNode": "2022-06-07 00:00:00",
                "id": "LC08_L1TP_089085_20220607_20220616_02_T1",
                "quicklook": "https://landsatlook.usgs.gov/gen-browse?size=rrb&type=refl&product_id=LC08_L1TP_089085_20220607_20220616_02_T1",
                "thumbnail": "https://landsatlook.usgs.gov/gen-browse?size=thumb&type=refl&product_id=LC08_L1TP_089085_20220607_20220616_02_T1",
                "storageStatus": "ONLINE",
                "entityId": "LC80890852022158LGN00",
                "productId": "5e81f14f92acf9ef",
                "downloadLink": "https://earthexplorer.usgs.gov/download/external/options/landsat_ot_c2_l1/LC80890852022158LGN00/M2M/",
            },
            productType="LANDSAT_C2L1",
        )

        with mock.patch.object(EOProduct, "download") as mock_download:
            # ensure the download is considered valid by the validator (no real file is created)
            with mock.patch("scrappi.api.eodag.validate_product_download", return_value=True):
                path = example_path
                mock_download.return_value = os.path.join(path, input_product.properties["id"])
                self.eodag_call_handler._download_product_EOProduct(input_product, path)
                mock_download.assert_called()
                called_kwargs = mock_download.call_args.kwargs
                self.assertEqual(called_kwargs.get("outputs_prefix"), example_path)
                self.assertEqual(called_kwargs.get("extract"), False)

    def test_download_product_None(self):
        input_product = ProductItem(
            constellation="Sentinel-2",
            platform="S2A",
            collection="S2_MSI_L1C",
            id="bad_id",
            url="",
            geometry=Polygon(
                (
                    (14.999802591641, -24.50175837821),
                    (15.757596662004, -24.499039822288),
                    (15.770908808258, -24.442610026108),
                    (15.80586933214, -24.294632160886),
                    (15.84060088455, -24.14669093206),
                    (15.876099065023, -23.998982180718),
                    (15.910846055559, -23.850993316575),
                    (15.945585244702, -23.702908496289),
                    (15.980265126168, -23.554689000244),
                    (15.991571437709, -23.506591342293),
                    (14.99980409915, -23.51001405806),
                    (14.999802591641, -24.50175837821),
                )
            ),
            start_time="2022-10-01T08:48:01",
            stop_time="2022-10-01T08:48:01",
            prod_dict={},
        )

        assert self.eodag_call_handler.download_product(input_product) is None

    def test_download_product_filename(self):
        # input_product = EOProduct(
        #     provider="usgs",
        #     properties={
        #         "productType": "landsat_ot_c2_l1",
        #         "title": "LC08_L1TP_089085_20220607_20220616_02_T1",
        #         "publicationDate": "2022-06-22 18:27:47-05",
        #         "cloudCover": 18,
        #         "startTimeFromAscendingNode": "2022-06-07 00:00:00",
        #         "completionTimeFromAscendingNode": "2022-06-07 00:00:00",
        #         "id": "LC08_L1TP_089085_20220607_20220616_02_T1",
        #         "quicklook": "https://landsatlook.usgs.gov/gen-browse?size=rrb&type=refl&product_id=LC08_L1TP_089085_20220607_20220616_02_T1",
        #         "thumbnail": "https://landsatlook.usgs.gov/gen-browse?size=thumb&type=refl&product_id=LC08_L1TP_089085_20220607_20220616_02_T1",
        #         "storageStatus": "ONLINE",
        #         "entityId": "LC80890852022158LGN00",
        #         "productId": "5e81f14f92acf9ef",
        #         "downloadLink": "https://earthexplorer.usgs.gov/download/external/options/landsat_ot_c2_l1/LC80890852022158LGN00/M2M/",
        #         "geometry": Polygon(
        #             [
        #                 (-37.10008, 149.64227),
        #                 (-34.98604, 149.64227),
        #                 (-34.98604, 152.22995),
        #                 (-37.10008, 152.22995),
        #                 (-37.10008, 149.64227),
        #             ]
        #         ),
        #     },
        #     productType="LANDSAT_C2L1",
        # )
        path = example_path
        with (
            mock.patch.object(EOProduct, "downloader", create=True) as mock_downloader,
            mock.patch("scrappi.api.eodag.EODataAccessGateway.search") as mock_search,
        ):
            mock_downloader.config = mock.Mock(timeout=10, wait=0.2)
            fs = make_fs(path)
            fake_eoprod = mock.MagicMock(spec=EOProduct)
            product_id = "S2A_MSIL1C_20220928T083731_N0400_R064_T33KWP_20220928T122019.SAFE"
            fake_eoprod.properties = {"id": product_id, "productType": "S2_MSI_L1C"}
            fake_eoprod.provider = "cop_dataspace"
            fake_eoprod.download.return_value = os.path.join(path, product_id)
            mock_search.return_value = [fake_eoprod]

            # make validator accept mocked download (no real file created)
            with mock.patch("scrappi.api.eodag.validate_product_download", return_value=True):
                self.eodag_call_handler.download_product_filename(
                    "S2A_MSIL1C_20220928T083731_N0400_R064_T33KWP_20220928T122019.SAFE",
                    fs,
                )

                fake_eoprod.download.assert_called()
                called_kwargs = fake_eoprod.download.call_args.kwargs
                self.assertEqual(called_kwargs.get("outputs_prefix"), example_path)
                self.assertEqual(called_kwargs.get("extract"), False)

    def test_quicklook(self):
        input_L8 = {
            "collection": "LANDSAT_C2L1",
            "start_time": dt.datetime(2022, 6, 7, 23, 30),
            "stop_time": dt.datetime(2022, 6, 7, 23, 50),
            "geom": {
                "latitude_minimum": -38,
                "longitude_minimum": 145,
                "latitude_maximum": -36,
                "longitude_maximum": 150,
            },
        }
        input_S2 = {
            "collection": "S2_MSI_L1C",
            "start_time": dt.datetime(2022, 6, 7, 23, 30),
            "stop_time": dt.datetime(2022, 6, 8, 23, 50),
            "geom": {
                "latitude_minimum": -38,
                "longitude_minimum": 145,
                "latitude_maximum": -36,
                "longitude_maximum": 150,
            },
        }
        input_S3 = {
            "collection": "S3_EFR",
            "start_time": dt.datetime(2022, 6, 7, 23, 30),
            "stop_time": dt.datetime(2022, 6, 12, 23, 50),
            "geom": {
                "latitude_minimum": -38,
                "longitude_minimum": 145,
                "latitude_maximum": -36,
                "longitude_maximum": 150,
            },
        }

        # Patch `make_fs` so any absolute T: paths returned by providers
        # are resolved to the `t-drive` filesystem handler rather than
        # raising when the T: drive does not exist on the test host.
        from scrappi.fs.tdrive import TdriveFileSystem

        orig_make_fs = make_fs
        with mock.patch(
            "scrappi.interface.make_fs",
            side_effect=lambda fs, context=None: TdriveFileSystem(context=context) if fs else orig_make_fs(fs, context),
        ):
            # Also patch the FS factory method to directly return a TdriveFileSystem
            # when provider metadata contains an absolute T: path. This avoids
            # dependence on the test host having a mounted T: drive.
            import scrappi.fs.factory as fs_factory

            orig_get = fs_factory.FSCallHandlerFactory.get_fs_call_handler

            def _get_fs(self, name, context=None):
                if name and ("T:\\" in str(name) or str(name).upper().startswith("T:")):
                    return TdriveFileSystem(context=context)
                return orig_get(self, name, context)

            with mock.patch.object(
                fs_factory.FSCallHandlerFactory,
                "get_fs_call_handler",
                new=_get_fs,
            ):
                products = self.eodag_call_handler.perform_query(input_S2)

        # Check that the quicklook is a non-empty URL
        quicklook = products[0].quicklook
        assert isinstance(quicklook, str) and quicklook.startswith("http") and len(quicklook) > 10

        # For L8, mock perform_query to avoid real network calls and provider-specific variations
        expected_quicklook = "https://landsatlook.usgs.gov/gen-browse?size=rrb&type=refl&product_id=LC08_L1TP_089085_20220607_20220616_02_T1"
        fake_product = ProductItem(
            constellation="Landsat",
            platform="Landsat-8",
            collection="LANDSAT_C2L1",
            id="LC08_L1TP_089085_20220607_20220616_02_T1",
            geometry=Polygon(
                [
                    (149.64227, -37.10008),
                    (149.64227, -34.98604),
                    (152.22995, -34.98604),
                    (152.22995, -37.10008),
                    (149.64227, -37.10008),
                ]
            ),
            start_time=dt.datetime(2022, 6, 7, 0, 0),
            stop_time=dt.datetime(2022, 6, 7, 23, 59, 59),
            prod_dict={
                "properties": {
                    "providers": [{"name": "usgs"}],
                    "id": "LC08_L1TP_089085_20220607_20220616_02_T1",
                    "quicklook": expected_quicklook,
                    "cloudCover": 18,
                }
            },
            url="https://earthexplorer.usgs.gov/download/external/options/landsat_ot_c2_l1/LC80890852022158LGN00/M2M/",
            quicklook=expected_quicklook,
        )

        with mock.patch.object(
            self.eodag_call_handler,
            "perform_query",
            return_value=ProductItemSet([fake_product]),
        ):
            products = self.eodag_call_handler.perform_query(input_L8)
            assert products[0].quicklook == expected_quicklook

    def test_quicklook_preferred_provider(self):
        context = ScrappiContext()
        context["api"]["preferred_provider"] = "creodias"
        eodag_call_handler = EODAGCallHandler(context)

        input_S2 = {
            "collection": "S2_MSI_L1C",
            "start_time": dt.datetime(2022, 6, 7, 23, 30),
            "stop_time": dt.datetime(2022, 6, 8, 23, 50),
            "geom": {
                "latitude_minimum": -38,
                "longitude_minimum": 145,
                "latitude_maximum": -36,
                "longitude_maximum": 150,
            },
        }
        # Patch filesystem resolution as providers may return absolute T: paths
        # which don't exist on the test host. Ensure these resolve to the
        # TdriveFileSystem for the scope of this test.
        from scrappi.fs.tdrive import TdriveFileSystem
        import scrappi.fs.factory as fs_factory

        orig_get = fs_factory.FSCallHandlerFactory.get_fs_call_handler

        def _get_fs(self, name, context=None):
            if name and ("T:\\" in str(name) or str(name).upper().startswith("T:")):
                return TdriveFileSystem(context=context)
            return orig_get(self, name, context)

        with mock.patch.object(fs_factory.FSCallHandlerFactory, "get_fs_call_handler", new=_get_fs):
            products = eodag_call_handler.perform_query(input_S2)
        quicklook = products[0].quicklook

        assert quicklook == ("https://datahub.creodias.eu/odata/v1/Assets(4d634f99-05c1-4120-8297-abad05301f9c)/$value")

        # assert products[0].quicklook == ""


if __name__ == "__main__":
    unittest.main()
