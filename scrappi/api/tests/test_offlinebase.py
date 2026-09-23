import os
import unittest
import unittest.mock
from datetime import datetime
from tempfile import TemporaryDirectory

from shapely.geometry import Point

from scrappi import ScrappiContext
from scrappi.api.offlinebase import OfflineArchiveHandler
from scrappi.product import ProductItem, ProductItemSet


class _Handler(OfflineArchiveHandler):
    """Minimal concrete OfflineArchiveHandler for exercising the base mechanics."""

    name = "test_offline"
    ARCHIVE_PATH_CONTEXT_KEYS = ("Test", "archive_path")

    def _default_archive_path(self) -> str:
        return "/the/hardcoded/default"

    def list_collections(self, fetch_update=False):
        return ["TEST_COL"]

    def perform_query(self, query):
        return ProductItemSet()


def _product(pid: str) -> ProductItem:
    return ProductItem(
        constellation="Test",
        platform="X",
        collection="TEST_COL",
        id=pid,
        geometry=Point(0, 0),
        start_time=datetime(2024, 1, 1),
        stop_time=datetime(2024, 1, 1),
        url="",
    )


class TestArchivePathResolution(unittest.TestCase):
    def test_explicit_arg_wins(self):
        self.assertEqual(_Handler(ScrappiContext(), archive_path="/given").archive_path, "/given")

    def test_falls_back_to_context_keys(self):
        ctx = ScrappiContext()
        ctx["Test"] = {"archive_path": "/from/context"}
        self.assertEqual(_Handler(ctx).archive_path, "/from/context")

    def test_falls_back_to_default_when_context_unset(self):
        self.assertEqual(_Handler(ScrappiContext()).archive_path, "/the/hardcoded/default")

    def test_missing_default_raises_a_clear_error(self):
        class _NoDefault(_Handler):
            ARCHIVE_PATH_CONTEXT_KEYS = ()

            def _default_archive_path(self):
                return OfflineArchiveHandler._default_archive_path(self)

        with self.assertRaises(NotImplementedError):
            _NoDefault(ScrappiContext())


class TestDownloadProduct(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.handler = _Handler(ScrappiContext(), archive_path=self.tmp.name)

    def _write(self, *parts):
        path = os.path.join(self.tmp.name, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()
        return path

    def test_locates_a_file_anywhere_in_the_tree_and_repins_the_filesystem(self):
        real = self._write("2024", "03", "some_product")
        product = _product("some_product")
        product.filesystem = None  # as if rebuilt from a STAC catalogue

        path = self.handler.download_product(product)

        self.assertEqual(os.path.normpath(path), os.path.normpath(real))
        self.assertEqual(os.path.normpath(product.get_path()), os.path.normpath(real))
        self.assertFalse(product.filesystem.organise_data)

    def test_raises_file_not_found_when_absent(self):
        with self.assertRaises(FileNotFoundError):
            self.handler.download_product(_product("not_here"))

    def test_recurses_over_a_product_item_set(self):
        self._write("a")
        self._write("b")
        paths = self.handler.download_product(ProductItemSet([_product("a"), _product("b")]))
        self.assertEqual({os.path.basename(p) for p in paths}, {"a", "b"})

    def test_non_product_input_warns_and_returns_none(self):
        with self.assertWarns(UserWarning):
            self.assertIsNone(self.handler.download_product("just a string"))

    def test_archive_is_walked_once_and_cached(self):
        self._write("x", "a")
        self._write("y", "b")
        with unittest.mock.patch("scrappi.api.offlinebase.os.walk", wraps=os.walk) as walk:
            self.handler.download_product(ProductItemSet([_product("a"), _product("b")]))
            self.handler._archive_index  # a third touch
        walk.assert_called_once()

    def test_clear_cache_forces_a_re_walk(self):
        self._write("a")
        self.handler.download_product(_product("a"))  # populates the cache
        with unittest.mock.patch("scrappi.api.offlinebase.os.walk", wraps=os.walk) as walk:
            self.handler._archive_index
            walk.assert_not_called()
            self.handler.clear_cache()
            self.handler._archive_index
            walk.assert_called_once()

    def test_default_matching_is_exact_only(self):
        """The base sets no PRODUCT_NAME_SUFFIXES: in-situ ids are the filenames,
        so an id of ``foo`` does NOT resolve to an on-disk ``foo.zip``."""
        self._write("2024", "foo.zip")
        with self.assertRaises(FileNotFoundError):
            self.handler.download_product(_product("foo"))

    def test_repinned_filesystem_is_read_only(self):
        """download_product's re-pinned filesystem carries ARCHIVE_READ_ONLY, so
        the archive-write protection a query set survives a catalogue-rebuilt
        product being resolved."""
        self._write("a")
        product = _product("a")
        product.filesystem = None
        self.handler.download_product(product)
        self.assertTrue(product.filesystem.read_only)


class _SuffixHandler(_Handler):
    INDEX_DIRECTORY_SUFFIXES = (".SAFE",)
    PRODUCT_NAME_SUFFIXES = (".SAFE", ".zip", ".nc")


class TestSuffixAndDirectoryMatching(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.handler = _SuffixHandler(ScrappiContext(), archive_path=self.tmp.name)

    def _write(self, *parts):
        path = os.path.join(self.tmp.name, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()
        return path

    def _mkproduct_dir(self, *parts):
        d = os.path.join(self.tmp.name, *parts)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "MTD_MSIL1C.xml"), "w").close()
        return d

    def test_id_resolves_to_an_on_disk_name_with_a_suffix(self):
        real = self._write("2024", "foo.zip")
        self.assertEqual(
            os.path.normpath(self.handler.download_product(_product("foo"))),
            os.path.normpath(real),
        )

    def test_a_dot_safe_directory_is_one_index_entry_not_its_contents(self):
        safe = self._mkproduct_dir("2023", "S2A_MSIL1C_20230607T104621.SAFE")
        index = self.handler._archive_index
        self.assertEqual(os.path.normpath(index["S2A_MSIL1C_20230607T104621.SAFE"]), os.path.normpath(safe))
        self.assertNotIn("MTD_MSIL1C.xml", index)

    def test_download_resolves_a_dot_safe_from_the_bare_id(self):
        safe = self._mkproduct_dir("2023", "S2A_MSIL1C_20230607T104621.SAFE")
        path = self.handler.download_product(_product("S2A_MSIL1C_20230607T104621"))
        self.assertEqual(os.path.normpath(path), os.path.normpath(safe))

    def test_a_json_sidecar_is_never_matched_as_the_data_file(self):
        """`.json` must not be in PRODUCT_NAME_SUFFIXES: a STAC item sidecar with
        no data file present must resolve to nothing, not to the sidecar."""
        self._write("2024", "baz.json")
        with self.assertRaises(FileNotFoundError):
            self.handler.download_product(_product("baz"))


if __name__ == "__main__":
    unittest.main()
