"""scrappi.api.tests.test_factory - tests for scrappi.api.factory"""

import unittest
import unittest.mock as mock

from scrappi.api.factory import APICallHandlerFactory
from scrappi.api.eodag import EODAGCallHandler
from scrappi.api.hypernets import HYPERNETSOfflineCallHandler
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


if __name__ == "__main__":
    unittest.main()
