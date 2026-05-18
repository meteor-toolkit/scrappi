"""scrappi.fs.tests.test_factory - tests for scrappi.fs.factory"""

import unittest
from scrappi.fs.factory import FSCallHandlerFactory
from scrappi.fs.localfilesystem import LocalFileSystem
from scrappi.fs.tdrive import TdriveFileSystem
import os.path
from scrappi import ScrappiContext

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


if __name__ == "__main__":
    unittest.main()
