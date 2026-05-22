"""scrappi.fs.tests.test_base - tests for scrappi.fs.base"""

import unittest
from scrappi.fs.base import BaseFileSystem
import os

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]


class TestBaseFileSystem(unittest.TestCase):
    def setUp(self) -> None:
        # dummy helper class to test BaseFSCallHandler class
        class DummyFSCallHandler(BaseFileSystem):
            def __init__(self, directory):
                super().__init__(directory=directory)

            def return_path(self, product_info: dict, check_exists: bool = False):
                pass

            def return_path_platform_collection_year_month_day(self, collection: str, year: str, month: str, day: str):
                pass

        self.DummyFSCallHandler = DummyFSCallHandler

    def test_subclass_builds(self) -> None:
        dummy_fs_call_handler = self.DummyFSCallHandler(directory="test")
        assert dummy_fs_call_handler.directory == "test"


if __name__ == "__main__":
    unittest.main()
