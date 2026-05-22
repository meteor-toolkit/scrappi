"""scrappi.tests.test_interface - tests for scrappi.interface"""

import os
import random
import shutil
import shutil
import string
import unittest
import datetime as dt
import numpy as np
import numpy.testing as npt

from unittest import mock
from shapely.geometry import Point, Polygon
from scrappi.product import ProductItem, ProductItemSet
from scrappi.interface import *
from scrappi.api.factory import APICallHandlerFactory
from scrappi import THIS_DIRECTORY, ScrappiContext

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]


class TestInterface(unittest.TestCase):
    def setUp(self) -> None:
        letters = string.ascii_lowercase
        self.tmp_dir_name = "tmp_" + "".join(random.choice(letters) for i in range(5))
        self.tmp_dir_path = os.path.join(THIS_DIRECTORY, self.tmp_dir_name)
        os.makedirs(self.tmp_dir_path)

        self.p = ProductItem(
            constellation="Sentinel-3",
            platform="S3B",
            collection="S3_EFR",
            api="eodag",
            id="S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002",
            geometry=Polygon(
                (
                    (21.252, -34.5187),
                    (21.8983, -31.8836),
                    (22.5277, -29.2403),
                    (23.1427, -26.5948),
                    (23.7457, -23.9471),
                    (23.0766, -23.8181),
                    (22.4168, -23.6878),
                    (21.7545, -23.554),
                    (21.095, -23.4188),
                    (20.4393, -23.2775),
                    (19.781, -23.1351),
                    (19.1288, -22.9881),
                    (18.4738, -22.8428),
                    (17.8229, -22.6926),
                    (17.1738, -22.5451),
                    (16.5212, -22.3887),
                    (15.8711, -22.23),
                    (15.2236, -22.0691),
                    (14.5757, -21.9053),
                    (13.9278, -21.7384),
                    (13.2816, -21.5691),
                    (12.6433, -21.3989),
                    (12.0034, -21.2254),
                    (11.3643, -21.0485),
                    (10.5243, -23.6423),
                    (9.63737, -26.2286),
                    (8.698, -28.8061),
                    (7.70076, -31.3688),
                    (8.38884, -31.5712),
                    (9.07972, -31.7691),
                    (9.77638, -31.964),
                    (10.4712, -32.1537),
                    (11.1726, -32.3406),
                    (11.8722, -32.5222),
                    (12.5793, -32.7012),
                    (13.286, -32.8756),
                    (13.9979, -33.0466),
                    (14.7147, -33.2089),
                    (15.4305, -33.3715),
                    (16.1486, -33.5271),
                    (16.871, -33.6842),
                    (17.5955, -33.834),
                    (18.3207, -33.9817),
                    (19.0503, -34.1217),
                    (19.781, -34.2582),
                    (20.5158, -34.3907),
                    (21.252, -34.5187),
                )
            ),
            start_time="2022-05-17T08:32:38",
            stop_time="2022-05-17T08:35:38",
            prod_dict={},
            url="",
            filesystem=self.tmp_dir_path,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir_path)

    def test_get_api_name_single(self):
        context = ScrappiContext()
        context["api"]["preferred_api"] = None
        m = mock.MagicMock()
        m().list_collections.return_value = ["LANDSAT_C2L1"]
        with mock.patch.dict(
            "scrappi.interface.Factory.api_call_handlers", {"handle1": m}, clear=True
        ) as mock_handlers:
            self.assertEqual(get_api_name("LANDSAT_C2L1", context=context), "handle1")

    def test_get_api_name_all(self):
        context = ScrappiContext()
        context["api"]["preferred_api"] = None
        m = mock.MagicMock()
        m().list_collections.return_value = ["LANDSAT_C2L1"]
        with mock.patch.dict(
            "scrappi.interface.Factory.api_call_handlers",
            {"handle1": m, "handle2": m},
            clear=True,
        ) as mock_handlers:
            self.assertEqual(get_api_name("LANDSAT_C2L1", all_apis=True), ["handle1", "handle2"])

    def test_get_api_name_None(self):
        context = ScrappiContext()
        context["api"]["preferred_api"] = None
        m = mock.MagicMock()
        m().list_collections.return_value = ["LANDSAT_C2L1"]
        with mock.patch.dict(
            "scrappi.interface.Factory.api_call_handlers",
            {"handle1": m, "handle2": m},
            clear=True,
        ) as mock_handlers:
            self.assertEqual(get_api_name("S2_MSI_L1C", context=context), None)

    @mock.patch(
        "scrappi.api.eodag.EODataAccessGateway.list_collections",
        return_value=[mock.Mock(id="LANDSAT_C2L1"), mock.Mock(id="S2_MSI_L1C")],
    )
    @mock.patch(
        "scrappi.api.earthaccess_api.EarthaccessCallHandler.list_collections",
        return_value=[],
    )
    def test_list_collections_guess_lower(self, mocklist, mocklist2):
        self.assertEqual(list_collections(guess="landsat"), ["LANDSAT_C2L1"])

    @mock.patch(
        "scrappi.api.eodag.EODataAccessGateway.list_collections",
        return_value=[mock.Mock(id="LANDSAT_C2L1"), mock.Mock(id="S2_MSI_L1C")],
    )
    @mock.patch(
        "scrappi.api.earthaccess_api.EarthaccessCallHandler.list_collections",
        return_value=[],
    )
    def test_list_collections_guess_upper(self, mock_list, mocklist2):
        self.assertEqual(list_collections(guess="S2"), ["S2_MSI_L1C"])

    def test_make_api(self):
        context = ScrappiContext()
        m = mock.MagicMock()
        with mock.patch.dict("scrappi.interface.Factory.api_call_handlers", {"api": m}, clear=True) as mock_handlers:
            make_api("api", context)
            m.assert_called_with(context=context)

    def test_make_fs(self):
        context = ScrappiContext()
        context["fs"]["path"] = "fs"
        m = mock.MagicMock()
        with mock.patch.dict("scrappi.interface.FSFactory.fs_call_handlers", {"fs": m}, clear=True) as mock_handlers:
            make_fs("fs", context)
            m.assert_called_with(context=context)

    def test_set_credentials_context(self):
        context = ScrappiContext()
        context = set_credentials("testapi", {"username": "user", "password": "pass"}, context)
        self.assertEqual(context["testapi"]["credentials"], {"username": "user", "password": "pass"})

    def test_update_context_file(self):
        update_context_file({"testapi": {"credentials": {"username": "user", "password": "pass"}}})
        context = ScrappiContext()
        self.assertEqual(context["testapi"]["credentials"], {"username": "user", "password": "pass"})

    def test_perform_query(self):
        m = mock.MagicMock()
        m().list_collections.return_value = ["LANDSAT_C2L1"]
        with mock.patch.dict("scrappi.interface.Factory.api_call_handlers", {"api": m}, clear=True) as mock_handlers:
            context = ScrappiContext()
            context["api"]["preferred_api"] = "api"
            query = {"collection": "LANDSAT_C2L1"}
            perform_query(query, context)
            m.assert_called_with(context=context)
            m().perform_query.assert_called_with({"collection": "LANDSAT_C2L1"})

    def test_download_product(self):
        context = ScrappiContext()
        m = mock.MagicMock()
        m().list_collections.return_value = ["S3_EFR"]
        with mock.patch.dict("scrappi.interface.Factory.api_call_handlers", {"api": m}, clear=True) as mock_handlers:
            download_product(self.p, context)
            m.assert_called_with(context=context)
            assert m().download_product.call_args[0][0] == self.p

    def test_download_product_filename(self):
        context = ScrappiContext()
        context["api"]["preferred_api"] = "api"
        m = mock.MagicMock()
        with mock.patch.dict("scrappi.interface.Factory.api_call_handlers", {"api": m}, clear=True) as mock_handlers:
            download_product_filename(
                "S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002",
                context=context,
            )
            m.assert_called_with(context=context)
            m().download_product_filename.assert_called_with(
                "S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002",
                context=context,
            )

            # attempt NotImplementedError (where gitlab searches products) and UnsupportedProvider for use on local
            try:
                with self.assertRaises(NotImplementedError):
                    context["api"]["preferred_api"] = "eodag"
                    download_product_filename(
                        "S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002",
                        context,
                    )
                from eodag.utils.exceptions import UnsupportedProvider

                with self.assertRaises(UnsupportedProvider):
                    download_product_filename(
                        "eodag",
                        "S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002",
                        config_dict={
                            "eodag": {
                                "username": "username",
                                "password": "password",
                            }
                        },
                    )
            except:
                print("product not unsupported or non existing")

    def test_download_product_scene(self):
        context = ScrappiContext()
        context["api"]["preferred_api"] = "api"
        m = mock.MagicMock()
        with mock.patch.dict("scrappi.interface.Factory.api_call_handlers", {"api": m}, clear=True) as mock_handlers:
            download_product_scene("LC09_L1GT_158111_20220126_20220126_02_T2", context)
            m.assert_called_with(context=context)
            m().download_product_scene.assert_called_with(
                "LC09_L1GT_158111_20220126_20220126_02_T2",
                context=context,
            )

        with self.assertRaises(NotImplementedError):
            context["api"]["preferred_api"] = "eodag"
            download_product_scene(
                "S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002",
                context,
            )

    def test_is_insitu_collection(self):
        assert is_insitu_collection("RCN_TOA")
        assert not is_insitu_collection("S2_MSI_L1C")

    @mock.patch("scrappi.interface.convert_datetime", return_value=dt.datetime(2022, 1, 10))
    def test_make_query_with_tolerance_deg_min(self, mock_datetime):
        self.assertEqual(
            make_query_with_tolerance("LANDSAT_C2L1", 1, 2, "2022-01-10", 1, None, 1, None),
            {
                "collections": ["LANDSAT_C2L1"],
                "geom": [0, 1, 2, 3],
                "start_time": "2022-01-09T23:59:00",
                "stop_time": "2022-01-10T00:01:00",
            },
        )

    @mock.patch("scrappi.interface.convert_datetime", return_value=dt.datetime(2022, 1, 10))
    def test_make_query_with_tolerance_point(self, mock_datetime):
        self.assertEqual(
            make_query_with_tolerance("LANDSAT_C2L1", 1, 2, "2022-01-10", None, None, 1, None),
            {
                "collections": ["LANDSAT_C2L1"],
                "geom": Point(1, 2),
                "start_time": "2022-01-09T23:59:00",
                "stop_time": "2022-01-10T00:01:00",
            },
        )

    @mock.patch("scrappi.interface.convert_datetime", return_value=dt.datetime(2022, 1, 10))
    def test_make_query_with_tolerance_spatial_error(self, mock_datetime):
        self.assertRaises(
            ValueError,
            make_query_with_tolerance,
            "LANDSAT_C2L1",
            1,
            2,
            "2022-01-10",
            1,
            1,
            1,
            None,
        )

    @mock.patch("scrappi.interface.convert_datetime", return_value=dt.datetime(2022, 1, 10))
    def test_make_query_with_tolerance_m_hours(self, mock_datetime):
        mock_transformer = mock.MagicMock()
        mock_transformer.transform.side_effect = [(1, 0), (3, 2)]
        mock_reverse_transformer = mock.MagicMock()
        mock_reverse_transformer.transform.return_value = 10, 10
        with mock.patch(
            "scrappi.interface.Transformer.from_crs",
            side_effect=[mock_transformer, mock_reverse_transformer],
        ) as mock_from_crs:
            self.assertEqual(
                make_query_with_tolerance("LANDSAT_C2L1", 1, 2, "2022-01-10", None, 1, None, 1),
                {
                    "collections": ["LANDSAT_C2L1"],
                    "geom": [10, 10, 10, 10],
                    "start_time": "2022-01-09T23:00:00",
                    "stop_time": "2022-01-10T01:00:00",
                },
            )

    @mock.patch("scrappi.interface.convert_datetime", return_value=dt.datetime(2022, 1, 10))
    def test_make_query_with_tolerance_temporal_error_both(self, mock_datetime):
        self.assertRaises(
            ValueError,
            make_query_with_tolerance,
            "LANDSAT_C2L1",
            1,
            2,
            "2022-01-10",
            1,
            None,
            1,
            1,
        )

    @mock.patch("scrappi.interface.convert_datetime", return_value=dt.datetime(2022, 1, 10))
    def test_make_query_with_tolerance_temporal_error_None(self, mock_datetime):
        self.assertRaises(
            ValueError,
            make_query_with_tolerance,
            "LANDSAT_C2L1",
            1,
            2,
            "2022-01-10",
            1,
            None,
            None,
            None,
        )

    def test_generate_bounding_box_mock(self):
        mock_transformer = mock.MagicMock()
        mock_transformer.transform.return_value = 10, 10
        mock_reverse_transformer = mock.MagicMock()
        mock_reverse_transformer.transform.side_effect = [(1, 1), (2, 2)]
        with mock.patch(
            "scrappi.interface.Transformer.from_crs",
            side_effect=[mock_transformer, mock_reverse_transformer],
        ) as mock_from_crs:
            self.assertEqual(
                generate_bounding_box(2, 1, 3, 4326),
                [[1, 2], [2, 2], [2, 1], [1, 1], [1, 2]],
            )

            mock_transformer.transform.assert_called_with(1, 2)
            mock_reverse_transformer.transform.assert_called_with(13, 13)

    def test_generate_bounding_box(self):
        bbox = generate_bounding_box(0, 0, 100)
        npt.assert_allclose(
            np.abs(np.array(bbox).flatten()), 100 / 6378100 / np.pi * 180, rtol=0.01
        )  # manual calculation using radius of earth

    def test_generate_bounding_lat_lon(self):
        latlon = generate_bounding_box(0, 0, 100)
        npt.assert_allclose(
            np.abs(np.array(latlon).flatten()), 100 / 6378100 / np.pi * 180, rtol=0.01
        )  # manual calculation using radius of earth


if __name__ == "__main__":
    unittest.main()
