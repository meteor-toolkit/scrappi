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


if __name__ == "__main__":
    unittest.main()
