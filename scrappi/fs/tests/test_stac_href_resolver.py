import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scrappi.fs.stac_href_resolver import StacHrefResolver
import os


class TestStacHrefResolver(unittest.TestCase):

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)

        self.stac_root = self.root / "stac"
        self.data_root = self.root / "data"

        self.stac_root.mkdir()
        self.data_root.mkdir()

        # create dummy files
        (self.stac_root / "items/2025/11/01").mkdir(parents=True)
        (self.data_root / "data/A/B").mkdir(parents=True)

        (self.stac_root / "items/2025/11/01/item.json").write_text("{}")
        (self.data_root / "data/A/B/file.nc").write_text("dummy")

        self.resolver = StacHrefResolver(
            stac_root=self.stac_root,
            data_root=self.data_root,
        )

    def tearDown(self):
        self.tmp.cleanup()

    # -------------------------------------------------------------

    def test_stac_uri_netloc_and_path_resolved_correctly(self):
        href = "stac://items/2025/11/01/item.json"
        resolved = self.resolver.resolve(href)

        expected = self.stac_root / "items/2025/11/01/item.json"
        self.assertEqual(Path(resolved), expected)

    def test_asset_uri_netloc_and_path_resolved_correctly(self):
        href = "asset://data/A/B/file.nc"
        resolved = self.resolver.resolve(href)

        expected = self.data_root / "data/A/B/file.nc"
        self.assertEqual(Path(resolved), expected)

    def test_invalid_scheme_raises(self):
        with self.assertRaises(ValueError):
            self.resolver.resolve("http://example.com/file")

    def test_missing_target_raises_or_returns_path(self):
        href = "stac://items/missing.json"
        resolved = self.resolver.resolve(href)

        self.assertTrue(str(resolved).endswith(os.path.join("items", "missing.json")))
