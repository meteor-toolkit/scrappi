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

    def test_id_matches_an_on_disk_name_with_a_product_suffix(self):
        """A product id of ``foo`` resolves to ``foo.zip`` / ``foo.nc`` on disk."""
        real = self._write("2024", "foo.zip")
        self.assertEqual(
            os.path.normpath(self.handler.download_product(_product("foo"))),
            os.path.normpath(real),
        )

    def test_id_matches_via_stem_when_the_id_carries_the_suffix(self):
        """A product id of ``foo.nc`` resolves to a file literally named ``foo.nc``
        *and* the base's suffix-strip fallback still finds ``foo`` if that's the
        on-disk name."""
        real = self._write("bar")
        self.assertEqual(
            os.path.normpath(self.handler.download_product(_product("bar.nc"))),
            os.path.normpath(real),
        )


class _DirHandler(_Handler):
    INDEX_DIRECTORY_SUFFIXES = (".SAFE",)


class TestDirectoryProducts(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.handler = _DirHandler(ScrappiContext(), archive_path=self.tmp.name)

    def _mkproduct_dir(self, *parts):
        d = os.path.join(self.tmp.name, *parts)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "MTD_MSIL1C.xml"), "w").close()
        open(os.path.join(d, "manifest.safe"), "w").close()
        return d

    def test_a_dot_safe_directory_is_one_index_entry_not_its_contents(self):
        safe = self._mkproduct_dir("2023", "S2A_MSIL1C_20230607T104621.SAFE")
        index = self.handler._archive_index
        self.assertIn("S2A_MSIL1C_20230607T104621.SAFE", index)
        self.assertEqual(os.path.normpath(index["S2A_MSIL1C_20230607T104621.SAFE"]), os.path.normpath(safe))
        # the granule files inside are NOT indexed
        self.assertNotIn("MTD_MSIL1C.xml", index)
        self.assertNotIn("manifest.safe", index)

    def test_download_resolves_a_dot_safe_from_the_bare_id(self):
        safe = self._mkproduct_dir("2023", "S2A_MSIL1C_20230607T104621.SAFE")
        path = self.handler.download_product(_product("S2A_MSIL1C_20230607T104621"))
        self.assertEqual(os.path.normpath(path), os.path.normpath(safe))


if __name__ == "__main__":
    unittest.main()
