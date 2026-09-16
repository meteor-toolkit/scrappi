"""scrappi.fs.tests.test_factory - tests for scrappi.fs.factory"""

import os.path
import tempfile
import unittest

from scrappi import ScrappiContext
from scrappi.fs.base import BaseFileSystem
from scrappi.fs.factory import FSCallHandlerFactory
from scrappi.fs.localfilesystem import LocalFileSystem
from scrappi.fs.stacfilesystem import STACFileSystem
from scrappi.fs.tdrive import TdriveFileSystem

__author__ = "Sam Hunt <sam.hunt@npl.co.uk>"

example_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "examples",
)


class TestFSCallHandlerFactory(unittest.TestCase):
    def test_get_fs_call_handler(self):
        factory = FSCallHandlerFactory()
        tdrivearchivehandler = factory.get_fs_call_handler("tdrive")
        assert isinstance(tdrivearchivehandler, TdriveFileSystem)
        localarchivehandler = factory.get_fs_call_handler(example_path)
        assert isinstance(localarchivehandler, LocalFileSystem)
        context = ScrappiContext()
        context["fs"]["organise_data"] = False
        localarchivehandler = factory.get_fs_call_handler(example_path, context)
        assert isinstance(localarchivehandler, LocalFileSystem)
        self.assertRaises(ValueError, factory.get_fs_call_handler, "bad_path")

    def test_get_fs_call_handler_with_none_or_existing_instance(self):
        factory = FSCallHandlerFactory()

        with self.assertRaises(ValueError):
            factory.get_fs_call_handler(None)

        class DummyFileSystem(BaseFileSystem):
            def return_path(self, product_item, check_exists: bool = False):
                return "dummy"

        dummy = DummyFileSystem(directory="dummy")
        self.assertIs(factory.get_fs_call_handler(dummy), dummy)

    def test_get_fs_call_handler_stac_context(self):
        factory = FSCallHandlerFactory()
        context = ScrappiContext()
        context["fs"]["stac"] = True

        with tempfile.TemporaryDirectory() as tmpdir:
            handler = factory.get_fs_call_handler(tmpdir, context=context)
            self.assertIsInstance(handler, STACFileSystem)


if __name__ == "__main__":
    unittest.main()
