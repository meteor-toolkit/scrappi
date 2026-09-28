"""scrappi.tests.test_interface - tests for scrappi.interface"""

import os
import random
import shutil
import string
import threading
import unittest
import datetime as dt
import numpy as np
import numpy.testing as npt

from unittest import mock
from shapely.geometry import Point, Polygon
from scrappi.product import ProductItem
from scrappi.interface import (
    Factory,
    _ensure_scrappi_context,
    download_product,
    download_product_filename,
    download_product_scene,
    generate_bounding_box,
    get_api_name,
    is_insitu_collection,
    list_collections,
    make_api,
    make_fs,
    make_query_with_tolerance,
    perform_query,
    set_credentials,
    update_context_file,
)
import scrappi.interface as interface_module
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
        # Avoid a stale entry from an earlier test's (by-then-garbage-collected)
        # context object whose id() happens to be reused within this same run --
        # see _ensure_scrappi_context's own docstring on why the cache holds a
        # reference to prevent that in real usage; tests don't hold one that long.
        interface_module._context_wrap_cache = {}

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

        # Cleared *after* the ProductItem above, whose __init__ calls set_api()
        # (and so, eventually, Factory.get_api_call_handler("eodag")) unconditionally
        # -- clearing before it would still leave a real, unmocked "eodag" handler
        # cached from here by the time a test's own mock.patch.dict(Factory.
        # api_call_handlers, ...) takes effect. Several tests below also reuse the
        # same mock name (e.g. "handle1") across different test methods, which
        # would otherwise resolve to a previous test's stale cached mock instance.
        Factory.clear_cache()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir_path)

    def test_get_api_name_single(self):
        context = ScrappiContext()
        context["api"]["preferred_api"] = None
        m = mock.MagicMock()
        m().list_collections.return_value = ["LANDSAT_C2L1"]
        with (
            mock.patch.dict(
                "scrappi.interface.Factory.api_call_handlers", {"handle1": m}, clear=True
            ) as _mock_handlers,
            mock.patch(
                "scrappi.interface.Factory.all_api_list",
                ["handle1"],
            ) as _mock_all_api_list,
        ):
            self.assertEqual(get_api_name("LANDSAT_C2L1", context=context), "handle1")

    def test_get_api_name_all(self):
        context = ScrappiContext()
        context["api"]["preferred_api"] = None
        m = mock.MagicMock()
        m().list_collections.return_value = ["LANDSAT_C2L1"]
        with (
            mock.patch.dict(
                "scrappi.interface.Factory.api_call_handlers",
                {"handle1": m, "handle2": m},
                clear=True,
            ) as _mock_handlers,
            mock.patch(
                "scrappi.interface.Factory.all_api_list",
                ["handle1", "handle2"],
            ) as _mock_all_api_list,
        ):
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
        ) as _mock_handlers:
            self.assertEqual(get_api_name("S2_MSI_L1C", context=context), None)

    def test_get_api_name_accepts_a_non_scrappicontext_truthy_context(self):
        """Regression test: a caller may pass a non-ScrappiContext object as
        *context* (e.g. eomatch's own EOMatchContext, or a plain populated dict) --
        get_api_name used to only normalise a falsy context (`if not context:`),
        so a truthy-but-wrong-type context skipped ScrappiContext() construction
        entirely and crashed on context["api"]["preferred_api"] (that key isn't
        populated with scrappi's own defaults on an arbitrary object). A plain
        dict is truthy the same way a populated EOMatchContext is, so it
        reproduces the same failure mode without needing eomatch installed."""
        context = {"platforms": "S2A,GONA", "collections": "S2_MSI_L1C,RCN_BOA", "api": {"preferred_api": None}}
        m = mock.MagicMock()
        m().list_collections.return_value = ["LANDSAT_C2L1"]
        with (
            mock.patch.dict(
                "scrappi.interface.Factory.api_call_handlers", {"handle1": m}, clear=True
            ) as _mock_handlers,
            mock.patch(
                "scrappi.interface.Factory.all_api_list",
                ["handle1"],
            ) as _mock_all_api_list,
        ):
            self.assertEqual(get_api_name("LANDSAT_C2L1", context=context), "handle1")
            self.assertEqual(get_api_name("LANDSAT_C2L1", context=context, all_apis=True), ["handle1"])

    def test_get_api_name_does_not_hang_on_a_processor_tools_context(self):
        """Regression test: a bare processor_tools.Context (e.g. eomatch's
        EOMatchContext, handed straight to get_api_name by
        Sat2InSituMUFinder.identify_mu_events) must be unwrapped to its values dict
        before ScrappiContext() construction. Context.__init__ treats a non-(str|dict)
        config as a sequence and does ``list(config)`` -- and ``list()`` on a Context
        never terminates, because Context.__getitem__ returns None (not IndexError) for
        the integer indices the sequence protocol probes. get_api_name used to hang here
        forever with no way to Ctrl-C out (eodag installs its own signal handling)."""
        from processor_tools import Context

        context = Context(
            {"platforms": "S2A,GONA", "collections": "S2_MSI_L1C,RCN_BOA", "api": {"preferred_api": None}}
        )
        m = mock.MagicMock()
        m().list_collections.return_value = ["LANDSAT_C2L1"]
        result = {}

        def _run():
            with (
                mock.patch.dict("scrappi.interface.Factory.api_call_handlers", {"handle1": m}, clear=True),
                mock.patch("scrappi.interface.Factory.all_api_list", ["handle1"]),
            ):
                result["value"] = get_api_name("LANDSAT_C2L1", context=context, all_apis=True)

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(timeout=15)
        self.assertFalse(worker.is_alive(), "get_api_name hung on a processor_tools.Context")
        self.assertEqual(result.get("value"), ["handle1"])

    def test_make_api_accepts_a_non_scrappicontext_truthy_context(self):
        """Same regression as test_get_api_name_accepts_a_non_scrappicontext_truthy_context,
        for make_api -- it reads context["api"]["preferred_api"] itself when *api*
        isn't given explicitly."""
        context = {"platforms": "S2A,GONA", "collections": "S2_MSI_L1C,RCN_BOA"}
        m = mock.MagicMock()
        with mock.patch.dict("scrappi.interface.Factory.api_call_handlers", {"handle1": m}, clear=True):
            make_api("handle1", context=context)
        m.assert_called_once()

    def test_make_fs_accepts_a_non_scrappicontext_truthy_context(self):
        """Same regression as test_get_api_name_accepts_a_non_scrappicontext_truthy_context,
        for make_fs -- it reads context["fs"]["path"] itself when *fs* isn't given."""
        context = {"platforms": "S2A,GONA", "collections": "S2_MSI_L1C,RCN_BOA"}
        fs = make_fs(self.tmp_dir_path, context=context)
        self.assertEqual(os.path.normpath(fs.directory), os.path.normpath(self.tmp_dir_path))

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
        with mock.patch.dict("scrappi.interface.Factory.api_call_handlers", {"api": m}, clear=True) as _mock_handlers:
            make_api("api", context)
            m.assert_called_with(context=context)

    def test_make_fs(self):
        context = ScrappiContext()
        context["fs"]["path"] = "fs"
        m = mock.MagicMock()
        with mock.patch.dict("scrappi.interface.FSFactory.fs_call_handlers", {"fs": m}, clear=True) as _mock_handlers:
            make_fs("fs", context)
            m.assert_called_with(context=context)

    def test_ensure_scrappi_context_passes_through_a_real_scrappicontext_unchanged(self):
        context = ScrappiContext()
        self.assertIs(_ensure_scrappi_context(context), context)

    def test_ensure_scrappi_context_wraps_a_non_scrappicontext_object(self):
        """A plain dict (standing in for e.g. eomatch's own EOMatchContext -- any
        non-ScrappiContext, config-like object) is wrapped into a real
        ScrappiContext, not just checked for truthiness -- a falsy check alone
        (the pre-fix behaviour) would pass a truthy-but-wrong-type object straight
        through unwrapped and crash later on e.g. context["api"]["preferred_api"],
        since it doesn't carry scrappi's own defaults.yaml."""
        raw = {"platforms": "S2A,GONA"}
        wrapped = _ensure_scrappi_context(raw)
        self.assertIsInstance(wrapped, ScrappiContext)
        self.assertIsNot(wrapped, raw)

    def test_ensure_scrappi_context_reuses_the_same_wrapped_instance(self):
        """The core fix: repeated calls with the *same* raw, non-ScrappiContext
        object -- the normal case, a caller builds one context once and reuses it
        for every query in a run -- must get back the *same* wrapped
        ScrappiContext each time, not a fresh one. Without this,
        APICallHandlerFactory.get_api_call_handler's own context-identity handler
        cache never hits for a caller (e.g. eomatch's run_scrappi) that always
        passes such an object through perform_query/make_api, since each call
        would otherwise see a differently-identified wrapper."""
        raw = {"platforms": "S2A,GONA"}
        first = _ensure_scrappi_context(raw)
        second = _ensure_scrappi_context(raw)
        self.assertIs(first, second)

    def test_ensure_scrappi_context_different_raw_objects_get_different_wrappers(self):
        first = _ensure_scrappi_context({"platforms": "S2A,GONA"})
        second = _ensure_scrappi_context({"platforms": "S2A,GONA"})
        self.assertIsNot(first, second)

    def test_ensure_scrappi_context_none_is_stable_across_calls_too(self):
        """context=None (the default for every caller that doesn't build its own)
        must also get back the same wrapped instance every time -- two separate
        perform_query calls, one for search and one for download, each passing
        context=None, should still let the factory cache share one handler."""
        first = _ensure_scrappi_context(None)
        second = _ensure_scrappi_context(None)
        self.assertIs(first, second)

    def test_make_api_reuses_one_handler_across_repeated_calls_with_a_raw_context(self):
        """End-to-end: make_api (as perform_query/download_product call it) reuses
        one cached handler across repeated calls that all pass the *same* raw,
        non-ScrappiContext object -- the actual fix this module exists for, proven
        through the real (unmocked) _ensure_scrappi_context -> Factory chain rather
        than just the wrapping helper in isolation."""
        Factory.clear_cache()
        raw_context = {"platforms": "S2A,GONA"}

        first = make_api("radcalnet", raw_context)
        second = make_api("radcalnet", raw_context)

        self.assertIs(first, second)

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
        with (
            mock.patch.dict(
                "scrappi.interface.Factory.api_call_handlers",
                {"handle1": m, "handle2": m},
                clear=True,
            ) as _mock_handlers,
            mock.patch(
                "scrappi.interface.Factory.all_api_list",
                ["handle1", "handle2"],
            ) as _mock_all_api_list,
        ):
            context = ScrappiContext()
            context["api"]["preferred_api"] = "api"
            query = {"collection": "LANDSAT_C2L1"}
            perform_query(query, context)
            m.assert_called_with(context=context)
            m().perform_query.assert_called_with({"collection": "LANDSAT_C2L1"})

    def test_perform_query_tries_next_api_when_a_candidate_raises(self):
        """A candidate whose perform_query *raises* (e.g. RadcalnetCallHandler
        raising for a site the online portal doesn't host) must not abort the
        fallback chain -- the next candidate (e.g. an offline archive handler for
        the same collection) still gets a turn. Without this, one candidate's
        error crashed the whole query instead of falling through."""
        failing = mock.MagicMock()
        failing.perform_query.side_effect = ValueError("site unknown")
        working = mock.MagicMock()
        working.perform_query.return_value = ["a product"]
        handler_classes = {
            "handle1": mock.MagicMock(return_value=failing),
            "handle2": mock.MagicMock(return_value=working),
        }
        for m in handler_classes.values():
            m().list_collections.return_value = ["LANDSAT_C2L1"]

        with (
            mock.patch.dict(
                "scrappi.interface.Factory.api_call_handlers",
                handler_classes,
                clear=True,
            ) as _mock_handlers,
            mock.patch(
                "scrappi.interface.Factory.all_api_list",
                ["handle1", "handle2"],
            ) as _mock_all_api_list,
        ):
            context = ScrappiContext()
            context["api"]["preferred_api"] = None
            with self.assertWarns(UserWarning):
                result = perform_query({"collection": "LANDSAT_C2L1"}, context)

        self.assertEqual(result, ["a product"])
        failing.perform_query.assert_called_once()
        working.perform_query.assert_called_once()

    def test_download_product(self):
        context = ScrappiContext()
        m = mock.MagicMock()
        m().list_collections.return_value = ["S3_EFR"]
        with (
            mock.patch.dict(
                "scrappi.interface.Factory.api_call_handlers",
                {"handle1": m, "handle2": m},
                clear=True,
            ) as _mock_handlers,
            mock.patch(
                "scrappi.interface.Factory.all_api_list",
                ["handle1", "handle2"],
            ) as _mock_all_api_list,
        ):
            download_product(self.p, context)
            m.assert_called_with(context=context)
            assert m().download_product.call_args[0][0] == self.p

    def test_download_product_skips_stac_registration_for_a_read_only_filesystem(self):
        """Regression test: an offline handler's product.filesystem is pinned inside
        its own archive (read-only). download_product used to call
        product.register_in_filesystem_catalog() on it regardless (the default,
        context['fs']['register_stac_items'] is True), writing a stac/ folder into
        the archive itself instead of a separate matchup catalogue."""
        context = ScrappiContext()
        self.p.filesystem = mock.Mock(read_only=True)
        self.p.filesystem.return_path.return_value = ("/some/path", False)
        m = mock.MagicMock()
        m().list_collections.return_value = ["S3_EFR"]
        m().download_product.return_value = "/some/path"
        with (
            mock.patch.dict(
                "scrappi.interface.Factory.api_call_handlers",
                {"handle1": m},
                clear=True,
            ),
            mock.patch("scrappi.interface.Factory.all_api_list", ["handle1"]),
            mock.patch.object(self.p, "register_in_filesystem_catalog") as mock_register,
        ):
            result = download_product(self.p, context)

        mock_register.assert_not_called()
        self.assertEqual(result, "/some/path")

    def test_candidate_failure_is_recoverable(self):
        from scrappi.interface import _candidate_failure_is_recoverable

        class _HTTPish(Exception):
            def __init__(self, code):
                self.response = mock.Mock(status_code=code)

        self.assertTrue(_candidate_failure_is_recoverable(ValueError("site unknown")))
        self.assertTrue(_candidate_failure_is_recoverable(KeyError("ERUS")))
        self.assertTrue(_candidate_failure_is_recoverable(NotImplementedError()))
        self.assertTrue(_candidate_failure_is_recoverable(_HTTPish(404)))
        self.assertTrue(_candidate_failure_is_recoverable(_HTTPish(503)))
        self.assertFalse(_candidate_failure_is_recoverable(_HTTPish(401)))
        self.assertFalse(_candidate_failure_is_recoverable(_HTTPish(403)))
        self.assertFalse(_candidate_failure_is_recoverable(TypeError("bug")))
        self.assertFalse(_candidate_failure_is_recoverable(ConnectionError()))

    def _fanout_handlers(self, first, second):
        """Two candidate APIs; `first`/`second` are the perform_query side effects."""
        h1, h2 = mock.MagicMock(), mock.MagicMock()
        h1.list_collections.return_value = h2.list_collections.return_value = ["LANDSAT_C2L1"]
        h1.perform_query.side_effect = first
        h2.perform_query.side_effect = second
        factory = {"h1": mock.MagicMock(return_value=h1), "h2": mock.MagicMock(return_value=h2)}
        return factory

    def test_perform_query_recoverable_failure_falls_through_to_next_candidate(self):
        from scrappi.product import ProductItemSet

        wanted = ProductItemSet([mock.Mock()])
        factory = self._fanout_handlers(ValueError("site not in this registry"), lambda q: wanted)
        with (
            mock.patch.dict("scrappi.interface.Factory.api_call_handlers", factory, clear=True),
            mock.patch("scrappi.interface.Factory.all_api_list", ["h1", "h2"]),
        ):
            with self.assertWarns(UserWarning):
                out = perform_query({"collection": "LANDSAT_C2L1"}, ScrappiContext())
            self.assertIs(out, wanted)

    def test_perform_query_reraises_a_non_recoverable_failure(self):
        factory = self._fanout_handlers(TypeError("a real bug"), lambda q: None)
        with (
            mock.patch.dict("scrappi.interface.Factory.api_call_handlers", factory, clear=True),
            mock.patch("scrappi.interface.Factory.all_api_list", ["h1", "h2"]),
        ):
            with self.assertRaises(TypeError):
                perform_query({"collection": "LANDSAT_C2L1"}, ScrappiContext())

    def test_perform_query_reraises_last_error_when_every_candidate_fails_recoverably(self):
        factory = self._fanout_handlers(ValueError("nope 1"), ValueError("nope 2"))
        with (
            mock.patch.dict("scrappi.interface.Factory.api_call_handlers", factory, clear=True),
            mock.patch("scrappi.interface.Factory.all_api_list", ["h1", "h2"]),
        ):
            with self.assertRaises(ValueError):
                perform_query({"collection": "LANDSAT_C2L1"}, ScrappiContext())

    def test_download_product_filename(self):
        context = ScrappiContext()
        context["api"]["preferred_api"] = "api"
        m = mock.MagicMock()
        with mock.patch.dict("scrappi.interface.Factory.api_call_handlers", {"api": m}, clear=True) as _mock_handlers:
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
            except Exception:
                print("product not unsupported or non existing")

    def test_download_product_scene(self):
        context = ScrappiContext()
        context["api"]["preferred_api"] = "api"
        m = mock.MagicMock()
        with mock.patch.dict("scrappi.interface.Factory.api_call_handlers", {"api": m}, clear=True) as _mock_handlers:
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
            "scrappi.utils.utils.Transformer.from_crs",
            side_effect=[mock_transformer, mock_reverse_transformer],
        ) as _mock_from_crs:
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
            "scrappi.utils.utils.Transformer.from_crs",
            side_effect=[mock_transformer, mock_reverse_transformer],
        ) as _mock_from_crs:
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
