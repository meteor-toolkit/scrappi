import os
import re
import requests
from requests.exceptions import SSLError
import unittest
import unittest.mock as mock
from datetime import datetime as dt, timedelta, timezone
import shutil
import pytest

import requests.exceptions

from scrappi.api.radcalnet_api_client import RadcalnetCallHandler
from scrappi.utils.utils import convert_geom_shapely

__author__ = [
    "Ashley Ramsay <ashley.ramsay@npl.co.uk",
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
]
__all__ = ["MockSession", "MockSessionError", "MockGetError", "MockGet"]

scrappi_folder = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

example_download_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "examples",
    "downloaded_data",
)

# scrappi does not make directory, ensure directory is present
if not os.path.exists(example_download_path):
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
    "GONA01_2022_314_v04.09.output",
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

    def test_check_date_in_range_matches_same_calendar_day(self):
        """Regression test: a query window entirely within one calendar day must
        match that day's own file (doy is 1-indexed, e.g. 1 Jan = 1), not the
        day before. check_date_in_range used to compute its internal doy1/doy2
        boundaries as 0-indexed (days elapsed since 1 Jan 00:00), silently
        shifting every match one day earlier than the file it should have found."""
        self.rcnHandler = RadcalnetCallHandler()
        # 15 March 2024 (leap year) = day-of-year 75 (1-indexed); a satellite-overpass
        # query window buffered several hours either side, but still same-day.
        date1 = dt(2024, 3, 15, 4, 30)
        date2 = dt(2024, 3, 15, 16, 30)
        self.assertTrue(self.rcnHandler.check_date_in_range(2024, 75, date1, date2))
        self.assertFalse(self.rcnHandler.check_date_in_range(2024, 74, date1, date2))
        self.assertFalse(self.rcnHandler.check_date_in_range(2024, 76, date1, date2))

    def test_check_date_in_range_matches_first_and_last_day_of_year(self):
        """Boundary check: 1 Jan (doy=1) and 31 Dec must each still match a
        same-day query window -- the ends of the 1-indexed doy1/doy2 fix."""
        self.rcnHandler = RadcalnetCallHandler()
        jan1 = dt(2024, 1, 1, 0, 0)
        jan1_end = dt(2024, 1, 1, 23, 59, 59)
        self.assertTrue(self.rcnHandler.check_date_in_range(2024, 1, jan1, jan1_end))

        dec31 = dt(2024, 12, 31, 0, 0)
        dec31_end = dt(2024, 12, 31, 23, 59, 59)
        # 2024 is a leap year: 31 Dec = day-of-year 366
        self.assertTrue(self.rcnHandler.check_date_in_range(2024, 366, dec31, dec31_end))

    def test_check_date_in_range_wide_window_still_excludes_out_of_range_days(self):
        """A multi-month query window should still exclude days clearly outside it,
        confirming the +1 fix didn't just make everything match."""
        self.rcnHandler = RadcalnetCallHandler()
        date1 = dt(2022, 10, 10)
        date2 = dt(2022, 11, 10)
        # 10 Oct 2022 = doy 283, 10 Nov 2022 = doy 314
        self.assertTrue(self.rcnHandler.check_date_in_range(2022, 283, date1, date2))
        self.assertTrue(self.rcnHandler.check_date_in_range(2022, 314, date1, date2))
        self.assertFalse(self.rcnHandler.check_date_in_range(2022, 282, date1, date2))
        self.assertFalse(self.rcnHandler.check_date_in_range(2022, 315, date1, date2))

    def test_parse_name(self):
        version_pattern = re.compile("v*.*.output")

        self.rcnHandler = RadcalnetCallHandler()
        site, year, doy, version = self.rcnHandler.parse_name("GONA01_2017_200_v04.09.output")
        self.assertEqual(site, "GONA01")
        self.assertEqual(year, 2017)
        self.assertEqual(doy, 200)
        self.assertTrue(re.search(version_pattern, version))

    def test_daylight_window_hours_matches_original_hardcoded_window_for_gona(self):
        """Regression/consistency check: the per-site window this replaces a
        hardcoded 08:00-14:00 UTC window that was only ever really correct
        for GONA (its local solar noon happens to fall in the middle of that
        range) -- confirms the longitude-based computation reproduces it."""
        self.rcnHandler = RadcalnetCallHandler()
        start_hour, stop_hour = self.rcnHandler._daylight_window_hours("GONA")
        self.assertAlmostEqual(start_hour, 8.0, delta=0.1)
        self.assertAlmostEqual(stop_hour, 14.0, delta=0.1)

    def test_daylight_window_hours_shifts_for_a_western_site(self):
        """RVUS (115.69 degW) is far enough west of GONA (15.12 degE) that
        its real daylight window falls many hours later in UTC -- this is
        the site/scenario the hardcoded 08:00-14:00 window was silently
        wrong for (see also eomatch's Sat2InSituMUFinder.to_matchup_set,
        which rejects candidate matchups whose products fall outside this
        window plus a tolerance)."""
        self.rcnHandler = RadcalnetCallHandler()
        start_hour, stop_hour = self.rcnHandler._daylight_window_hours("RVUS")
        self.assertAlmostEqual(start_hour, 16.71, delta=0.1)
        self.assertAlmostEqual(stop_hour, 22.71, delta=0.1)

    def test_daylight_window_hours_is_six_hours_wide_for_every_site(self):
        self.rcnHandler = RadcalnetCallHandler()
        for site in self.rcnHandler.DEFAULT_SITE_DEFINITIONS:
            start_hour, stop_hour = self.rcnHandler._daylight_window_hours(site)
            self.assertAlmostEqual(stop_hour - start_hour, 6.0, delta=1e-9)

    def test_perform_query_products_use_per_site_daylight_window(self):
        """End-to-end: perform_query()'s constructed ProductItems carry each
        product's site-appropriate window, not the old universal 08:00-14:00."""
        self.rcnHandler = RadcalnetCallHandler()
        with mock.patch.object(self.rcnHandler, "get_files_list", return_value=["RVUS01_2025_334_v04.09.output"]):
            products = self.rcnHandler.perform_query(
                {
                    "collection": "RCN_TOA",
                    "site": "RVUS",
                    "start_time": dt(2025, 11, 30),
                    "stop_time": dt(2025, 12, 1),
                }
            )

        self.assertEqual(len(products), 1)
        product = list(products)[0]
        start_hour, stop_hour = self.rcnHandler._daylight_window_hours("RVUS")
        expected_start = (dt(2025, 1, 1) + timedelta(days=333, hours=start_hour)).replace(tzinfo=timezone.utc)
        expected_stop = (dt(2025, 1, 1) + timedelta(days=333, hours=stop_hour)).replace(tzinfo=timezone.utc)
        self.assertEqual(product.start_time, expected_start)
        self.assertEqual(product.stop_time, expected_stop)

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

            for test_collection, stated_collection in zip(test_collections_output, ["RCN_TOA", "RCN_BOA"]):
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

    def test_site_size(self):
        # make shapely files to compare with
        shapes = {
            "BSCN": convert_geom_shapely(
                {
                    "longitude_minimum": 109.61374874265117,
                    "latitude_minimum": 40.864427753168556,
                    "longitude_maximum": 109.61725132962366,
                    "latitude_maximum": 40.86717222107943,
                }
            ),
            "BTCN": convert_geom_shapely(
                {
                    "longitude_minimum": 109.62916162640767,
                    "latitude_minimum": 40.85126126573982,
                    "longitude_maximum": 109.6292783736726,
                    "latitude_maximum": 40.851352734231575,
                }
            ),
            "GONA": convert_geom_shapely(
                {
                    "longitude_minimum": 15.117107578351696,
                    "latitude_minimum": -23.602461051102456,
                    "longitude_maximum": 15.122004337734927,
                    "latitude_maximum": -23.597940909979695,
                }
            ),
            "LCFR": convert_geom_shapely(
                {
                    "longitude_minimum": 4.863787427354276,
                    "latitude_minimum": 43.55862507162645,
                    "longitude_maximum": 4.864546575957476,
                    "latitude_maximum": 43.55915292704115,
                }
            ),
            "RVUS": convert_geom_shapely(
                {
                    "longitude_minimum": -115.69581358554443,
                    "latitude_minimum": 38.49255908632671,
                    "longitude_maximum": -115.68418570083671,
                    "latitude_maximum": 38.50144060902196,
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
