"""scrappi.api.tests.test_factory - tests for scrappi.api.factory"""

import unittest
from unittest import mock

from scrappi import ScrappiContext
from scrappi.api.factory import APICallHandlerFactory
from scrappi.api.eodag import EODAGCallHandler
from scrappi.api.flex_stac_api import FLEXSTACAPICallHandler
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
        radcalnet_api = self.api_call_handler_factory.get_api_call_handler("radcalnet")
        assert isinstance(radcalnet_api, RadcalnetCallHandler)
        flex_api = self.api_call_handler_factory.get_api_call_handler("flex_stac")
        assert isinstance(flex_api, FLEXSTACAPICallHandler)
        self.assertRaises(IOError, self.api_call_handler_factory.get_api_call_handler, "bad_path")

    def test_get_api_call_handler_eodag_with_provider(self):
        context = ScrappiContext()
        with mock.patch("scrappi.api.factory.EODAGCallHandler") as mock_eodag_handler:
            mock_eodag_handler.return_value = mock.Mock()
            handler = self.api_call_handler_factory.get_api_call_handler("eodag:cop_dataspace", context=context)
            self.assertIsNotNone(handler)
            self.assertEqual(context["api"]["preferred_provider"], "cop_dataspace")

    def test_get_api_call_handler_invalid_eodag_provider_format(self):
        with self.assertRaises(IOError):
            self.api_call_handler_factory.get_api_call_handler("aws:provider_a")


if __name__ == "__main__":
    unittest.main()
