import os
import re
import requests
from requests.exceptions import SSLError
import unittest
import unittest.mock as mock
import warnings
from datetime import datetime as dt, timedelta, timezone
import shutil
import pytest
from tempfile import TemporaryDirectory

import requests.exceptions

from scrappi import ScrappiContext
from scrappi.api.radcalnet_api_client import RadcalnetCallHandler, RadcalnetOfflineCallHandler
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
    def get(self, url, **kwargs):
        return MockGet(url)


class MockSessionError:
    def get(self, url, **kwargs):
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

    @mock.patch("requests.session")
    def test_get_files_list_passes_a_request_timeout(self, mock_session):
        """Regression test: the file-list GET must carry a timeout -- without one, a
        request to an unresponsive server (e.g. for a site the portal doesn't host but
        that a user added via context["RadCalNet"]["site_definitions"]) hangs the whole
        run forever, and eodag's signal handling means Ctrl-C won't break out of it."""
        session = mock_session.return_value
        session.get.return_value = MockGet("url")
        RadcalnetCallHandler().get_files_list("GONA", "GONA_TOA", dt(2022, 10, 10), dt(2022, 11, 10))
        self.assertTrue(session.get.call_args.kwargs.get("timeout"))

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

    def test_get_roi_shapely_raises_a_helpful_error_for_an_unregistered_site(self):
        """A site that isn't a scrappi built-in and hasn't been added to
        context['RadCalNet']['site_definitions'] used to fail with a bare
        ``KeyError: '<site>'`` from ``roi_dict[site]``, deep in insitubase.py. The
        error now names the site, lists the known ones, and points at the config."""
        handler = RadcalnetCallHandler()
        with self.assertRaises(KeyError) as ctx:
            handler.get_roi("ERUS")
        message = str(ctx.exception)
        self.assertIn("ERUS", message)
        self.assertIn("site_definitions", message)

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
        #
        # These bounds are generated with generate_bounding_lat_lon's local
        # Azimuthal Equidistant projection (its default), which preserves true
        # ground distance from the site's centre point in every direction --
        # each site's box is a true default_roi*2 metre square (verified
        # geodesically), unlike the previous fixed-CRS (EPSG:32630, UTM zone
        # 30N) default, which was only accurate near that zone's own meridian
        # and produced a badly non-square box far from it (e.g. RVUS's
        # nominal 1000m x 1000m square previously came out ~960m x ~190m).
        shapes = {
            "BSCN": convert_geom_shapely(
                {
                    "longitude_minimum": 109.6137207949809,
                    "latitude_minimum": 40.86444925920302,
                    "longitude_maximum": 109.61727927732053,
                    "latitude_maximum": 40.86715071303549,
                }
            ),
            "BTCN": convert_geom_shapely(
                {
                    "longitude_minimum": 109.62916070492611,
                    "latitude_minimum": 40.85126197564054,
                    "longitude_maximum": 109.62927929515419,
                    "latitude_maximum": 40.851352024328634,
                }
            ),
            "GONA": convert_geom_shapely(
                {
                    "longitude_minimum": 15.11710650612445,
                    "latitude_minimum": -23.602458266106517,
                    "longitude_maximum": 15.12200541002855,
                    "latitude_maximum": -23.597943694603075,
                }
            ),
            "LCFR": convert_geom_shapely(
                {
                    "longitude_minimum": 4.863795705480817,
                    "latitude_minimum": 43.558618981217094,
                    "longitude_maximum": 4.864538297835298,
                    "latitude_maximum": 43.55915901756431,
                }
            ),
            "RVUS": convert_geom_shapely(
                {
                    "longitude_minimum": -115.69573119658749,
                    "latitude_minimum": 38.49249559303247,
                    "longitude_maximum": -115.6842680896183,
                    "latitude_maximum": 38.50150412301871,
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


class TestRCNCredentials(unittest.TestCase):
    """Credentials reach the session from the config, or else from the environment variables."""

    ENV = {"RADCALNET_USERNAME": "env_user", "RADCALNET_REMOVED_PASSWORD": "env_pass"}

    @staticmethod
    def _context(username=None, password=None):
        # unset values, as in the default config
        context = ScrappiContext()
        context["RadCalNet"]["credentials"] = {"username": username, "password": password}
        return context

    def test_environment_variables_are_used_when_the_config_credentials_are_unset(self):
        with mock.patch.dict(os.environ, self.ENV):
            handler = RadcalnetCallHandler(self._context())
        self.assertEqual(handler.session.auth, ("env_user", "env_pass"))

    def test_config_credentials_take_priority_over_the_environment(self):
        with mock.patch.dict(os.environ, self.ENV):
            handler = RadcalnetCallHandler(self._context("cfg_user", "cfg_pass"))
        self.assertEqual(handler.session.auth, ("cfg_user", "cfg_pass"))

    def test_username_and_password_can_come_from_different_places(self):
        with mock.patch.dict(os.environ, self.ENV):
            handler = RadcalnetCallHandler(self._context(username="cfg_user"))
        self.assertEqual(handler.session.auth, ("cfg_user", "env_pass"))

    def test_no_credentials_anywhere_gives_an_unauthenticated_session_without_a_warning(self):
        env = {k: v for k, v in os.environ.items() if k not in self.ENV}
        with mock.patch.dict(os.environ, env, clear=True), warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            handler = RadcalnetCallHandler(self._context())
        self.assertIsNone(handler.session.auth)
        self.assertEqual([w for w in caught if "RADCALNET" in str(w.message)], [])

    def test_config_credentials_do_not_warn(self):
        with mock.patch.dict(os.environ, {}), warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            RadcalnetCallHandler(self._context("cfg_user", "cfg_pass"))
        self.assertEqual([w for w in caught if "RADCALNET" in str(w.message)], [])

    @mock.patch("requests.session")
    def test_a_401_response_raises_an_error_that_says_how_to_provide_credentials(self, mock_session):
        mock_session.return_value.get.return_value = mock.Mock(status_code=401)
        handler = RadcalnetCallHandler(self._context())
        with self.assertRaisesRegex(requests.exceptions.HTTPError, "RADCALNET_USERNAME"):
            handler.get_files_list("GONA", "GONA_TOA", dt(2022, 10, 10), dt(2022, 11, 10))


class TestRadcalnetOfflineCallHandler(unittest.TestCase):
    """Tests for RadcalnetOfflineCallHandler -- resolving RadCalNet products from a
    local archive rather than the online API. See RadcalnetOfflineCallHandler's own
    docstring for the archive-layout rationale (any directory tree, matched purely by
    filename, not location)."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.archive_path = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, *path_parts):
        """Create an empty file at os.path.join(self.archive_path, *path_parts),
        creating any intermediate directories -- content is irrelevant, perform_query
        only inspects the filename."""
        full_path = os.path.join(self.archive_path, *path_parts)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w"):
            pass
        return full_path

    def test_list_collections(self):
        handler = RadcalnetOfflineCallHandler(archive_path=self.archive_path)
        self.assertEqual(handler.list_collections(), ["RCN_TOA", "RCN_BOA"])

    def test_perform_query_finds_matching_file_in_nested_directory(self):
        """Archive layout mirrors the online API's own {site}/data/{filename}
        convention -- perform_query must search recursively, not just archive_path's
        top level."""
        self._write("GONA", "data", "GONA01_2022_291_v04.09.output")
        handler = RadcalnetOfflineCallHandler(archive_path=self.archive_path)

        products = handler.perform_query(
            {
                "collection": "RCN_TOA",
                "site": "GONA",
                "start_time": dt(2022, 10, 1),
                "stop_time": dt(2022, 11, 1),
            }
        )

        self.assertEqual(len(products), 1)
        product = list(products)[0]
        self.assertEqual(product.id, "GONA01_2022_291_v04.09.output")

    def test_perform_query_filters_toa_vs_boa_by_filename_suffix(self):
        # RadCalNet: .output = modelled TOA reflectance, .input = measured surface (BOA)
        # -- same mapping as the online handler and eoio's own RadCalNet reader.
        self._write("GONA01_2022_291_v04.09.output")
        self._write("GONA01_2022_291_v04.09.input")
        handler = RadcalnetOfflineCallHandler(archive_path=self.archive_path)
        query = {"site": "GONA", "start_time": dt(2022, 10, 1), "stop_time": dt(2022, 11, 1)}

        toa_products = handler.perform_query({**query, "collection": "RCN_TOA"})
        boa_products = handler.perform_query({**query, "collection": "RCN_BOA"})

        self.assertEqual([p.id for p in toa_products], ["GONA01_2022_291_v04.09.output"])
        self.assertEqual([p.id for p in boa_products], ["GONA01_2022_291_v04.09.input"])

    def test_perform_query_skips_files_for_other_sites(self):
        self._write("GONA01_2022_291_v04.09.output")
        self._write("RVUS01_2022_291_v04.09.output")
        handler = RadcalnetOfflineCallHandler(archive_path=self.archive_path)

        products = handler.perform_query(
            {"collection": "RCN_TOA", "site": "GONA", "start_time": dt(2022, 10, 1), "stop_time": dt(2022, 11, 1)}
        )

        self.assertEqual([p.id for p in products], ["GONA01_2022_291_v04.09.output"])

    def test_perform_query_skips_non_rcn_named_files(self):
        """A file that doesn't parse via the site_instrument_year_doy_version
        convention (e.g. a checksum or readme) is silently skipped, not an error."""
        self._write("GONA01_2022_291_v04.09.output")
        self._write("README.md")
        self._write("checksums.sha256")
        handler = RadcalnetOfflineCallHandler(archive_path=self.archive_path)

        products = handler.perform_query(
            {"collection": "RCN_TOA", "site": "GONA", "start_time": dt(2022, 10, 1), "stop_time": dt(2022, 11, 1)}
        )

        self.assertEqual([p.id for p in products], ["GONA01_2022_291_v04.09.output"])

    def test_perform_query_respects_date_range(self):
        self._write("GONA01_2022_291_v04.09.output")  # 18 Oct 2022
        self._write("GONA01_2023_291_v04.09.output")  # 18 Oct 2023 -- out of range
        handler = RadcalnetOfflineCallHandler(archive_path=self.archive_path)

        products = handler.perform_query(
            {"collection": "RCN_TOA", "site": "GONA", "start_time": dt(2022, 10, 1), "stop_time": dt(2022, 11, 1)}
        )

        self.assertEqual([p.id for p in products], ["GONA01_2022_291_v04.09.output"])

    def test_perform_query_returns_empty_when_archive_path_missing(self):
        missing_path = os.path.join(self.archive_path, "does-not-exist")
        handler = RadcalnetOfflineCallHandler(archive_path=missing_path)

        with self.assertWarns(UserWarning):
            products = handler.perform_query(
                {
                    "collection": "RCN_TOA",
                    "site": "GONA",
                    "start_time": dt(2022, 10, 1),
                    "stop_time": dt(2022, 11, 1),
                }
            )

        self.assertEqual(len(products), 0)

    def test_perform_query_keeps_only_the_newest_version_of_each_day(self):
        """An accumulating archive keeps several reprocessings of the same day; the
        online portal exposes only the latest, so the offline handler must dedup."""
        self._write("GONA01_2022_291_v04.08.output")
        self._write("GONA01_2022_291_v04.09.output")
        self._write("GONA01_2022_291_v04.10.output")  # newest -- string-sorts below v04.9
        self._write("GONA01_2022_292_v04.09.output")  # a different day, kept as-is
        handler = RadcalnetOfflineCallHandler(archive_path=self.archive_path)

        products = handler.perform_query(
            {"collection": "RCN_TOA", "site": "GONA", "start_time": dt(2022, 10, 1), "stop_time": dt(2022, 11, 1)}
        )

        self.assertEqual(
            sorted(p.id for p in products),
            ["GONA01_2022_291_v04.10.output", "GONA01_2022_292_v04.09.output"],
        )

    def test_perform_query_returns_empty_for_unregistered_site(self):
        self._write("ZZZZ01_2022_291_v04.09.output")
        handler = RadcalnetOfflineCallHandler(archive_path=self.archive_path)

        with self.assertWarns(UserWarning):
            products = handler.perform_query(
                {
                    "collection": "RCN_TOA",
                    "site": "ZZZZ",
                    "start_time": dt(2022, 10, 1),
                    "stop_time": dt(2022, 11, 1),
                }
            )

        self.assertEqual(len(products), 0)

    def test_perform_query_finds_offline_only_site_registered_via_context(self):
        """A site with no built-in entry (e.g. a newer RCN site not yet on the online
        portal) becomes discoverable purely by adding it to
        context['RadCalNet']['site_definitions'] -- no code change needed."""
        self._write("NEWS01_2024_100_v04.09.output")
        context = ScrappiContext()
        context["RadCalNet"]["site_definitions"] = {"NEWS": {"latitude": 10.0, "longitude": 20.0, "default_roi": 100}}
        handler = RadcalnetOfflineCallHandler(context=context, archive_path=self.archive_path)

        products = handler.perform_query(
            {"collection": "RCN_TOA", "site": "NEWS", "start_time": dt(2024, 1, 1), "stop_time": dt(2024, 12, 31)}
        )

        self.assertEqual([p.id for p in products], ["NEWS01_2024_100_v04.09.output"])

    def test_archive_path_resolves_from_context_when_not_passed_explicitly(self):
        context = ScrappiContext()
        context["RadCalNet"]["offline_archive_path"] = self.archive_path
        handler = RadcalnetOfflineCallHandler(context=context)
        self.assertEqual(handler.archive_path, self.archive_path)

    def test_explicit_archive_path_overrides_context(self):
        context = ScrappiContext()
        context["RadCalNet"]["offline_archive_path"] = "/some/other/path"
        handler = RadcalnetOfflineCallHandler(context=context, archive_path=self.archive_path)
        self.assertEqual(handler.archive_path, self.archive_path)

    def test_construction_does_not_mutate_the_shared_context(self):
        """The handler must not flip context['fs']['organise_data'] on the shared
        context object -- that leaks to every other handler and download in the run.
        The per-product filesystem is built flat instead."""
        context = ScrappiContext()
        before = context["fs"]["organise_data"]
        RadcalnetOfflineCallHandler(context=context, archive_path=self.archive_path)
        self.assertEqual(context["fs"]["organise_data"], before)

    def test_perform_query_product_filesystem_is_flat(self):
        self._write("GONA", "data", "GONA01_2022_291_v04.09.output")
        handler = RadcalnetOfflineCallHandler(archive_path=self.archive_path)
        product = list(
            handler.perform_query(
                {"collection": "RCN_TOA", "site": "GONA", "start_time": dt(2022, 10, 1), "stop_time": dt(2022, 11, 1)}
            )
        )[0]
        product.filesystem = product.set_fs(product.filesystem_init)  # ensure it's a LocalFileSystem, not None
        self.assertFalse(product.filesystem.organise_data)

    def test_download_product_resolves_existing_file_without_network(self):
        file_path = self._write("GONA", "data", "GONA01_2022_291_v04.09.output")
        handler = RadcalnetOfflineCallHandler(archive_path=self.archive_path)
        products = handler.perform_query(
            {"collection": "RCN_TOA", "site": "GONA", "start_time": dt(2022, 10, 1), "stop_time": dt(2022, 11, 1)}
        )

        path = handler.download_product(products)

        self.assertEqual(len(path), 1)
        self.assertEqual(os.path.normpath(path[0]), os.path.normpath(file_path))

    def test_download_product_relocates_file_for_a_product_with_no_filesystem(self):
        """A product rebuilt from a STAC catalogue (eomatch's product_item_from_stac)
        arrives with no filesystem/API config -- download_product must re-locate the
        file under archive_path by filename, not trust product.filesystem."""
        file_path = self._write("ERUS", "2023", "08", "30", "ERUS00_2023_242_v00.04.input")
        context = ScrappiContext()
        context["RadCalNet"]["site_definitions"] = {
            "ERUS": {"latitude": 43.738, "longitude": -96.6304, "default_roi": 45}
        }
        handler = RadcalnetOfflineCallHandler(context=context, archive_path=self.archive_path)
        product = list(
            handler.perform_query(
                {"collection": "RCN_BOA", "site": "ERUS", "start_time": dt(2023, 1, 1), "stop_time": dt(2023, 12, 31)}
            )
        )[0]
        product.filesystem = None  # as if freshly rebuilt from a STAC item

        path = handler.download_product(product)

        self.assertEqual(os.path.normpath(path), os.path.normpath(file_path))
        # filesystem is repinned so get_path()/STAC registration work afterwards
        self.assertEqual(os.path.normpath(product.get_path()), os.path.normpath(file_path))

    def test_download_product_raises_when_file_not_in_archive(self):
        context = ScrappiContext()
        context["RadCalNet"]["site_definitions"] = {
            "ERUS": {"latitude": 43.738, "longitude": -96.6304, "default_roi": 45}
        }
        handler = RadcalnetOfflineCallHandler(context=context, archive_path=self.archive_path)
        self._write("ERUS", "2023", "08", "30", "ERUS00_2023_242_v00.04.input")
        product = list(
            handler.perform_query(
                {"collection": "RCN_BOA", "site": "ERUS", "start_time": dt(2023, 1, 1), "stop_time": dt(2023, 12, 31)}
            )
        )[0]
        product.id = "ERUS00_2023_999_v00.04.input"  # not in the archive

        with self.assertRaises(FileNotFoundError):
            handler.download_product(product)

    def test_product_can_be_converted_to_a_stac_item(self):
        """Regression test: adding an offline-archive matchup to a catalogue calls
        ProductItem.to_stac_item(), which needs the product's filesystem to expose
        return_stac_item_path (a STACFileSystem method) and to resolve the archive
        file relative to its own data_root. A plain LocalFileSystem raised
        AttributeError; STACFileSystem with the default <dir>/data/ layout raised
        ValueError on the relative_to."""
        file_path = self._write("ERUS", "2023", "02", "15", "ERUS01_2023_046_v04.09.input")
        context = ScrappiContext()
        context["RadCalNet"]["site_definitions"] = {
            "ERUS": {"latitude": 43.738, "longitude": -96.6304, "default_roi": 45}
        }
        handler = RadcalnetOfflineCallHandler(context=context, archive_path=self.archive_path)
        products = handler.perform_query(
            {"collection": "RCN_BOA", "site": "ERUS", "start_time": dt(2023, 1, 1), "stop_time": dt(2023, 3, 1)}
        )
        self.assertEqual(len(products), 1)

        item = products[0].to_stac_item()

        self.assertEqual(item.id, "ERUS01_2023_046_v04.09.input")
        # the on-disk file still resolves for a (networkless) download
        self.assertEqual(os.path.normpath(products[0].get_path()), os.path.normpath(file_path))

    def test_offline_product_filesystem_is_read_only(self):
        """The archive is the user's, not scrappi's to write to -- see
        test_registering_offline_product_raises_instead_of_writing_into_the_archive."""
        self._write("GONA", "data", "GONA01_2022_291_v04.09.output")
        handler = RadcalnetOfflineCallHandler(archive_path=self.archive_path)
        product = handler.perform_query(
            {"collection": "RCN_TOA", "site": "GONA", "start_time": dt(2022, 10, 1), "stop_time": dt(2022, 11, 1)}
        )[0]

        product.filesystem = product.set_fs(product.filesystem_init)  # ensure it's a LocalFileSystem, not None
        self.assertTrue(product.filesystem.read_only)

    def test_download_product_keeps_the_filesystem_read_only(self):
        """download_product re-pins product.filesystem; the read-only protection
        perform_query set must survive that re-pin."""
        self._write("GONA", "data", "GONA01_2022_291_v04.09.output")
        handler = RadcalnetOfflineCallHandler(archive_path=self.archive_path)
        product = handler.perform_query(
            {"collection": "RCN_TOA", "site": "GONA", "start_time": dt(2022, 10, 1), "stop_time": dt(2022, 11, 1)}
        )[0]

        handler.download_product(product)

        self.assertTrue(product.filesystem.read_only)

    def test_registering_offline_product_raises_instead_of_writing_into_the_archive(self):
        """Regression test: ProductItem.register_in_filesystem_catalog() defaults to
        product.filesystem, and an offline handler's product.filesystem is pinned
        *inside the archive itself* (flat mode). Without a read-only check this
        silently created a stac/ folder inside the user's RadCalNet archive -- not
        the matchup catalogue -- every time scrappi.interface.download_product()
        auto-registered a downloaded product (the default,
        context['fs']['register_stac_items'] is True)."""
        self._write("GONA", "data", "GONA01_2022_291_v04.09.output")
        handler = RadcalnetOfflineCallHandler(archive_path=self.archive_path)
        product = handler.perform_query(
            {"collection": "RCN_TOA", "site": "GONA", "start_time": dt(2022, 10, 1), "stop_time": dt(2022, 11, 1)}
        )[0]

        with self.assertRaises(IOError):
            product.register_in_filesystem_catalog()

        self.assertFalse(os.path.exists(os.path.join(self.archive_path, "GONA", "data", "stac")))


if __name__ == "__main__":
    unittest.main()
