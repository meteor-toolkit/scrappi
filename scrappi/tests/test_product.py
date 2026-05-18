"""scrappi.tests.test_product - tests for scrappi.product"""

import unittest
from unittest.mock import patch
import unittest.mock as mock
from scrappi.product import (
    ProductItem,
    ProductItemSet,
    open_product_item,
    open_product_item_set,
    product_item_from_dict,
    product_item_set_from_dict,
)
from shapely.geometry import Polygon
from scrappi.api.eodag import EODAGCallHandler
from eodag import EOProduct
from processor_tools.utils.formatters import convert_datetime

from datetime import datetime
from matplotlib import pyplot as plt
from scrappi.fs.tdrive import TdriveFileSystem
from scrappi.fs.localfilesystem import LocalFileSystem
from typing import Dict, Union
import string
import random
import os
import shutil
import socket

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]


THIS_DIRECTORY = os.path.dirname(__file__)

S3_PRODUCT_EXAMPLE = {
    "constellation": "Sentinel-3",
    "platform": "S3B",
    "collection": "S3_EFR",
    "id": "S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002",
    "geometry": Polygon(
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
    "start_time": convert_datetime("2022-05-17T08:32:38"),
    "stop_time": convert_datetime("2022-05-17T08:35:38"),
    "prod_dict": {"val": "entry"},
    "filter_dict": {"val": "entry"},
    "filesystem": "t-drive",
}

L8_PRODUCT_EXAMPLE_1 = {
    "constellation": "Landsat",
    "platform": "LC08",
    "collection": "LANDSAT_C2L1",
    "id": "LC08_L1TP_172030_20220120_20220127_02_T2C",
    "geometry": [
        (41.0856816815745, 44.24112580952904),
        (41.08680806465548, 44.24110522982958),
        (43.393265796852866, 43.82234984482247),
        (43.39318664569185, 43.821272570187),
        (42.777074012665516, 42.11245652952103),
        (42.777074012665516, 42.11245652952103),
        (40.531355852298944, 42.52837451259882),
        (40.531362450839524, 42.52864459095809),
        (41.0856816815745, 44.24112580952904),
    ],
    "start_time": datetime(2022, 6, 7, 23, 40, 8, 609447),
    "stop_time": datetime(2022, 6, 7, 23, 45, 40, 379447),
    "prod_dict": {"val": "entry"},
    "filter_dict": {"val": "entry"},
}


L8_PRODUCT_EXAMPLE_2 = {
    "constellation": "Landsat",
    "platform": "LC08",
    "collection": "LANDSAT_C2L1",
    "id": "LC08_L1TP_172030_20220120_20220127_02_T2B",
    "geometry": [
        (40.17522471269021, 41.3861400123577),
        (40.17558345095594, 41.3861363475318),
        (42.38002952306863, 40.978818955572315),
        (42.38000194853155, 40.978279401481856),
        (41.80764599721697, 39.26470702042967),
        (41.805909323763835, 39.26474891065633),
        (39.65908676451177, 39.6694679250438),
        (39.65908676451177, 39.6694679250438),
        (40.17522471269021, 41.3861400123577),
    ],
    "start_time": datetime(2022, 6, 7, 23, 30, 8, 609447),
    "stop_time": datetime(2022, 6, 7, 23, 45, 40, 379447),
    "prod_dict": {"val": "entry"},
    "filter_dict": {"val": "entry"},
}

L8_PRODUCT_EXAMPLE_3 = {
    "constellation": "Landsat",
    "platform": "LC08",
    "collection": "LANDSAT_C2L1",
    "id": "LC08_L1TP_172030_20220120_20220127_02_T2A",
    "geometry": [
        (42.06239725042473, 47.09014884645623),
        (42.063186749290715, 47.090169109917824),
        (44.48843284961724, 46.65748606317669),
        (44.48843284961724, 46.65748606317669),
        (43.81882313084526, 44.953559032103655),
        (43.81806263359167, 44.95355116301529),
        (41.46673146290274, 45.381351153094556),
        (41.46671465356733, 45.381620678652574),
        (42.06239725042473, 47.09014884645623),
    ],
    "start_time": datetime(2022, 6, 7, 23, 35, 8, 609447),
    "stop_time": datetime(2022, 6, 7, 23, 45, 40, 379447),
    "prod_dict": {"val": "entry"},
    "filter_dict": {"val": "entry"},
}

S2_PRODUCT_EXAMPLE = {
    "constellation": "Sentinel-2",
    "platform": "S2A",
    "collection": "S2_MSI_L1C",
    "id": "S2A_MSIL1C_20221001T084801_N0400_R107_T33KWP_20221001T123324",
    "geometry": Polygon(
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
    "start_time": convert_datetime("2022-10-01T08:48:01"),
    "stop_time": convert_datetime("2022-10-02T08:48:01"),
    "prod_dict": {"val": "entry"},
    "filter_dict": {"val": "entry"},
}

example_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "examples",
)


class TestProductItem(unittest.TestCase):
    def setUp(self) -> None:
        letters = string.ascii_lowercase
        self.tmp_dir_name = "tmp_" + "".join(random.choice(letters) for i in range(5))
        self.tmp_dir_path = os.path.join(THIS_DIRECTORY, self.tmp_dir_name)
        os.makedirs(self.tmp_dir_path)

        self.p = ProductItem(
            constellation=S2_PRODUCT_EXAMPLE["constellation"],
            platform=S2_PRODUCT_EXAMPLE["platform"],
            collection=S2_PRODUCT_EXAMPLE["collection"],
            id=S2_PRODUCT_EXAMPLE["id"],
            url="",
            geometry=S2_PRODUCT_EXAMPLE["geometry"],
            start_time=S2_PRODUCT_EXAMPLE["start_time"],
            stop_time=S2_PRODUCT_EXAMPLE["stop_time"],
            prod_dict=S2_PRODUCT_EXAMPLE["prod_dict"],
            filter_dict=S2_PRODUCT_EXAMPLE["filter_dict"],
            filesystem=self.tmp_dir_path,
        )

        

    def tearDown(self):
        shutil.rmtree(self.tmp_dir_path)

    def test___init__(self):
        p = self.p
        self.assertEqual(p.platform, S2_PRODUCT_EXAMPLE["platform"])
        self.assertEqual(p.collection, S2_PRODUCT_EXAMPLE["collection"])
        self.assertEqual(p.id, S2_PRODUCT_EXAMPLE["id"])
        self.assertEqual(p._geometry.wkt, S2_PRODUCT_EXAMPLE["geometry"].wkt)
        self.assertEqual(p.start_time, S2_PRODUCT_EXAMPLE["start_time"])
        self.assertEqual(p.stop_time, S2_PRODUCT_EXAMPLE["stop_time"])
        self.assertDictEqual(p.prod_dict, S2_PRODUCT_EXAMPLE["prod_dict"])
        self.assertDictEqual(p.filter_dict, S2_PRODUCT_EXAMPLE["filter_dict"])

    def test_to_json(self):
        p_dict = self.p.to_json()

        exp_p_dict = {
            "constellation": "Sentinel-2",
            "platform": "S2A",
            "collection": "S2_MSI_L1C",
            "id": "S2A_MSIL1C_20221001T084801_N0400_R107_T33KWP_20221001T123324",
            "geometry": "POLYGON ((14.999802591641 -24.50175837821, 15.757596662004 -24.499039822288, 15.770908808258 -24.442610026108, 15.80586933214 -24.294632160886, 15.84060088455 -24.14669093206, 15.876099065023 -23.998982180718, 15.910846055559 -23.850993316575, 15.945585244702 -23.702908496289, 15.980265126168 -23.554689000244, 15.991571437709 -23.506591342293, 14.99980409915 -23.51001405806, 14.999802591641 -24.50175837821))",
            "start_time": "2022-10-01T08:48:01+00:00",
            "stop_time": "2022-10-02T08:48:01+00:00",
            "url": "",
            "quicklook": "",
            "prod_dict": {"val": "entry"},
            "filter_dict": {"val": "entry"},
        }

        self.assertDictEqual(p_dict, exp_p_dict)

    def test_to_json_path(self):
        tmp_json_path = os.path.join(self.tmp_dir_path, "pi.json")
        p_dict = self.p.to_json(tmp_json_path)

        exp_p_dict = {
            "constellation": "Sentinel-2",
            "platform": "S2A",
            "collection": "S2_MSI_L1C",
            "id": "S2A_MSIL1C_20221001T084801_N0400_R107_T33KWP_20221001T123324",
            "geometry": "POLYGON ((14.999802591641 -24.50175837821, 15.757596662004 -24.499039822288, 15.770908808258 -24.442610026108, 15.80586933214 -24.294632160886, 15.84060088455 -24.14669093206, 15.876099065023 -23.998982180718, 15.910846055559 -23.850993316575, 15.945585244702 -23.702908496289, 15.980265126168 -23.554689000244, 15.991571437709 -23.506591342293, 14.99980409915 -23.51001405806, 14.999802591641 -24.50175837821))",
            "start_time": "2022-10-01T08:48:01+00:00",
            "stop_time": "2022-10-02T08:48:01+00:00",
            "url": "",
            "quicklook": "",
            "prod_dict": {"val": "entry"},
            "filter_dict": {"val": "entry"},
        }

        self.assertDictEqual(p_dict, exp_p_dict)

        self.assertTrue(tmp_json_path)

    def test_product_item_from_dict(self):
        p_dict = {
            "constellation": "Sentinel-2",
            "platform": "S2A",
            "collection": "S2_MSI_L1C",
            "id": "S2A_MSIL1C_20221001T084801_N0400_R107_T33KWP_20221001T123324",
            "geometry": "POLYGON ((14.999802591641 -24.50175837821, 15.757596662004 -24.499039822288, 15.770908808258 -24.442610026108, 15.80586933214 -24.294632160886, 15.84060088455 -24.14669093206, 15.876099065023 -23.998982180718, 15.910846055559 -23.850993316575, 15.945585244702 -23.702908496289, 15.980265126168 -23.554689000244, 15.991571437709 -23.506591342293, 14.99980409915 -23.51001405806, 14.999802591641 -24.50175837821))",
            "start_time": "2022-10-01T08:48:01+00:00",
            "stop_time": "2022-10-02T08:48:01+00:00",
            "url": "",
            "quicklook": "",
            "filter_dict": {},
        }

        p = product_item_from_dict(p_dict)

        self.assertEqual(p.collection, "S2_MSI_L1C")

    def test_open_product_item(self):
        tmp_json_path = os.path.join(self.tmp_dir_path, "pi.json")
        p_dict = self.p.to_json(tmp_json_path)

        p = open_product_item(tmp_json_path)

        self.assertEqual(p.collection, self.p.collection)

    def test_geometry_Polygon(self):
        p = self.p

        self.assertEqual(p.geometry.wkt, S2_PRODUCT_EXAMPLE["geometry"].wkt)

    def test_geometry_wkt(self):
        p = self.p

        self.assertEqual(p.geometry.wkt, S2_PRODUCT_EXAMPLE["geometry"].wkt)

    def test_geometry_seq(self):
        p = self.p

        self.assertEqual(p.geometry.wkt, S2_PRODUCT_EXAMPLE["geometry"].wkt)

    def test_geometry_invalid(self):
        p = ProductItem(
            constellation=S2_PRODUCT_EXAMPLE["constellation"],
            platform=S2_PRODUCT_EXAMPLE["platform"],
            collection=S2_PRODUCT_EXAMPLE["collection"],
            id=S2_PRODUCT_EXAMPLE["id"],
            url="",
            geometry=12,
            start_time=S2_PRODUCT_EXAMPLE["start_time"],
            stop_time=S2_PRODUCT_EXAMPLE["stop_time"],
            prod_dict=S2_PRODUCT_EXAMPLE["prod_dict"],
        )

        def geometry_property(p):
            p.geometry

        self.assertRaises(ValueError, geometry_property, p)

    def test_plot_geometry(self):
        p = self.p

        p.plot_geometry(padding_type="rel", padding_val=2, geometry_color="y")

    def test_s2_cloud_filter(self):
        p1 = ProductItem(**S2_PRODUCT_EXAMPLE)
        p1.filter_dict = {"cloud_fraction": 20}
        p2 = ProductItem(**S2_PRODUCT_EXAMPLE)
        p2.filter_dict = {"cloud_fraction": 50}
        p_set = ProductItemSet([p1, p2])
        p_set.cloud_filter(30)

        self.assertEqual(
            len(p_set), 1, "Product item set was not filtered, no product removed"
        )

    def test_l8_cloud_filter(self):
        p1 = ProductItem(**L8_PRODUCT_EXAMPLE_1)
        p1.filter_dict = {"cloud_fraction": 20}
        p2 = ProductItem(**L8_PRODUCT_EXAMPLE_2)
        p2.filter_dict = {"cloud_fraction": 10}
        p_set = ProductItemSet([p1, p2])
        p_set.cloud_filter(15)

        self.assertEqual(
            len(p_set), 1, "Product item set was not filtered, no product removed"
        )

    def test_get_path(self):
        p = ProductItem(**S3_PRODUCT_EXAMPLE)
        if os.name == "nt":
            assert (
                p.get_path()
                == r"T:\ECO\EOServer\data\product_archive\data\Sentinel-3\S3B\S3_EFR\2022\05\17\S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002"
            )
        elif socket.gethostname() == "eoserver.npl.co.uk":
            assert (
                p.get_path()
                == r"/mnt/t/data/product_archive/data/Sentinel-3/S3B/S3_EFR/2022/05/17/S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002"
            )
        else:
            assert p.get_path() == os.path.join(
                "T:\\",
                "ECO",
                "EOServer",
                "data",
                "product_archive",
                "data",
                "Sentinel-3",
                "S3B",
                "S3_EFR",
                "2022",
                "05",
                "17",
                "S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002",
            )

    def test_download_product(self):
        with mock.patch.object(
            EODAGCallHandler, "_download_product_EOProduct"
        ) as mock_download_EOProduct, mock.patch.object(
            EODAGCallHandler, "_perform_query"
        ) as mock_perform_query:
            # Make perform_query return a fake EOProduct with matching id
            fake_eoprod = mock.MagicMock(spec=EOProduct)
            fake_eoprod.as_dict.return_value = {"id": self.p.id}
            mock_perform_query.return_value = [fake_eoprod]

            product = self.p.download_product()
            assert (
                mock_download_EOProduct.call_args_list[0][0][0].as_dict()["id"]
                == self.p.id
            )

    def test_set_fs(self):
        self.p.set_fs("t-drive")

        assert isinstance(self.p.filesystem, TdriveFileSystem)

        example_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "examples",
        )
        self.p.set_fs(example_path)

        assert isinstance(self.p.filesystem, LocalFileSystem)

    def test_set_api(self):
        assert isinstance(self.p.api, EODAGCallHandler)
        self.p.set_api(
            api="eodag:cop_dataspace",
        )
        assert isinstance(self.p.api, EODAGCallHandler)

    @patch("scrappi.fs.localfilesystem.os.path.exists", return_value=True)
    @patch("scrappi.product.shutil.copy")
    def test_move_product(self, mock_shutil, mock_exists):
        example_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "examples",
        )
        p = ProductItem(**S3_PRODUCT_EXAMPLE)

        p.move_product(example_path)

        assert isinstance(p.filesystem, LocalFileSystem)
        assert mock_shutil.call_args[0][0] == os.path.join(
            "T:\\",
            "ECO",
            "EOServer",
            "data",
            "product_archive",
            "data",
            "Sentinel-3",
            "S3B",
            "S3_EFR",
            "2022",
            "05",
            "17",
            "S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002",
        )


class TestProductItemSet(unittest.TestCase):
    def setUp(self) -> None:
        s2_product = ProductItem(
            constellation=S2_PRODUCT_EXAMPLE["constellation"],
            platform=S2_PRODUCT_EXAMPLE["platform"],
            collection=S2_PRODUCT_EXAMPLE["collection"],
            id=S2_PRODUCT_EXAMPLE["id"],
            url="",
            geometry=S2_PRODUCT_EXAMPLE["geometry"],
            start_time=S2_PRODUCT_EXAMPLE["start_time"],
            stop_time=S2_PRODUCT_EXAMPLE["stop_time"],
            prod_dict=S2_PRODUCT_EXAMPLE["prod_dict"],
            filter_dict=dict(L8_PRODUCT_EXAMPLE_1["filter_dict"]),
        )

        s3_product = ProductItem(
            constellation=S3_PRODUCT_EXAMPLE["constellation"],
            platform=S3_PRODUCT_EXAMPLE["platform"],
            collection=S3_PRODUCT_EXAMPLE["collection"],
            id=S3_PRODUCT_EXAMPLE["id"],
            url="",
            geometry=S3_PRODUCT_EXAMPLE["geometry"],
            start_time=S3_PRODUCT_EXAMPLE["start_time"],
            stop_time=S3_PRODUCT_EXAMPLE["stop_time"],
            prod_dict=S3_PRODUCT_EXAMPLE["prod_dict"],
            filter_dict=dict(L8_PRODUCT_EXAMPLE_1["filter_dict"]),
        )

        l8_product_1 = ProductItem(
            constellation=L8_PRODUCT_EXAMPLE_1["constellation"],
            platform=L8_PRODUCT_EXAMPLE_1["platform"],
            collection=str(L8_PRODUCT_EXAMPLE_1["collection"]),
            id=str(L8_PRODUCT_EXAMPLE_1["id"]),
            url="",
            geometry=list(L8_PRODUCT_EXAMPLE_1["geometry"]),
            start_time=datetime.fromisoformat(str(L8_PRODUCT_EXAMPLE_1["start_time"])),
            stop_time=datetime.fromisoformat(str(L8_PRODUCT_EXAMPLE_1["stop_time"])),
            prod_dict=dict(L8_PRODUCT_EXAMPLE_1["prod_dict"]),
            filter_dict=dict(L8_PRODUCT_EXAMPLE_1["filter_dict"]),
        )

        l8_product_2 = ProductItem(
            constellation=L8_PRODUCT_EXAMPLE_2["constellation"],
            platform=L8_PRODUCT_EXAMPLE_2["platform"],
            collection=L8_PRODUCT_EXAMPLE_2["collection"],
            id=L8_PRODUCT_EXAMPLE_2["id"],
            url="",
            geometry=L8_PRODUCT_EXAMPLE_2["geometry"],
            start_time=L8_PRODUCT_EXAMPLE_2["start_time"],
            stop_time=L8_PRODUCT_EXAMPLE_2["stop_time"],
            prod_dict=L8_PRODUCT_EXAMPLE_2["prod_dict"],
            filter_dict=dict(L8_PRODUCT_EXAMPLE_1["filter_dict"]),
        )

        l8_product_3 = ProductItem(
            constellation=L8_PRODUCT_EXAMPLE_3["constellation"],
            platform=L8_PRODUCT_EXAMPLE_3["platform"],
            collection=L8_PRODUCT_EXAMPLE_3["collection"],
            id=L8_PRODUCT_EXAMPLE_3["id"],
            url="",
            geometry=L8_PRODUCT_EXAMPLE_3["geometry"],
            start_time=L8_PRODUCT_EXAMPLE_3["start_time"],
            stop_time=L8_PRODUCT_EXAMPLE_3["stop_time"],
            prod_dict=L8_PRODUCT_EXAMPLE_3["prod_dict"],
            filter_dict=dict(L8_PRODUCT_EXAMPLE_1["filter_dict"]),
        )

        self.products = [s3_product, l8_product_1, l8_product_2, l8_product_3]
        letters = string.ascii_lowercase
        self.tmp_dir_name = "tmp_" + "".join(random.choice(letters) for i in range(5))
        self.tmp_dir_path = os.path.join(THIS_DIRECTORY, self.tmp_dir_name)
        os.makedirs(self.tmp_dir_path)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir_path)

    def test___init__(self):
        ps = ProductItemSet(self.products)
        self.assertCountEqual(ps._products, self.products)
        self.assertIsNone(ps._collections)

    def test___len__(self):
        ps = ProductItemSet(self.products)
        self.assertEqual(len(ps), 4)

    def test___getitem__(self):
        ps = ProductItemSet(self.products)
        ps[0].id = S3_PRODUCT_EXAMPLE["id"]

    def test___iter__(self):
        ps = ProductItemSet(self.products)

        exp_ids = [p.id for p in self.products]
        for p, exp_id in zip(ps, exp_ids):
            self.assertEqual(p.id, exp_id)

    def test_to_json(self):
        ps = ProductItemSet(self.products)
        ps_dict = ps.to_json()

        exp_ps_dict = {
            "collections": sorted(["LANDSAT_C2L1", "S3_EFR"]),
            "n_products": 4,
            "longitude_minimum": 7.70076,
            "latitude_minimum": -34.5187,
            "lon_maximum": 44.48843284961724,
            "lat_maximmum": 47.090169109917824,
            "products": [
                {
                    "constellation": "Sentinel-3",
                    "platform": "S3B",
                    "collection": "S3_EFR",
                    "id": "S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002",
                    "geometry": "POLYGON ((21.252 -34.5187, 21.8983 -31.8836, 22.5277 -29.2403, 23.1427 -26.5948, 23.7457 -23.9471, 23.0766 -23.8181, 22.4168 -23.6878, 21.7545 -23.554, 21.095 -23.4188, 20.4393 -23.2775, 19.781 -23.1351, 19.1288 -22.9881, 18.4738 -22.8428, 17.8229 -22.6926, 17.1738 -22.5451, 16.5212 -22.3887, 15.8711 -22.23, 15.2236 -22.0691, 14.5757 -21.9053, 13.9278 -21.7384, 13.2816 -21.5691, 12.6433 -21.3989, 12.0034 -21.2254, 11.3643 -21.0485, 10.5243 -23.6423, 9.63737 -26.2286, 8.698 -28.8061, 7.70076 -31.3688, 8.38884 -31.5712, 9.07972 -31.7691, 9.77638 -31.964, 10.4712 -32.1537, 11.1726 -32.3406, 11.8722 -32.5222, 12.5793 -32.7012, 13.286 -32.8756, 13.9979 -33.0466, 14.7147 -33.2089, 15.4305 -33.3715, 16.1486 -33.5271, 16.871 -33.6842, 17.5955 -33.834, 18.3207 -33.9817, 19.0503 -34.1217, 19.781 -34.2582, 20.5158 -34.3907, 21.252 -34.5187))",
                    "start_time": "2022-05-17T08:32:38+00:00",
                    "stop_time": "2022-05-17T08:35:38+00:00",
                    "url": "",
                    "quicklook": "",
                    "prod_dict": {"val": "entry"},
                    "filter_dict": {"val": "entry"},
                },
                {
                    "constellation": "Landsat",
                    "platform": "LC08",
                    "collection": "LANDSAT_C2L1",
                    "id": "LC08_L1TP_172030_20220120_20220127_02_T2C",
                    "geometry": "POLYGON ((41.0856816815745 44.24112580952904, 41.08680806465548 44.24110522982958, 43.393265796852866 43.82234984482247, 43.39318664569185 43.821272570187, 42.777074012665516 42.11245652952103, 42.777074012665516 42.11245652952103, 40.531355852298944 42.52837451259882, 40.531362450839524 42.52864459095809, 41.0856816815745 44.24112580952904))",
                    "start_time": "2022-06-07T23:40:08.609447+00:00",
                    "stop_time": "2022-06-07T23:45:40.379447+00:00",
                    "url": "",
                    "quicklook": "",
                    "prod_dict": {"val": "entry"},
                    "filter_dict": {"val": "entry"},
                },
                {
                    "constellation": "Landsat",
                    "platform": "LC08",
                    "collection": "LANDSAT_C2L1",
                    "id": "LC08_L1TP_172030_20220120_20220127_02_T2B",
                    "geometry": "POLYGON ((40.17522471269021 41.3861400123577, 40.17558345095594 41.3861363475318, 42.38002952306863 40.978818955572315, 42.38000194853155 40.978279401481856, 41.80764599721697 39.26470702042967, 41.805909323763835 39.26474891065633, 39.65908676451177 39.6694679250438, 39.65908676451177 39.6694679250438, 40.17522471269021 41.3861400123577))",
                    "start_time": "2022-06-07T23:30:08.609447+00:00",
                    "stop_time": "2022-06-07T23:45:40.379447+00:00",
                    "url": "",
                    "quicklook": "",
                    "prod_dict": {"val": "entry"},
                    "filter_dict": {"val": "entry"},
                },
                {
                    "constellation": "Landsat",
                    "platform": "LC08",
                    "collection": "LANDSAT_C2L1",
                    "id": "LC08_L1TP_172030_20220120_20220127_02_T2A",
                    "geometry": "POLYGON ((42.06239725042473 47.09014884645623, 42.063186749290715 47.090169109917824, 44.48843284961724 46.65748606317669, 44.48843284961724 46.65748606317669, 43.81882313084526 44.953559032103655, 43.81806263359167 44.95355116301529, 41.46673146290274 45.381351153094556, 41.46671465356733 45.381620678652574, 42.06239725042473 47.09014884645623))",
                    "start_time": "2022-06-07T23:35:08.609447+00:00",
                    "stop_time": "2022-06-07T23:45:40.379447+00:00",
                    "url": "",
                    "quicklook": "",
                    "prod_dict": {"val": "entry"},
                    "filter_dict": {"val": "entry"},
                },
            ],
        }
        ps_dict["collections"] = sorted(ps_dict["collections"])
        self.assertDictEqual(ps_dict, exp_ps_dict)

    def test_to_json_path(self):
        tmp_json_path = os.path.join(self.tmp_dir_path, "pis.json")

        ps = ProductItemSet(self.products)
        ps_dict = ps.to_json(tmp_json_path)

        exp_ps_dict = {
            "collections": ["LANDSAT_C2L1", "S3_EFR"],
            "n_products": 4,
            "longitude_minimum": 7.70076,
            "latitude_minimum": -34.5187,
            "lon_maximum": 44.48843284961724,
            "lat_maximmum": 47.090169109917824,
            "products": [
                {
                    "constellation": "Sentinel-3",
                    "platform": "S3B",
                    "collection": "S3_EFR",
                    "id": "S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002",
                    "geometry": "POLYGON ((21.252 -34.5187, 21.8983 -31.8836, 22.5277 -29.2403, 23.1427 -26.5948, 23.7457 -23.9471, 23.0766 -23.8181, 22.4168 -23.6878, 21.7545 -23.554, 21.095 -23.4188, 20.4393 -23.2775, 19.781 -23.1351, 19.1288 -22.9881, 18.4738 -22.8428, 17.8229 -22.6926, 17.1738 -22.5451, 16.5212 -22.3887, 15.8711 -22.23, 15.2236 -22.0691, 14.5757 -21.9053, 13.9278 -21.7384, 13.2816 -21.5691, 12.6433 -21.3989, 12.0034 -21.2254, 11.3643 -21.0485, 10.5243 -23.6423, 9.63737 -26.2286, 8.698 -28.8061, 7.70076 -31.3688, 8.38884 -31.5712, 9.07972 -31.7691, 9.77638 -31.964, 10.4712 -32.1537, 11.1726 -32.3406, 11.8722 -32.5222, 12.5793 -32.7012, 13.286 -32.8756, 13.9979 -33.0466, 14.7147 -33.2089, 15.4305 -33.3715, 16.1486 -33.5271, 16.871 -33.6842, 17.5955 -33.834, 18.3207 -33.9817, 19.0503 -34.1217, 19.781 -34.2582, 20.5158 -34.3907, 21.252 -34.5187))",
                    "start_time": "2022-05-17T08:32:38+00:00",
                    "stop_time": "2022-05-17T08:35:38+00:00",
                    "url": "",
                    "quicklook": "",
                    "prod_dict": {"val": "entry"},
                    "filter_dict": {"val": "entry"},
                },
                {
                    "constellation": "Landsat",
                    "platform": "LC08",
                    "collection": "LANDSAT_C2L1",
                    "id": "LC08_L1TP_172030_20220120_20220127_02_T2C",
                    "geometry": "POLYGON ((41.0856816815745 44.24112580952904, 41.08680806465548 44.24110522982958, 43.393265796852866 43.82234984482247, 43.39318664569185 43.821272570187, 42.777074012665516 42.11245652952103, 42.777074012665516 42.11245652952103, 40.531355852298944 42.52837451259882, 40.531362450839524 42.52864459095809, 41.0856816815745 44.24112580952904))",
                    "start_time": "2022-06-07T23:40:08.609447+00:00",
                    "stop_time": "2022-06-07T23:45:40.379447+00:00",
                    "url": "",
                    "quicklook": "",
                    "prod_dict": {"val": "entry"},
                    "filter_dict": {"val": "entry"},
                },
                {
                    "constellation": "Landsat",
                    "platform": "LC08",
                    "collection": "LANDSAT_C2L1",
                    "id": "LC08_L1TP_172030_20220120_20220127_02_T2B",
                    "geometry": "POLYGON ((40.17522471269021 41.3861400123577, 40.17558345095594 41.3861363475318, 42.38002952306863 40.978818955572315, 42.38000194853155 40.978279401481856, 41.80764599721697 39.26470702042967, 41.805909323763835 39.26474891065633, 39.65908676451177 39.6694679250438, 39.65908676451177 39.6694679250438, 40.17522471269021 41.3861400123577))",
                    "start_time": "2022-06-07T23:30:08.609447+00:00",
                    "stop_time": "2022-06-07T23:45:40.379447+00:00",
                    "url": "",
                    "quicklook": "",
                    "prod_dict": {"val": "entry"},
                    "filter_dict": {"val": "entry"},
                },
                {
                    "constellation": "Landsat",
                    "platform": "LC08",
                    "collection": "LANDSAT_C2L1",
                    "id": "LC08_L1TP_172030_20220120_20220127_02_T2A",
                    "geometry": "POLYGON ((42.06239725042473 47.09014884645623, 42.063186749290715 47.090169109917824, 44.48843284961724 46.65748606317669, 44.48843284961724 46.65748606317669, 43.81882313084526 44.953559032103655, 43.81806263359167 44.95355116301529, 41.46673146290274 45.381351153094556, 41.46671465356733 45.381620678652574, 42.06239725042473 47.09014884645623))",
                    "start_time": "2022-06-07T23:35:08.609447+00:00",
                    "stop_time": "2022-06-07T23:45:40.379447+00:00",
                    "url": "",
                    "quicklook": "",
                    "prod_dict": {"val": "entry"},
                    "filter_dict": {"val": "entry"},
                },
            ],
        }

        self.assertDictEqual(ps_dict, exp_ps_dict)
        self.assertTrue(tmp_json_path)

    def test_product_item_set_from_dict(self):
        ps_dict = {
            "collections": ["S3_EFR", "LANDSAT_C2L1"],
            "n_products": 4,
            "longitude_minimum": 7.70076,
            "latitude_minimum": -34.5187,
            "lon_maximum": 44.48843284961724,
            "lat_maximmum": 47.090169109917824,
            "products": [
                {
                    "constellation": "Sentinel-3",
                    "platform": "S3B",
                    "collection": "S3_EFR",
                    "id": "S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002",
                    "geometry": "POLYGON ((21.252 -34.5187, 21.8983 -31.8836, 22.5277 -29.2403, 23.1427 -26.5948, 23.7457 -23.9471, 23.0766 -23.8181, 22.4168 -23.6878, 21.7545 -23.554, 21.095 -23.4188, 20.4393 -23.2775, 19.781 -23.1351, 19.1288 -22.9881, 18.4738 -22.8428, 17.8229 -22.6926, 17.1738 -22.5451, 16.5212 -22.3887, 15.8711 -22.23, 15.2236 -22.0691, 14.5757 -21.9053, 13.9278 -21.7384, 13.2816 -21.5691, 12.6433 -21.3989, 12.0034 -21.2254, 11.3643 -21.0485, 10.5243 -23.6423, 9.63737 -26.2286, 8.698 -28.8061, 7.70076 -31.3688, 8.38884 -31.5712, 9.07972 -31.7691, 9.77638 -31.964, 10.4712 -32.1537, 11.1726 -32.3406, 11.8722 -32.5222, 12.5793 -32.7012, 13.286 -32.8756, 13.9979 -33.0466, 14.7147 -33.2089, 15.4305 -33.3715, 16.1486 -33.5271, 16.871 -33.6842, 17.5955 -33.834, 18.3207 -33.9817, 19.0503 -34.1217, 19.781 -34.2582, 20.5158 -34.3907, 21.252 -34.5187))",
                    "start_time": "2022-05-17T08:32:38+00:00",
                    "stop_time": "2022-05-17T08:35:38+00:00",
                    "url": "",
                    "quicklook": "",
                    "filter_dict": {},
                },
                {
                    "constellation": "Landsat-8",
                    "platform": "LC08",
                    "collection": "LANDSAT_C2L1",
                    "id": "LC08_L1TP_172030_20220120_20220127_02_T2C",
                    "geometry": "POLYGON ((41.0856816815745 44.24112580952904, 41.08680806465548 44.24110522982958, 43.393265796852866 43.82234984482247, 43.39318664569185 43.821272570187, 42.777074012665516 42.11245652952103, 42.777074012665516 42.11245652952103, 40.531355852298944 42.52837451259882, 40.531362450839524 42.52864459095809, 41.0856816815745 44.24112580952904))",
                    "start_time": "2022-06-07T23:40:08.609447+00:00",
                    "stop_time": "2022-06-07T23:45:40.379447+00:00",
                    "url": "",
                    "quicklook": "",
                    "filter_dict": {},
                },
                {
                    "constellation": "Landsat-8",
                    "platform": "LC08",
                    "collection": "LANDSAT_C2L1",
                    "id": "LC08_L1TP_172030_20220120_20220127_02_T2B",
                    "geometry": "POLYGON ((40.17522471269021 41.3861400123577, 40.17558345095594 41.3861363475318, 42.38002952306863 40.978818955572315, 42.38000194853155 40.978279401481856, 41.80764599721697 39.26470702042967, 41.805909323763835 39.26474891065633, 39.65908676451177 39.6694679250438, 39.65908676451177 39.6694679250438, 40.17522471269021 41.3861400123577))",
                    "start_time": "2022-06-07T23:30:08.609447+00:00",
                    "stop_time": "2022-06-07T23:45:40.379447+00:00",
                    "url": "",
                    "quicklook": "",
                    "filter_dict": {},
                },
                {
                    "constellation": "Landsat-8",
                    "platform": "LC08",
                    "collection": "LANDSAT_C2L1",
                    "id": "LC08_L1TP_172030_20220120_20220127_02_T2A",
                    "geometry": "POLYGON ((42.06239725042473 47.09014884645623, 42.063186749290715 47.090169109917824, 44.48843284961724 46.65748606317669, 44.48843284961724 46.65748606317669, 43.81882313084526 44.953559032103655, 43.81806263359167 44.95355116301529, 41.46673146290274 45.381351153094556, 41.46671465356733 45.381620678652574, 42.06239725042473 47.09014884645623))",
                    "start_time": "2022-06-07T23:35:08.609447+00:00",
                    "stop_time": "2022-06-07T23:45:40.379447+00:00",
                    "url": "",
                    "quicklook": "",
                    "filter_dict": {},
                },
            ],
        }

        ps = product_item_set_from_dict(ps_dict)

        self.assertCountEqual(ps.collections, ["S3_EFR", "LANDSAT_C2L1"])
        self.assertEqual(len(ps_dict["products"]), len(ps._products))

    def test_open_product_item_set(self):
        tmp_json_path = os.path.join(self.tmp_dir_path, "pis.json")

        exp_ps = ProductItemSet(self.products)
        ps_dict = exp_ps.to_json(tmp_json_path)

        ps = open_product_item_set(tmp_json_path)

        self.assertCountEqual(ps.collections, exp_ps.collections)
        self.assertEqual(len(ps_dict["products"]), len(ps._products))

    def test_collections(self):
        ps = ProductItemSet(self.products)

        self.assertCountEqual(
            ps.collections,
            [S3_PRODUCT_EXAMPLE["collection"], L8_PRODUCT_EXAMPLE_1["collection"]],
        )

    def test_append_ProductItemSet(self):
        ps = ProductItemSet(self.products)
        ps2 = ProductItemSet(self.products)
        ps.append_ProductItemSet(ps2)
        self.assertEqual(len(ps._products), 8)

    def test_collections_preset(self):
        ps = ProductItemSet(self.products)
        ps._collections = "test"

        self.assertEqual(ps.collections, "test")

    def test_product_bounds(self):
        ps = ProductItemSet(self.products)

        self.assertCountEqual(
            ps.product_bounds,
            (7.70076, -34.5187, 44.48843284961724, 47.090169109917824),
        )

    def test_argsort_collection(self):
        exp_idx = [1, 2, 3, 0]

        idx = ProductItemSet(self.products).argsort(sort_by="collection")

        self.assertCountEqual(exp_idx, idx)

    def test_argsort_id(self):
        exp_idx = [3, 2, 1, 0]

        idx = ProductItemSet(self.products).argsort(sort_by="id")

        self.assertCountEqual(exp_idx, idx)

    def test_argsort_start_time(self):
        exp_idx = [2, 3, 1, 0]

        idx = ProductItemSet(self.products).argsort(sort_by="start_time")

        self.assertCountEqual(exp_idx, idx)

    def test_argsort_area(self):
        exp_idx = [1, 2, 3, 0]

        idx = ProductItemSet(self.products).argsort(sort_by="area")

        self.assertCountEqual(exp_idx, idx)

    def test_argsort_invalid(self):
        self.assertRaises(
            ValueError, ProductItemSet(self.products).argsort, sort_by="invalid"
        )

    @patch("scrappi.product.ProductItemSet.argsort", return_value=[3, 2, 1, 0])
    def test_sort(self, mock_argsort):
        ps = ProductItemSet(self.products)

        ps.sort(sort_by="value")
        mock_argsort.assert_called_once_with(sort_by="value")

        self.assertCountEqual(
            [p.id for p in ps._products],
            [
                "LC08_L1TP_172030_20220120_20220127_02_T2A",
                "LC08_L1TP_172030_20220120_20220127_02_T2B",
                "LC08_L1TP_172030_20220120_20220127_02_T2C",
                "S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002",
            ],
        )

    def test_plot_geometries(self):
        ps = ProductItemSet(self.products)
        ps.plot_geometries(padding_type="rel", padding_val=0.5, label_by="id")
        plt.clf()

    def test_set_fs(self):
        ps = ProductItemSet(self.products)

        assert isinstance(ps[0].filesystem, STACFileSystem)

        example_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "examples",
        )
        ps.set_fs(example_path)

        assert isinstance(ps[0].filesystem, LocalFileSystem)

    def test_set_api(self):
        ps = ProductItemSet(self.products)

        assert isinstance(ps[0].api, EODAGCallHandler)
        ps.set_api("eodag")

        assert isinstance(ps[0].api, EODAGCallHandler)

    @patch("scrappi.fs.localfilesystem.os.path.exists", return_value=True)
    @patch("scrappi.product.shutil.copy")
    def test_move_product(self, mock_shutil, mock_exists):
        ps = ProductItemSet(self.products)
        ps.set_fs("t-drive")
        example_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "examples",
        )
        ps.move_product(example_path)

        assert isinstance(ps[0].filesystem, LocalFileSystem)
        assert mock_shutil.call_args[0][0] == os.path.join(
            "T:\\",
            "ECO",
            "EOServer",
            "data",
            "product_archive",
            "data",
            "Landsat",
            "LC08",
            "LANDSAT_C2L1",
            "2022",
            "06",
            "07",
            "LC08_L1TP_172030_20220120_20220127_02_T2A",
        )

    def test_get_path(self):
        ps = ProductItemSet(self.products)
        ps.set_fs("t-drive")
        if os.name == "nt":
            assert (
                ps.get_path()[0]
                == r"T:\ECO\EOServer\data\product_archive\data\Sentinel-3\S3B\S3_EFR\2022\05\17\S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002"
            )
        if socket.gethostname() == "eoserver.npl.co.uk":
            assert (
                ps.get_path()[0]
                == r"/mnt/t/data/product_archive/data/Sentinel-3/S3B/S3_EFR/2022/05/17/S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002"
            )
        else:
            assert ps.get_path()[0] == os.path.join(
                "T:\\",
                "ECO",
                "EOServer",
                "data",
                "product_archive",
                "data",
                "Sentinel-3",
                "S3B",
                "S3_EFR",
                "2022",
                "05",
                "17",
                "S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002",
            )

    def test_download_product(self):
        ps = ProductItemSet(self.products)
        ps.set_fs("t-drive")
        example_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "examples",
        )
        ps.set_fs(self.tmp_dir_path)
        with mock.patch.object(
            EODAGCallHandler, "download_product"
        ) as mock_download_EOProduct:
            product = ps.download_product()
            assert mock_download_EOProduct.call_args_list[0][0][0].id == ps[0].id

    def test_plot_geometry(self):
        p = ProductItem(
            constellation=S3_PRODUCT_EXAMPLE["constellation"],
            platform=S3_PRODUCT_EXAMPLE["platform"],
            collection=S3_PRODUCT_EXAMPLE["collection"],
            id=S3_PRODUCT_EXAMPLE["id"],
            geometry=S3_PRODUCT_EXAMPLE["geometry"],
            start_time=S3_PRODUCT_EXAMPLE["start_time"],
            stop_time=S3_PRODUCT_EXAMPLE["stop_time"],
            prod_dict=S3_PRODUCT_EXAMPLE["prod_dict"],
        )

        p.plot_geometry(padding_type="rel", padding_val=2, geometry_color="y")
        plt.show()


import unittest
import json
import datetime as dt
from pathlib import Path
from tempfile import TemporaryDirectory

from shapely.geometry import box

from scrappi.product import ProductItem
from scrappi.fs.stac_href_resolver import StacHrefResolver
from scrappi.fs.stacfilesystem import STACFileSystem


# ---------------------------------------------------------------------
# Base test class
# ---------------------------------------------------------------------
class BaseStacTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

        self.fs = STACFileSystem(self.root)

    def tearDown(self):
        self.tmpdir.cleanup()

    def make_product(
        self,
        item_id: str,
        bounds,
        start_time,
        stop_time=None,
        collection="TEST_COLLECTION",
    ):
        geom = box(*bounds)

        return ProductItem(
            constellation="TEST",
            platform="PLATFORM",
            collection=collection,
            id=item_id,
            geometry=geom,
            start_time=start_time,
            stop_time=stop_time or start_time,
            filesystem=self.fs,
            url="asset://",
        )


class TestStacCatalog(BaseStacTest):

    def test_item_written_with_logical_hrefs(self):
        p = self.make_product(
            "item-1",
            bounds=(0, 0, 1, 1),
            start_time="2025-01-01T00:00:00Z",
        )

        item_path = p.register_in_filesystem_catalog()
        item_json = Path(item_path)

        self.assertTrue(item_json.exists())

        data = json.loads(item_json.read_text())

        self.assertEqual(data["id"], "item-1")

        # Logical self link
        self.assertTrue(
            any(l["href"].startswith("stac://") for l in data.get("links", []))
        )

        # Logical asset href
        asset_href = data["assets"]["data"]["href"]
        self.assertTrue(asset_href.startswith("asset://"))

    def test_collection_links_items(self):
        p = self.make_product(
            "item-1",
            bounds=(0, 0, 1, 1),
            start_time="2025-01-01T00:00:00Z",
        )

        p.register_in_filesystem_catalog()

        collection_json = (
            Path(self.fs.stac_root) / "TEST_COLLECTION" / "collection.json"
        )

        self.assertTrue(collection_json.exists())

        data = json.loads(collection_json.read_text())

        item_links = [l for l in data["links"] if l["rel"] == "item"]

        self.assertEqual(len(item_links), 1)
        self.assertTrue(item_links[0]["href"].startswith("stac://"))

    def test_collection_extent_expands_with_multiple_items(self):
        p1 = self.make_product(
            "item-1",
            bounds=(0, 0, 1, 1),
            start_time="2025-01-01T00:00:00Z",
        )

        p2 = self.make_product(
            "item-2",
            bounds=(10, 10, 12, 12),
            start_time="2025-01-10T00:00:00Z",
        )

        p1.register_in_filesystem_catalog()
        p2.register_in_filesystem_catalog()

        collection_json = (
            Path(self.fs.stac_root) / "TEST_COLLECTION" / "collection.json"
        )

        data = json.loads(collection_json.read_text())

        bbox = data["extent"]["spatial"]["bbox"][0]
        interval = data["extent"]["temporal"]["interval"][0]

        # Spatial extent union
        self.assertEqual(bbox, [0, 0, 12, 12])

        # Temporal extent union
        self.assertTrue(interval[0].startswith("2025-01-01"))
        self.assertTrue(interval[1].startswith("2025-01-10"))

    def test_root_catalog_links_collection_once(self):
        p = self.make_product(
            "item-1",
            bounds=(0, 0, 1, 1),
            start_time="2025-01-01T00:00:00Z",
        )

        p.register_in_filesystem_catalog()

        catalog_json = Path(self.fs.stac_root) / "catalog.json"
        self.assertTrue(catalog_json.exists())

        data = json.loads(catalog_json.read_text())

        child_links = [l for l in data["links"] if l["rel"] == "child"]

        self.assertEqual(len(child_links), 1)
        self.assertTrue(child_links[0]["href"].startswith("stac://collections/"))

    # -----------------------------------------------------------------

    def test_no_os_paths_leak_into_json(self):
        p = self.make_product(
            "item-1",
            bounds=(0, 0, 1, 1),
            start_time="2025-01-01T00:00:00Z",
        )

        p.register_in_filesystem_catalog()

        for json_file in Path(self.fs.stac_root).rglob("*.json"):
            text = json_file.read_text()

            self.assertNotIn("C:\\", text)
            self.assertNotIn("/home/", text)
            self.assertTrue(("stac://" in text) or ("asset://" in text) or ("http://"))


if __name__ == "__main__":
    unittest.main()
