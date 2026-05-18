"""scrappi.fs.tests.test_localarchive - tests for scrappi.fs.local_archive"""

import unittest
from unittest.mock import patch
from scrappi.fs.localfilesystem import LocalFileSystem
from scrappi.fs.stacfilesystem import STACFileSystem
from scrappi import ScrappiContext
from datetime import datetime
from scrappi.product import ProductItem
from shapely.geometry import Polygon
import os

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
    "Harry Morris <harry.morris@npl.co.uk>",
]

L8_PRODUCT_EXAMPLE_1 = {
    "constellation": "Landsat",
    "platform": "LC08",
    "collection": "LANDSAT_C2L1",
    "id": "LC08_L1TP_172030_20220120_20220127_02_T2B",
    "geometry": Polygon(
        [
            (40.17522471269021, 41.3861400123577),
            (40.17558345095594, 41.3861363475318),
            (42.38002952306863, 40.978818955572315),
            (42.38000194853155, 40.978279401481856),
            (41.80764599721697, 39.26470702042967),
            (41.805909323763835, 39.26474891065633),
            (39.65908676451177, 39.6694679250438),
            (39.65908676451177, 39.6694679250438),
            (40.17522471269021, 41.3861400123577),
        ]
    ),
    "start_time": datetime(2022, 6, 7, 23, 30, 8, 609447),
    "stop_time": datetime(2022, 6, 7, 23, 45, 40, 379447),
    "prod_dict": {"val": "entry"},
}

example_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "examples",
)


class TestLocalFileSystem(unittest.TestCase):
    def test_return_path(self):
        test_prod = ProductItem(
            constellation=L8_PRODUCT_EXAMPLE_1["constellation"],
            platform=L8_PRODUCT_EXAMPLE_1["platform"],
            collection=L8_PRODUCT_EXAMPLE_1["collection"],
            id=L8_PRODUCT_EXAMPLE_1["id"],
            geometry=L8_PRODUCT_EXAMPLE_1["geometry"],
            start_time=L8_PRODUCT_EXAMPLE_1["start_time"],
            stop_time=L8_PRODUCT_EXAMPLE_1["stop_time"],
            prod_dict=L8_PRODUCT_EXAMPLE_1["prod_dict"],
            url="",
        )

        local_fs = LocalFileSystem(example_path)
        path = local_fs.return_path(test_prod, False)
        self.assertEqual(
            path,
            os.path.join(
                example_path,
                "Landsat",
                "LC08",
                "LANDSAT_C2L1",
                "2022",
                "06",
                "07",
                "LC08_L1TP_172030_20220120_20220127_02_T2B",
            ),
        )


class TestSTACFileSystem(unittest.TestCase):
    def test_return_path(self):
        test_prod = ProductItem(
            constellation=L8_PRODUCT_EXAMPLE_1["constellation"],
            platform=L8_PRODUCT_EXAMPLE_1["platform"],
            collection=L8_PRODUCT_EXAMPLE_1["collection"],
            id=L8_PRODUCT_EXAMPLE_1["id"],
            geometry=L8_PRODUCT_EXAMPLE_1["geometry"],
            start_time=L8_PRODUCT_EXAMPLE_1["start_time"],
            stop_time=L8_PRODUCT_EXAMPLE_1["stop_time"],
            prod_dict=L8_PRODUCT_EXAMPLE_1["prod_dict"],
            url="",
        )

        stac_fs = STACFileSystem(example_path)
        path = stac_fs.return_path(test_prod, False)
        self.assertEqual(
            path,
            os.path.join(
                example_path,
                "data",
                "Landsat",
                "LC08",
                "LANDSAT_C2L1",
                "2022",
                "06",
                "07",
                "LC08_L1TP_172030_20220120_20220127_02_T2B",
            ),
        )

        path_stac = stac_fs.return_stac_item_path(test_prod, False)
        self.assertEqual(
            path_stac,
            os.path.join(
                example_path,
                "stac",
                "LANDSAT_C2L1",
                "items",
                "2022",
                "06",
                "07",
                "LC08_L1TP_172030_20220120_20220127_02_T2B.json",
            ),
        )
        stac_fs = STACFileSystem(
            os.path.join(example_path, "data"), os.path.join(example_path, "stac")
        )
        path = stac_fs.return_path(test_prod, False)
        self.assertEqual(
            path,
            os.path.join(
                example_path,
                "data",
                "Landsat",
                "LC08",
                "LANDSAT_C2L1",
                "2022",
                "06",
                "07",
                "LC08_L1TP_172030_20220120_20220127_02_T2B",
            ),
        )

        path_stac = stac_fs.return_stac_item_path(test_prod, False)
        self.assertEqual(
            path_stac,
            os.path.join(
                example_path,
                "stac",
                "LANDSAT_C2L1",
                "items",
                "2022",
                "06",
                "07",
                "LC08_L1TP_172030_20220120_20220127_02_T2B.json",
            ),
        )


if __name__ == "__main__":
    unittest.main()


# class TestLocalFileSystem(unittest.TestCase):
#     def setUp(self) -> None:
#         l8_product_1 = ProductItem(
#             collection=L8_PRODUCT_EXAMPLE_1["collection"],
#             id=L8_PRODUCT_EXAMPLE_1["id"],
#             geometry=L8_PRODUCT_EXAMPLE_1["geometry"],
#             start_time=L8_PRODUCT_EXAMPLE_1["start_time"],
#             stop_time=L8_PRODUCT_EXAMPLE_1["stop_time"],
#             prod_dict=L8_PRODUCT_EXAMPLE_1["prod_dict"],
#         )
#
#         # dummy helper class to test BaseFSCallHandler class
#         class DummyFSCallHandler(LocalFileSystem):
#             def return_path(self, product_info: l8_product_1, check_exists: bool = False):
#
#
#                 pass
#
#         self.DummyFSCallHandler = DummyFSCallHandler
#
#
#     # Dummy test to be deleted when I submit the merge request
#     def test_get_value_gen(self):
#         input_1 = [("Ground_Floor", "A1")]
#         output_1 = [("Ground_Floor", "A1")]
#
#         self.assertEqual(input_1,output_1)
#
#
#     #print(l8_product_1.start_time.strftime("%d"))
#     #print(l8_product_1.start_time.strftime("%m"))
#     #print(l8_product_1.start_time.strftime("%Y"))
#     def test_return_path(self):
#         example = LocalFileSystem.return_path(l8_product_1,False)
#         print(example)
#     # def test_subclass_builds(self) -> None:
#     #     dummy_fs_call_handler = self.DummyFSCallHandler(directory="test")
#
#
# if __name__ == "__main__":
#     unittest.main()
