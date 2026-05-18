import os, re
import requests
from requests.exceptions import SSLError
import unittest
import unittest.mock as mock
import datetime
from datetime import datetime as dt
import shutil
import pytest

import requests.exceptions

from scrappi.api.radcalnet_api_client import RadcalnetCallHandler
from scrappi.utils.utils import convert_geom_shapely

__author__ = ["Ashley Ramsay <ashley.ramsay@npl.co.uk",
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
]
__all__ = ["MockSession", "MockSessionError", "MockGetError", "MockGet"]

scrappi_folder = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
)

example_download_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "examples",
    "downloaded_data",
)

# scrappi does not make directory, ensure directory is present
if os.path.exists(example_download_path) == False:
    os.mkdir(example_download_path)

product_list = [
    "GONA01_2022_291_v04.09.output",
    "GONA01_2022_292_v04.09.output",
    "GONA01_2022_294_v04.09.output",
    "GONA01_2022_296_v04.09.output",
    "GONA01_2022_299_v04.09.output",
    "GONA01_2022_300_v04.09.output",
    "GONA01_2022_301_v04.09.output",
    "GONA01_2022_302_v04.09.output",
    "GONA01_2022_306_v04.09.output",
    "GONA01_2022_307_v04.09.output",
    "GONA01_2022_308_v04.09.output",
    "GONA01_2022_313_v04.09.output",
]


class MockSession:
    def get(self, url):
        return MockGet(url)


class MockSessionError:
    def get(self, url):
        return MockGetError()


class MockGet:
    def __init__(self, url):
        pass

    def raise_for_status(self):
        pass

    def json(self):
        return [
            {"name": "GONA01_2022_289_v04.09.output"},
            {"name": "GONA01_2022_290_v04.09.output"},
        ]  # since parse_name returns a usable output this can be junk


class MockGetError:
    def raise_for_status(self):
        raise requests.exceptions.HTTPError


class TestRCNCallHandler(unittest.TestCase):
    def test_initialise(self):
        self.rcnHandler = RadcalnetCallHandler()

    @mock.patch("requests.session", return_value=MockSession())
    def test_file_list(self, mock_session):
        self.rcnHandler = RadcalnetCallHandler()

        date1 = dt(2022, 10, 10)
        date2 = dt(2022, 11, 10)
        filtered_list = self.rcnHandler.get_files_list("GONA", "GONA_TOA", date1, date2)
        self.assertListEqual(
            filtered_list,
            ["GONA01_2022_289_v04.09.output", "GONA01_2022_290_v04.09.output"],
        )

    def test_parse_name(self):
        version_pattern = re.compile("v*.*.output")

        self.rcnHandler = RadcalnetCallHandler()
        site, year, doy, version = self.rcnHandler.parse_name(
            "GONA01_2017_200_v04.09.output"
        )
        self.assertEqual(site, "GONA01")
        self.assertEqual(year, 2017)
        self.assertEqual(doy, 200)
        self.assertTrue(re.search(version_pattern, version))

    @pytest.mark.slow
    def test_download_product(self):
        self.rcnHandler = RadcalnetCallHandler()
        # test_data_path = os.path.join(r"C:\Users", "ar17", "Data", "insitu", "scrappi_test")

        date1 = dt(2022, 10, 10)
        date2 = dt(2022, 11, 10)
        products = self.rcnHandler.perform_query(
            {
                "collection": "RCN_TOA",
                "site": "GONA",
                "start_time": date1,
                "stop_time": date2,
            }
        )
        products.set_fs(example_download_path)
        path_list = self.rcnHandler.download_product(products)
        file_list = [os.path.basename(file) for file in path_list]
        self.assertEqual(file_list, product_list)

        # clean up files
        for f in file_list:
            if os.path.exists(os.path.join(example_download_path, f)):
                os.remove(os.path.join(example_download_path, f))

        # delete empty directory
        shutil.rmtree(example_download_path)

    def test_list_collections(self):
        self.rcnHandler = RadcalnetCallHandler()
        try:
            test_collections_output = self.rcnHandler.list_collections()

            for test_collection, stated_collection in zip(
                test_collections_output, ["RCN_TOA", "RCN_BOA"]
            ):
                self.assertEqual(test_collection, stated_collection)

        except SSLError as err:
            print("SSL Error detected, this is expected if running via the NPL LAN")
            print(err)

    def test_list_sites(self):
        self.rcnHandler = RadcalnetCallHandler()
        try:
            test_collections_output = self.rcnHandler.list_sites()

            for test_collection, stated_collection in zip(
                test_collections_output,
                ["GONA", "BTCN", "BSCN", "LCFR", "RVUS", "GHNA"],
            ):
                self.assertEqual(test_collection, stated_collection)

        except SSLError as err:
            print("SSL Error detected, this is expected if running via the NPL LAN")
            print(err)

    # "BSCN": convert_geom_shapely(
    # [(109.6181134, 40.86734998), (109.6175416, 40.86381612),
    # (109.612886896779, 40.86424995), (109.6134581, 40.86778386), (109.6181134, 40.86734998)]),
    # "BTCN": convert_geom_shapely(
    # [(109.6293071, 40.85135863), (109.629288, 40.85124087),
    # (109.6291329, 40.85125537),	(109.629152,40.85137313), (109.6293071, 40.85135863)]),
    # "GONA": convert_geom_shapely(
    # [(15.11465119, 23.59568831), (15.12445257, 23.59568076),
    # (15.12446109, 23.6047135),  (15.11465905, 23.60472105), (15.11465119, 23.59568831)]),
    # "RVUS": convert_geom_shapely(
    # [(4.863345627, 43.55935528), (4.864808188, 43.55948632), (4.86498836, 43.55842271),
    # (4.863525825, 43.55829168), (4.863345627, 43.55935528)]),
    # "LCFR": convert_geom_shapely(
    # [(-115.6879503, 38.48687306), (-115.7028871, 38.49538812), (-115.6920493, 38.50712799),
    # (-115.6771133, 38.49860936), (-115.6879503, 38.48687306)])

    def test_site_size(self):
        # make shapely files to compare with
        shapes = {
            "BSCN": convert_geom_shapely(
                {
                    "longitude_minimum": 109.6151061872157,
                    "latitude_minimum": 40.86446369669309,
                    "longitude_maximum": 109.61589376182471,
                    "latitude_maximum": 40.867136318760544,
                }
            ),
            "BTCN": convert_geom_shapely(
                {
                    "longitude_minimum": 109.62920690365492,
                    "latitude_minimum": 40.8512624569282,
                    "longitude_maximum": 109.62923309628796,
                    "latitude_maximum": 40.851351543088896,
                }
            ),
            "GONA": convert_geom_shapely(
                {
                    "longitude_minimum": 15.117532788744471,
                    "latitude_minimum": -23.602627898833834,
                    "longitude_maximum": 15.121579092331926,
                    "latitude_maximum": -23.59777408779308,
                }
            ),
            "LCFR": convert_geom_shapely(
                {
                    "longitude_minimum": 4.863764033960914,
                    "latitude_minimum": 43.55864688771256,
                    "longitude_maximum": 4.864569969233603,
                    "latitude_maximum": 43.559131110606714,
                }
            ),
            "RVUS": convert_geom_shapely(
                {
                    "longitude_minimum": -115.695507468333,
                    "latitude_minimum": 38.49614047027827,
                    "longitude_maximum": -115.68449303343614,
                    "latitude_maximum": 38.49785907324905,
                }
            ),
        }
        self.rcnHandler = RadcalnetCallHandler()

        self.rcnHandler._set_Polygons()
        for site in ["BSCN", "BTCN", "GONA", "LCFR", "RVUS"]:
            # test initially failed due to rounding error - test to 5dp
            for i in range(len(shapes[site].bounds)):
                self.assertAlmostEqual(
                    self.rcnHandler._default_geometries[site].bounds[i],
                    shapes[site].bounds[i],
                    places=5,
                )


if __name__ == "__main__":
    unittest.main()
