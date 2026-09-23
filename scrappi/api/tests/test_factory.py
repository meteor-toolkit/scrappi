"""scrappi.api.tests.test_factory - tests for scrappi.api.factory"""

import unittest
from unittest import mock

from scrappi.api.factory import API_CALL_HANDLERS, APICallHandlerFactory
from scrappi.api.eodag import EODAGCallHandler
from scrappi.api.radcalnet_api_client import RadcalnetCallHandler

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]


class TestAPICallHandlerFactory(unittest.TestCase):
    def setUp(self) -> None:
        self.api_call_handler_factory = APICallHandlerFactory()

    def test_get_api_call_handler(self):
        eodag_api = self.api_call_handler_factory.get_api_call_handler("eodag")
        assert isinstance(eodag_api, EODAGCallHandler)
        # hypernets_api = self.api_call_handler_factory.get_api_call_handler(
        #     "hypernets_offline"
        # )
        # assert isinstance(hypernets_api, HYPERNETSOfflineCallHandler)
        radcalnet_api = self.api_call_handler_factory.get_api_call_handler("radcalnet")
        assert isinstance(radcalnet_api, RadcalnetCallHandler)
        self.assertRaises(IOError, self.api_call_handler_factory.get_api_call_handler, "bad_path")

    def test_eumdac_not_in_static_handler_dict(self):
        """eumdac must stay out of the static, eagerly-imported API_CALL_HANDLERS
        dict -- like earthaccess/hypernets, it's meant to be resolved lazily inside
        get_api_call_handler so importing scrappi.api.factory doesn't pull in
        eumdac's module (and its shapely/requests imports) unless actually used."""
        self.assertNotIn("eumdac", API_CALL_HANDLERS)

    def test_get_api_call_handler_eumdac(self):
        from scrappi import ScrappiContext
        from scrappi.api.eumdac import EUMDACCallHandler

        context = ScrappiContext()
        context["eumdac"] = {"credentials": {"key": "key", "secret": "secret"}}

        with (
            mock.patch("scrappi.api.eumdac.eumdac.AccessToken", return_value=mock.Mock()),
            mock.patch("scrappi.api.eumdac.eumdac.DataStore", return_value=mock.Mock()),
        ):
            eumdac_api = self.api_call_handler_factory.get_api_call_handler("eumdac", context=context)

        self.assertIsInstance(eumdac_api, EUMDACCallHandler)

    def test_get_api_call_handler_caches_by_default(self):
        """Repeated calls for the same name return the *same* instance -- this is
        what avoids rebuilding e.g. eodag's EODataAccessGateway (a few hundred ms)
        on every call."""
        first = self.api_call_handler_factory.get_api_call_handler("radcalnet")
        second = self.api_call_handler_factory.get_api_call_handler("radcalnet")
        self.assertIs(first, second)

    def test_get_api_call_handler_use_cache_false_builds_fresh(self):
        first = self.api_call_handler_factory.get_api_call_handler("radcalnet")
        second = self.api_call_handler_factory.get_api_call_handler("radcalnet", use_cache=False)
        self.assertIsNot(first, second)

    def test_get_api_call_handler_use_cache_false_does_not_disturb_cache(self):
        """A use_cache=False call builds a throwaway handler without touching
        (overwriting or populating) the cache for subsequent use_cache=True calls."""
        first = self.api_call_handler_factory.get_api_call_handler("radcalnet")
        self.api_call_handler_factory.get_api_call_handler("radcalnet", use_cache=False)
        third = self.api_call_handler_factory.get_api_call_handler("radcalnet")
        self.assertIs(first, third)

    def test_clear_cache_forces_rebuild(self):
        first = self.api_call_handler_factory.get_api_call_handler("radcalnet")
        self.api_call_handler_factory.clear_cache()
        second = self.api_call_handler_factory.get_api_call_handler("radcalnet")
        self.assertIsNot(first, second)

    def test_different_names_cached_independently(self):
        radcalnet_api = self.api_call_handler_factory.get_api_call_handler("radcalnet")
        eodag_api = self.api_call_handler_factory.get_api_call_handler("eodag")
        self.assertIsInstance(radcalnet_api, RadcalnetCallHandler)
        self.assertIsInstance(eodag_api, EODAGCallHandler)
        self.assertIsNot(radcalnet_api, eodag_api)

    def test_context_aware_call_rebuilds_a_handler_cached_without_context(self):
        """Regression test: a no-context call (e.g. is_insitu_collection, which only
        needs a handler to type-check list_collections()) primes the cache with a
        handler built from scrappi defaults only. A later call that *does* pass a
        context must not get that context-free handler back on a cache hit -- it must
        be rebuilt from the given context, so per-run config (credentials, RadCalNet
        site_definitions, an offline archive path, ...) actually reaches it."""
        from scrappi import ScrappiContext

        context_free = self.api_call_handler_factory.get_api_call_handler("radcalnet")
        ctx = ScrappiContext(
            {"RadCalNet": {"site_definitions": {"ZZZZ": {"latitude": 1.0, "longitude": 2.0, "default_roi": 30}}}}
        )
        with_context = self.api_call_handler_factory.get_api_call_handler("radcalnet", context=ctx)

        self.assertIsNot(context_free, with_context)
        self.assertIn("ZZZZ", with_context.sites)
        self.assertNotIn("ZZZZ", context_free.sites)

    def test_same_context_object_reuses_the_cached_handler(self):
        """Regression test: repeated calls that reuse the *same* context object (the
        common case within one run -- one context built once, passed to every query)
        must reuse one handler and its live session, not rebuild from scratch every
        call. Without this, a batch run issuing many context-aware queries (e.g.
        Sat2InSituMUFinder's per-event RadCalNet queries) piles up one open session
        per query -- each pinned alive by every ProductItem it returned via
        ProductItem.api -- and can exhaust the process's open-file limit."""
        from scrappi import ScrappiContext

        ctx = ScrappiContext()
        first = self.api_call_handler_factory.get_api_call_handler("radcalnet", context=ctx)
        second = self.api_call_handler_factory.get_api_call_handler("radcalnet", context=ctx)
        self.assertIs(first, second)

    def test_different_context_objects_get_independent_handlers(self):
        """Two distinct context objects -- even with identical content -- must not
        share a cached handler: the whole point of keying by context identity (not
        just name) is that a genuinely different context always gets its own handler."""
        from scrappi import ScrappiContext

        ctx_a = ScrappiContext()
        ctx_b = ScrappiContext()
        first = self.api_call_handler_factory.get_api_call_handler("radcalnet", context=ctx_a)
        second = self.api_call_handler_factory.get_api_call_handler("radcalnet", context=ctx_b)
        self.assertIsNot(first, second)

    def test_eodag_handler_is_served_from_cache_regardless_of_context(self):
        """eodag construction is expensive and its per-run context differences (the
        preferred provider) are applied at query time, so it stays cached by name even
        when a context is passed."""
        from scrappi import ScrappiContext

        first = self.api_call_handler_factory.get_api_call_handler("eodag")
        second = self.api_call_handler_factory.get_api_call_handler("eodag", context=ScrappiContext())
        self.assertIs(first, second)

if __name__ == "__main__":
    unittest.main()
