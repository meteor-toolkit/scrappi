"""Tests for scrappi.api.satellite_offline.SatelliteOfflineCallHandler (skeleton).

Each test builds a minimal version of the archive layout the handler expects --
scrappi's ``stac/`` tree plus the data product -- and checks the
query / download / to_stac_item flow.
"""

import json
import math
import os
import sys
import types
import unittest
import unittest.mock
from datetime import datetime
from tempfile import TemporaryDirectory

from shapely.geometry import Polygon

from scrappi import ScrappiContext
from scrappi.api.satellite_offline import SatelliteOfflineCallHandler
from scrappi.fs.stacfilesystem import STACFileSystem


def _fake_eoio_modules(metadata_by_filename: dict) -> dict:
    """sys.modules entries faking eoio.readers.factory.ReaderFactory, so
    _metadata_via_eoio can be exercised without the real (optional, lazily
    imported) eoio package installed. get_reader(path) returns a reader class
    whose instance exposes .mtd.basic_metadata / .mtd.product_metadata from
    metadata_by_filename[os.path.basename(path)] = (basic, product); a path with
    no entry makes get_reader raise, like eoio does for an unrecognised product."""

    class _FakeMtd:
        def __init__(self, basic, product):
            self.basic_metadata = basic
            self.product_metadata = product

    class _FakeReader:
        def __init__(self, path):
            basic, product = metadata_by_filename[os.path.basename(path)]
            self.mtd = _FakeMtd(basic, product)

    class _FakeReaderFactory:
        @staticmethod
        def get_reader(path):
            if os.path.basename(path) not in metadata_by_filename:
                raise ValueError(f"no fake eoio reader registered for {path!r}")
            return _FakeReader

    eoio_pkg = types.ModuleType("eoio")
    readers_pkg = types.ModuleType("eoio.readers")
    factory_mod = types.ModuleType("eoio.readers.factory")
    factory_mod.ReaderFactory = _FakeReaderFactory
    readers_pkg.factory = factory_mod
    eoio_pkg.readers = readers_pkg
    return {"eoio": eoio_pkg, "eoio.readers": readers_pkg, "eoio.readers.factory": factory_mod}


def _stac_item(item_id: str, collection: str, *, platform="S2A", cloud=12.0) -> dict:
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": item_id,
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]},
        "bbox": [0, 0, 2, 2],
        "properties": {
            "datetime": "2023-06-07T10:46:21Z",
            "start_datetime": "2023-06-07T10:46:21Z",
            "end_datetime": "2023-06-07T10:46:21Z",
            "platform": platform,
            "constellation": "Sentinel-2",
            "eo:cloud_cover": cloud,
        },
        "links": [],
        "assets": {"data": {"href": f"./{item_id}.SAFE"}},
        "collection": collection,
    }


def _collection_json(collection: str) -> dict:
    return {
        "type": "Collection",
        "id": collection,
        "stac_version": "1.0.0",
        "description": "",
        "license": "other",
        "extent": {
            "spatial": {"bbox": [[0, 0, 2, 2]]},
            "temporal": {"interval": [["2023-06-07T00:00:00Z", None]]},
        },
        "links": [],
    }


def _write_json(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f)


def _populate(base: str, collection: str, item_id: str, **item_kw) -> str:
    """Write <base>/{data,stac}/... for one product. Returns the .SAFE dir path."""
    safe = os.path.join(base, "data", f"{item_id}.SAFE")
    os.makedirs(safe, exist_ok=True)
    open(os.path.join(safe, "MTD_MSIL1C.xml"), "w").close()
    _write_json(
        os.path.join(base, "stac", collection, "items", "2023", "06", "07", f"{item_id}.json"),
        _stac_item(item_id, collection, **item_kw),
    )
    _write_json(os.path.join(base, "stac", collection, "collection.json"), _collection_json(collection))
    return safe


_S2_ID = "S2A_MSIL1C_20230607T104621_N0509_R051_T31UDQ_20230607T142522"
_LS_ID = "LC09_L1TP_203023_20230607_20230607_02_T1"


class TestPerCollectionLayout(unittest.TestCase):
    """<root>/<collection>/{data,stac}/..."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.s2_dir = os.path.join(self.root, "S2_MSI_L1C")
        self.safe = _populate(self.s2_dir, "S2_MSI_L1C", _S2_ID)
        _populate(os.path.join(self.root, "LANDSAT_C2L1"), "LANDSAT_C2L1", _LS_ID, platform="LC09")
        self.handler = SatelliteOfflineCallHandler(ScrappiContext(), archive_path=self.root)

    def _query(self, **over):
        q = {
            "collection": "S2_MSI_L1C",
            "start_time": datetime(2023, 6, 1),
            "stop_time": datetime(2023, 6, 30),
            "geom": {"latitude_minimum": 0, "longitude_minimum": 0, "latitude_maximum": 3, "longitude_maximum": 3},
        }
        q.update(over)
        return q

    # ---- discovery ----
    def test_list_collections_finds_every_collection(self):
        self.assertEqual(self.handler.list_collections(), ["LANDSAT_C2L1", "S2_MSI_L1C"])

    def test_list_collections_does_not_recursively_walk_the_archive(self):
        with unittest.mock.patch("scrappi.api.satellite_offline.os.walk") as walk:
            self.handler.clear_cache()
            self.handler.list_collections()
        walk.assert_not_called()

    def test_list_collections_is_cached(self):
        self.handler.list_collections()
        with unittest.mock.patch("scrappi.api.satellite_offline.glob.glob") as g:
            self.handler.list_collections()
        g.assert_not_called()

    def test_collection_root_prefers_the_named_subdirectory(self):
        self.assertEqual(
            os.path.normpath(self.handler._collection_root("S2_MSI_L1C")),
            os.path.normpath(self.s2_dir),
        )

    def test_collection_root_context_override_wins(self):
        ctx = ScrappiContext()
        ctx["api"]["offline_archive_paths"] = {"S2_MSI_L1C": "/explicit/path"}
        h = SatelliteOfflineCallHandler(ctx, archive_path=self.root)
        self.assertEqual(h._collection_root("S2_MSI_L1C"), "/explicit/path")

    # ---- query ----
    def test_perform_query_returns_only_the_requested_collection(self):
        products = self.handler.perform_query(self._query())
        self.assertEqual([p.id for p in products], [_S2_ID])

    def test_perform_query_all_collections_when_none_given(self):
        q = self._query()
        q.pop("collection")
        ids = sorted(p.id for p in self.handler.perform_query(q))
        self.assertEqual(ids, sorted([_S2_ID, _LS_ID]))

    def test_geometry_filter(self):
        self.assertEqual(
            len(
                self.handler.perform_query(
                    self._query(
                        geom={
                            "latitude_minimum": 40,
                            "longitude_minimum": 40,
                            "latitude_maximum": 41,
                            "longitude_maximum": 41,
                        }
                    )
                )
            ),
            0,
        )

    def test_time_filter(self):
        self.assertEqual(
            len(
                self.handler.perform_query(self._query(start_time=datetime(2024, 1, 1), stop_time=datetime(2024, 2, 1)))
            ),
            0,
        )

    def test_platform_filter(self):
        self.assertEqual(len(self.handler.perform_query(self._query(platform="S2B"))), 0)
        self.assertEqual(len(self.handler.perform_query(self._query(platform="S2A"))), 1)

    def test_product_filesystem_is_read_only_and_pinned_to_the_data_dir(self):
        p = self.handler.perform_query(self._query())[0]
        self.assertIsInstance(p.filesystem, STACFileSystem)
        self.assertTrue(p.filesystem.read_only)
        self.assertEqual(
            os.path.normpath(p.filesystem.directory),
            os.path.normpath(os.path.join(self.s2_dir, "data")),
        )

    def test_product_can_be_converted_to_a_stac_item(self):
        p = self.handler.perform_query(self._query())[0]
        self.assertEqual(p.to_stac_item().id, _S2_ID)

    def test_filesystem_is_only_built_for_matches(self):
        """The geom/time/platform filter runs before _pin_filesystem, so a
        no-match query builds no STACFileSystem objects."""
        with unittest.mock.patch.object(self.handler, "_flat_filesystem") as fs:
            self.handler.perform_query(self._query(platform="NOPE"))
        fs.assert_not_called()

    # ---- download ----
    def test_download_resolves_the_safe_directory_and_stays_read_only(self):
        p = self.handler.perform_query(self._query())[0]
        path = self.handler.download_product(p)
        self.assertEqual(os.path.normpath(path), os.path.normpath(self.safe))
        self.assertTrue(p.filesystem.read_only)


class TestSharedLayout(unittest.TestCase):
    """<root>/{data,stac}/... shared across collections (no per-collection subdir)."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        _populate(self.root, "S2_MSI_L1C", _S2_ID)
        _populate(self.root, "LANDSAT_C2L1", _LS_ID, platform="LC09")
        self.handler = SatelliteOfflineCallHandler(ScrappiContext(), archive_path=self.root)

    def test_list_collections_returns_ids_not_data_and_stac_dirnames(self):
        self.assertEqual(self.handler.list_collections(), ["LANDSAT_C2L1", "S2_MSI_L1C"])

    def test_shared_root_is_walked_once_for_multiple_collections(self):
        q = {
            "collections": ["S2_MSI_L1C", "LANDSAT_C2L1"],
            "start_time": datetime(2023, 6, 1),
            "stop_time": datetime(2023, 6, 30),
        }
        real = SatelliteOfflineCallHandler._stac_item_paths
        calls = []
        with unittest.mock.patch.object(
            SatelliteOfflineCallHandler,
            "_stac_item_paths",
            autospec=True,
            side_effect=lambda self, r: calls.append(r) or real(self, r),
        ):
            products = self.handler.perform_query(q)
        self.assertEqual(len(calls), 1)  # one shared <root>/stac walk, not one per collection
        self.assertEqual(sorted(p.id for p in products), sorted([_S2_ID, _LS_ID]))


class TestDirectoryNameDoesNotMatchCollectionId(unittest.TestCase):
    """<root>/<some_other_name>/{data,stac/<real_collection_id>}/...

    Regression tests: list_collections() discovers a collection by the "id" field
    inside its collection.json, regardless of the containing directory's name.
    _collection_root() used to separately assume that directory was named after
    the collection id (the "<archive_path>/<collection>/" convention) -- so a
    collection list_collections() found correctly could still be unresolvable by
    perform_query.
    """

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.mission_dir = os.path.join(self.root, "sentinel2")
        self.safe = _populate(self.mission_dir, "S2_MSI_L1C", _S2_ID)
        self.handler = SatelliteOfflineCallHandler(ScrappiContext(), archive_path=self.root)

    def test_list_collections_finds_it(self):
        self.assertEqual(self.handler.list_collections(), ["S2_MSI_L1C"])

    def test_collection_root_resolves_to_the_actual_directory(self):
        self.assertEqual(
            os.path.normpath(self.handler._collection_root("S2_MSI_L1C")),
            os.path.normpath(self.mission_dir),
        )

    def test_perform_query_finds_the_product(self):
        products = self.handler.perform_query(
            {
                "collection": "S2_MSI_L1C",
                "start_time": datetime(2023, 6, 1),
                "stop_time": datetime(2023, 6, 30),
            }
        )
        self.assertEqual([p.id for p in products], [_S2_ID])

    def test_download_resolves_the_safe_directory(self):
        products = self.handler.perform_query(
            {
                "collection": "S2_MSI_L1C",
                "start_time": datetime(2023, 6, 1),
                "stop_time": datetime(2023, 6, 30),
            }
        )
        path = self.handler.download_product(products[0])
        self.assertEqual(os.path.normpath(path), os.path.normpath(self.safe))


class TestArchiveRootNamedStac(unittest.TestCase):
    """archive_path itself sits under a directory literally named "stac" -- e.g.
    "/data/stac_archives/sentinel2" -- before scrappi's own stac/ tree. Regression
    test for _collection_of() taking the *first* "stac" path segment instead of
    the last."""

    def test_collection_recovered_when_item_collection_field_is_absent(self):
        with TemporaryDirectory() as outer:
            root = os.path.join(outer, "stac", "sentinel2")  # "stac" appears in the path
            os.makedirs(root)
            item = _stac_item(_S2_ID, "S2_MSI_L1C")
            del item["collection"]  # force the path-derived fallback in _load_item
            _write_json(os.path.join(root, "stac", "S2_MSI_L1C", "items", "2023", "06", "07", f"{_S2_ID}.json"), item)
            _write_json(os.path.join(root, "stac", "S2_MSI_L1C", "collection.json"), _collection_json("S2_MSI_L1C"))
            safe = os.path.join(root, "data", f"{_S2_ID}.SAFE")
            os.makedirs(safe)

            handler = SatelliteOfflineCallHandler(ScrappiContext(), archive_path=root)
            products = handler.perform_query(
                {
                    "collection": "S2_MSI_L1C",
                    "start_time": datetime(2023, 6, 1),
                    "stop_time": datetime(2023, 6, 30),
                }
            )

            self.assertEqual([p.id for p in products], [_S2_ID])


class TestUnconfiguredAndBareArchive(unittest.TestCase):
    def _query(self):
        return {"collection": "S2_MSI_L1C", "start_time": datetime(2023, 6, 1), "stop_time": datetime(2023, 6, 30)}

    def test_unconfigured_handler_is_inert(self):
        h = SatelliteOfflineCallHandler(ScrappiContext())
        self.assertEqual(h.list_collections(), [])
        with self.assertWarns(UserWarning):
            self.assertEqual(len(h.perform_query(self._query())), 0)

    def test_archive_without_a_stac_tree_warns_and_returns_empty(self):
        with TemporaryDirectory() as bare:
            os.makedirs(os.path.join(bare, "S2_MSI_L1C"))
            open(os.path.join(bare, "S2_MSI_L1C", f"{_S2_ID}.zip"), "w").close()
            h = SatelliteOfflineCallHandler(ScrappiContext(), archive_path=bare)
            with self.assertWarns(UserWarning):
                self.assertEqual(len(h.perform_query(self._query())), 0)


class TestMetadataViaEoio(unittest.TestCase):
    def setUp(self):
        self.handler = SatelliteOfflineCallHandler(ScrappiContext(), archive_path="/nonexistent")

    def test_raises_a_clear_import_error_when_eoio_is_not_installed(self):
        # genuinely not installed in this environment -- no faking needed
        with self.assertRaises(ImportError) as ctx:
            self.handler._metadata_via_eoio("/archive/S2A_TEST.SAFE")
        self.assertIn("scrappi[satellite_offline]", str(ctx.exception))

    def test_extracts_geometry_datetime_platform_and_cloud_cover(self):
        geom = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
        basic = {
            "platform": "S2A",
            "product_datetime": "2023-06-07T10:46:21Z",
            "footprint": {"geometry": geom},
        }
        product_md = {"cloudy_pixel_percentage": 12.0}
        with unittest.mock.patch.dict(sys.modules, _fake_eoio_modules({"S2A_TEST.SAFE": (basic, product_md)})):
            meta = self.handler._metadata_via_eoio("/archive/S2A_TEST.SAFE")

        self.assertEqual(meta["geometry"], geom)
        self.assertEqual(meta["start_time"], "2023-06-07T10:46:21Z")
        self.assertEqual(meta["platform"], "S2A")
        self.assertEqual(meta["cloud_fraction"], 12.0)

    def test_warns_and_returns_none_when_eoio_has_no_reader_for_the_product(self):
        with unittest.mock.patch.dict(sys.modules, _fake_eoio_modules({})):
            with self.assertWarns(UserWarning):
                meta = self.handler._metadata_via_eoio("/archive/UNKNOWN_FORMAT.bin")
        self.assertIsNone(meta)

    def test_warns_and_returns_none_when_geometry_or_datetime_is_missing(self):
        basic = {"platform": "S2A", "product_datetime": None, "footprint": {"geometry": None}}
        with unittest.mock.patch.dict(sys.modules, _fake_eoio_modules({"X.SAFE": (basic, {})})):
            with self.assertWarns(UserWarning):
                meta = self.handler._metadata_via_eoio("/archive/X.SAFE")
        self.assertIsNone(meta)


class TestBuildProductItem(unittest.TestCase):
    def setUp(self):
        self.handler = SatelliteOfflineCallHandler(ScrappiContext(), archive_path="/nonexistent")
        self.geom = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])

    def test_strip_container_suffix(self):
        self.assertEqual(self.handler._strip_container_suffix(f"{_S2_ID}.SAFE"), _S2_ID)
        self.assertEqual(self.handler._strip_container_suffix(_S2_ID), _S2_ID)
        self.assertEqual(self.handler._strip_container_suffix("foo.tar.gz"), "foo")

    def test_fast_metadata_from_name_is_unimplemented_by_default(self):
        self.assertIsNone(self.handler._fast_metadata_from_name("/x/S2A_TEST.SAFE", "S2_MSI_L1C"))

    def test_none_when_neither_fast_path_nor_eoio_has_metadata(self):
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=None):
            product = self.handler._build_product_item("/archive/S2A_TEST.SAFE", "S2_MSI_L1C")
        self.assertIsNone(product)

    def test_fast_path_is_tried_before_eoio(self):
        meta = {"geometry": self.geom, "start_time": "2023-06-07T00:00:00Z"}
        with (
            unittest.mock.patch.object(self.handler, "_fast_metadata_from_name", return_value=meta),
            unittest.mock.patch.object(self.handler, "_metadata_via_eoio") as eoio_mock,
        ):
            product = self.handler._build_product_item("/archive/S2A_TEST.SAFE", "S2_MSI_L1C")
        self.assertIsNotNone(product)
        eoio_mock.assert_not_called()

    def test_minus_one_cloud_fraction_is_normalised_to_nan(self):
        """Same USGS/Landsat "not calculated" sentinel EODAGCallHandler.perform_query
        normalises -- see that fix."""
        meta = {"geometry": self.geom, "start_time": "2023-06-07T00:00:00Z", "cloud_fraction": -1}
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=meta):
            product = self.handler._build_product_item(f"/archive/{_S2_ID}.SAFE", "S2_MSI_L1C")
        self.assertTrue(math.isnan(product.cloud_fraction))

    def test_platform_preferentially_parsed_from_the_recognised_name(self):
        meta = {"geometry": self.geom, "start_time": "2023-06-07T00:00:00Z", "platform": "meta-says-something-else"}
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=meta):
            product = self.handler._build_product_item(f"/archive/{_S2_ID}.SAFE", "S2_MSI_L1C")
        self.assertEqual(product.platform, "S2A")

    def test_platform_falls_back_to_eoio_metadata_for_an_unrecognised_name(self):
        meta = {"geometry": self.geom, "start_time": "2023-06-07T00:00:00Z", "platform": "WEIRDSAT"}
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=meta):
            product = self.handler._build_product_item("/archive/totally_unrecognised_name", "S2_MSI_L1C")
        self.assertEqual(product.platform, "WEIRDSAT")


class TestHarvest(unittest.TestCase):
    """SatelliteOfflineCallHandler.harvest(): builds the STAC index perform_query
    reads, for an archive of bare product files scrappi never downloaded (so
    nothing wrote a STAC record for it)."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.coll_dir = os.path.join(self.root, "S2_MSI_L1C")
        self.safe = os.path.join(self.coll_dir, "data", f"{_S2_ID}.SAFE")
        os.makedirs(self.safe)
        open(os.path.join(self.safe, "MTD_MSIL1C.xml"), "w").close()
        self.handler = SatelliteOfflineCallHandler(ScrappiContext(), archive_path=self.root)
        self.meta = {
            "geometry": Polygon([(0, 0), (2, 0), (2, 2), (0, 2)]),
            "start_time": "2023-06-07T10:46:21Z",
            "platform": "S2A",
            "cloud_fraction": 12.0,
        }

    def _query(self, **over):
        q = {
            "collection": "S2_MSI_L1C",
            "start_time": datetime(2023, 6, 1),
            "stop_time": datetime(2023, 6, 30),
        }
        q.update(over)
        return q

    def test_writes_a_stac_item_and_collection_json(self):
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=self.meta):
            n = self.handler.harvest("S2_MSI_L1C")

        self.assertEqual(n, 1)
        item_path = os.path.join(self.coll_dir, "stac", "S2_MSI_L1C", "items", f"{_S2_ID}.json")
        self.assertTrue(os.path.exists(item_path))
        collection_path = os.path.join(self.coll_dir, "stac", "S2_MSI_L1C", "collection.json")
        self.assertTrue(os.path.exists(collection_path))
        with open(collection_path) as f:
            self.assertEqual(json.load(f)["id"], "S2_MSI_L1C")

    def test_harvested_archive_is_then_queryable(self):
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=self.meta):
            self.handler.harvest("S2_MSI_L1C")

        products = self.handler.perform_query(self._query())

        self.assertEqual([p.id for p in products], [_S2_ID])
        self.assertEqual(products[0].platform, "S2A")

    def test_skips_an_already_harvested_product_unless_overwrite(self):
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=self.meta) as m:
            self.handler.harvest("S2_MSI_L1C")
            n_again = self.handler.harvest("S2_MSI_L1C")
        self.assertEqual(n_again, 0)
        m.assert_called_once()  # not re-extracted for the already-harvested product

        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=self.meta):
            n_overwrite = self.handler.harvest("S2_MSI_L1C", overwrite=True)
        self.assertEqual(n_overwrite, 1)

    def test_skips_a_product_with_no_extractable_metadata(self):
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=None):
            n = self.handler.harvest("S2_MSI_L1C")
        self.assertEqual(n, 0)
        self.assertFalse(os.path.isdir(os.path.join(self.coll_dir, "stac")))

    def test_clears_the_cache_so_a_query_on_the_same_instance_sees_new_items(self):
        self.assertEqual(self.handler.list_collections(), [])  # populates the (empty) discovery cache

        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=self.meta):
            self.handler.harvest("S2_MSI_L1C")

        self.assertEqual(self.handler.list_collections(), ["S2_MSI_L1C"])

    def test_perform_query_never_calls_eoio_even_after_harvesting(self):
        """The whole point of harvesting separately: perform_query only ever reads
        the already-built STAC index, regardless of what harvest() needed."""
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=self.meta):
            self.handler.harvest("S2_MSI_L1C")

        with unittest.mock.patch.object(SatelliteOfflineCallHandler, "_metadata_via_eoio") as eoio_mock:
            products = self.handler.perform_query(self._query())

        eoio_mock.assert_not_called()
        self.assertEqual(len(products), 1)


if __name__ == "__main__":
    unittest.main()
