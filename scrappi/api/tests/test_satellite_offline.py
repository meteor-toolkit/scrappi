"""Tests for scrappi.api.satellite_offline.SatelliteOfflineCallHandler (skeleton).

Each test builds a minimal version of the archive layout the handler expects --
scrappi's ``stac/`` tree plus the data product -- and checks the
query / download / to_stac_item flow.
"""

import json
import math
import os
import re
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
    """sys.modules entries faking eoio.read (the one common entry point
    _metadata_via_eoio calls), so it can be exercised without the real
    (optional, lazily imported) eoio package installed.

    metadata_by_filename[os.path.basename(path)] = (basic, product); a path with
    no entry raises, like eoio does for a product no reader recognises. Mirrors
    eoio's own attach_metadata (eoio/readers/metadata.py): basic is merged
    straight into the returned "Dataset"'s .attrs, product is nested under
    attrs["product_metadata"] -- only when read_params requests metadata_level,
    same as the real thing (attach_metadata is never called at all otherwise)."""

    class _FakeDataset:
        def __init__(self, attrs):
            self.attrs = attrs

    def _fake_read(path, vars_sel=None, subset=None, read_params=None, *args, **kwargs):
        if os.path.basename(path) not in metadata_by_filename:
            raise ValueError(f"no fake eoio reader registered for {path!r}")
        basic, product = metadata_by_filename[os.path.basename(path)]
        attrs = {}
        if read_params and read_params.get("metadata_level"):
            attrs.update(basic)
            attrs["product_metadata"] = product
        return _FakeDataset(attrs)

    eoio_pkg = types.ModuleType("eoio")
    eoio_pkg.read = _fake_read
    return {"eoio": eoio_pkg}


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

    def test_cloud_fraction_falls_back_to_cloud_area_fraction(self):
        """Readers other than S2 (e.g. Planet's) report cloud_area_fraction; a legitimate 0
        must be kept, not treated as missing."""
        geom = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
        basic = {"platform": "251b", "product_datetime": "2025-01-08T09:26:01", "footprint": {"geometry": geom}}
        for reported in (0, 35.0):
            with unittest.mock.patch.dict(
                sys.modules, _fake_eoio_modules({"X.tif": (basic, {"cloud_area_fraction": reported})})
            ):
                meta = self.handler._metadata_via_eoio("/archive/X.tif")
            self.assertEqual(meta["cloud_fraction"], reported)

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
            product = self.handler._build_product_item("/archive/S2A_TEST.SAFE", "S2A_TEST", "S2_MSI_L1C")
        self.assertIsNone(product)

    def test_fast_path_is_tried_before_eoio(self):
        meta = {"geometry": self.geom, "start_time": "2023-06-07T00:00:00Z"}
        with (
            unittest.mock.patch.object(self.handler, "_fast_metadata_from_name", return_value=meta),
            unittest.mock.patch.object(self.handler, "_metadata_via_eoio") as eoio_mock,
        ):
            product = self.handler._build_product_item("/archive/S2A_TEST.SAFE", "S2A_TEST", "S2_MSI_L1C")
        self.assertIsNotNone(product)
        eoio_mock.assert_not_called()

    def test_incomplete_fast_path_metadata_falls_through_to_eoio(self):
        """Regression test: a _fast_metadata_from_name override returning a
        non-empty but incomplete dict (e.g. missing start_time) used to be treated
        as a real answer (truthy), so meta["start_time"] raised an uncaught
        KeyError instead of falling through to eoio like missing/None eoio
        metadata already does."""
        incomplete = {"geometry": self.geom}  # no start_time
        complete = {"geometry": self.geom, "start_time": "2023-06-07T00:00:00Z"}
        with (
            unittest.mock.patch.object(self.handler, "_fast_metadata_from_name", return_value=incomplete),
            unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=complete) as eoio_mock,
        ):
            product = self.handler._build_product_item("/archive/S2A_TEST.SAFE", "S2A_TEST", "S2_MSI_L1C")
        eoio_mock.assert_called_once()
        self.assertIsNotNone(product)

    def test_minus_one_cloud_fraction_is_normalised_to_nan(self):
        """Same USGS/Landsat "not calculated" sentinel EODAGCallHandler.perform_query
        normalises (via the shared BaseAPICallHandler.normalize_cloud_fraction)."""
        meta = {"geometry": self.geom, "start_time": "2023-06-07T00:00:00Z", "cloud_fraction": -1}
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=meta):
            product = self.handler._build_product_item(f"/archive/{_S2_ID}.SAFE", _S2_ID, "S2_MSI_L1C")
        self.assertTrue(math.isnan(product.cloud_fraction))

    def test_platform_preferentially_parsed_from_the_recognised_name(self):
        meta = {"geometry": self.geom, "start_time": "2023-06-07T00:00:00Z", "platform": "meta-says-something-else"}
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=meta):
            product = self.handler._build_product_item(f"/archive/{_S2_ID}.SAFE", _S2_ID, "S2_MSI_L1C")
        self.assertEqual(product.platform, "S2A")

    def test_platform_falls_back_to_eoio_metadata_for_an_unrecognised_name(self):
        meta = {"geometry": self.geom, "start_time": "2023-06-07T00:00:00Z", "platform": "WEIRDSAT"}
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=meta):
            product = self.handler._build_product_item(
                "/archive/totally_unrecognised_name", "totally_unrecognised_name", "S2_MSI_L1C"
            )
        self.assertEqual(product.platform, "WEIRDSAT")


_PLANET_ID = "20250108_092601_62_251b_3B_AnalyticMS_8b_clip"


class TestHarvestPlanetSuperDove(unittest.TestCase):
    """A SuperDove scene is several files (image tif, udm2 mask tif, xml, json): only the
    8-band analytic image is a product -- eoio's reader factory says which, nothing here does."""

    COLLECTION = "PLANET_SUPERDOVE"

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.data = os.path.join(self.root, self.COLLECTION, "data", "GONA-JAN25", "PSScene")
        os.makedirs(self.data)
        scene = "20250108_092601_62_251b"
        self.files = [
            f"{scene}_3B_AnalyticMS_8b_clip.tif",  # the product
            f"{scene}_3B_udm2_clip.tif",
            f"{scene}_3B_AnalyticMS_8b_metadata_clip.xml",
            f"{scene}_metadata.json",
            f"{scene}.json",
        ]
        for f in self.files:
            open(os.path.join(self.data, f), "w").close()
        self.handler = SatelliteOfflineCallHandler(ScrappiContext(), archive_path=self.root)
        self.meta = {
            "geometry": Polygon([(15.1, -23.6), (15.13, -23.6), (15.13, -23.59), (15.1, -23.59)]),
            "start_time": "2025-01-08T09:26:01",
            "platform": "251b",
            "cloud_fraction": 0,
        }
        # eoio's planetscope pattern (eoio.readers.factory)
        self.reader_for = unittest.mock.patch.object(
            self.handler,
            "_has_eoio_reader",
            side_effect=lambda name: bool(re.search(r".*AnalyticMS.*8b.*.tif\Z", name)),
        )
        self.reader_for.start()
        self.addCleanup(self.reader_for.stop)

    def test_only_the_analytic_image_is_harvested(self):
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=self.meta) as m:
            n = self.handler.harvest(self.COLLECTION)

        self.assertEqual(n, 1)
        m.assert_called_once()
        self.assertTrue(m.call_args.args[0].endswith("_3B_AnalyticMS_8b_clip.tif"))

    def test_item_id_has_no_tif_extension_and_platform_is_the_constellation(self):
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=self.meta):
            self.handler.harvest(self.COLLECTION)
        products = self.handler.perform_query(
            {"collection": self.COLLECTION, "start_time": datetime(2025, 1, 1), "stop_time": datetime(2025, 2, 1)}
        )
        self.assertEqual([p.id for p in products], [_PLANET_ID])
        self.assertEqual(products[0].platform, "SuperDove")
        self.assertEqual(products[0].constellation, "PlanetScope")

    def test_product_resolves_to_its_tif_in_the_archive(self):
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=self.meta):
            self.handler.harvest(self.COLLECTION)
        (product,) = self.handler.perform_query(
            {"collection": self.COLLECTION, "start_time": datetime(2025, 1, 1), "stop_time": datetime(2025, 2, 1)}
        )
        path = self.handler.download_product(product)
        self.assertEqual(os.path.basename(path), f"{_PLANET_ID}.tif")


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

    def test_raises_for_an_empty_or_none_collection(self):
        with self.assertRaises(ValueError):
            self.handler.harvest("")
        with self.assertRaises(ValueError):
            self.handler.harvest(None)

    def test_warns_and_returns_zero_when_there_is_nothing_to_harvest(self):
        empty_root = os.path.join(self.root, "LANDSAT_C2L1", "data")
        os.makedirs(empty_root)
        with self.assertWarns(UserWarning):
            n = self.handler.harvest("LANDSAT_C2L1")
        self.assertEqual(n, 0)

    def test_collection_json_carries_constellation_and_platform(self):
        """Parity with ProductItem.register_in_filesystem_catalog's own
        collection.json (an online download's), which sets the same two fields."""
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=self.meta):
            self.handler.harvest("S2_MSI_L1C")

        with open(os.path.join(self.coll_dir, "stac", "S2_MSI_L1C", "collection.json")) as f:
            data = json.load(f)
        self.assertEqual(data["constellation"], "Sentinel-2")
        self.assertEqual(data["platform"], "S2A")

    def test_one_bad_product_does_not_abort_the_rest_of_the_batch(self):
        """Regression test: harvest()'s loop used to have no per-product error
        handling, so one product's metadata extraction blowing up (a corrupt file,
        an eoio ImportError encountered mid-batch) killed the whole run instead of
        being skipped like a malformed STAC item already is at query time."""
        second_safe = os.path.join(self.coll_dir, "data", "BAD_PRODUCT.SAFE")
        os.makedirs(second_safe)
        open(os.path.join(second_safe, "x"), "w").close()

        def side_effect(path):
            if "BAD_PRODUCT" in path:
                raise RuntimeError("simulated corrupt manifest")
            return self.meta

        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", side_effect=side_effect):
            with self.assertWarns(UserWarning):
                n = self.handler.harvest("S2_MSI_L1C")

        self.assertEqual(n, 1)  # the good product was still harvested
        self.assertTrue(os.path.exists(os.path.join(self.coll_dir, "stac", "S2_MSI_L1C", "items", f"{_S2_ID}.json")))

    def test_cache_is_cleared_even_when_nothing_new_was_harvested(self):
        """Regression test: the archive-index cache used to only clear when n > 0,
        so a no-op re-harvest left a stale (empty-of-new-files) data-dir listing
        cached with no expiry -- a file arriving after that no-op run would become
        permanently invisible to this handler instance."""
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=self.meta):
            self.handler.harvest("S2_MSI_L1C")  # n=1, populates the data-dir index cache
            n_noop = self.handler.harvest("S2_MSI_L1C")  # n=0 -- already harvested
        self.assertEqual(n_noop, 0)

        # a new product arrives on disk after the no-op run
        new_safe = os.path.join(self.coll_dir, "data", "NEW_PRODUCT.SAFE")
        os.makedirs(new_safe)
        open(os.path.join(new_safe, "x"), "w").close()

        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=self.meta):
            n_next = self.handler.harvest("S2_MSI_L1C")

        self.assertEqual(n_next, 1)  # found, not hidden by a stale cached listing

    def test_does_not_duplicate_an_item_that_already_exists_at_an_organised_path(self):
        """Regression test: an online download writes its STAC item at an
        organised, dated path (fs.organise_data defaults True), not the flat path
        harvest() writes new items at. harvest() used to only check the flat path
        for "already harvested", so it re-extracted metadata and wrote a *second*,
        duplicate item for the same id -- and perform_query's recursive walk
        would then return the same product twice."""
        dated_item_path = os.path.join(
            self.coll_dir, "stac", "S2_MSI_L1C", "items", "2023", "06", "07", f"{_S2_ID}.json"
        )
        _write_json(dated_item_path, _stac_item(_S2_ID, "S2_MSI_L1C"))
        _write_json(
            os.path.join(self.coll_dir, "stac", "S2_MSI_L1C", "collection.json"),
            _collection_json("S2_MSI_L1C"),
        )

        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio") as eoio_mock:
            n = self.handler.harvest("S2_MSI_L1C")

        self.assertEqual(n, 0)
        eoio_mock.assert_not_called()
        flat_item_path = os.path.join(self.coll_dir, "stac", "S2_MSI_L1C", "items", f"{_S2_ID}.json")
        self.assertFalse(os.path.exists(flat_item_path))

        products = self.handler.perform_query(self._query())
        self.assertEqual(len(products), 1)  # not duplicated

    def test_overwrite_rewrites_the_existing_item_in_place_not_a_duplicate(self):
        dated_item_path = os.path.join(
            self.coll_dir, "stac", "S2_MSI_L1C", "items", "2023", "06", "07", f"{_S2_ID}.json"
        )
        _write_json(dated_item_path, _stac_item(_S2_ID, "S2_MSI_L1C"))
        _write_json(
            os.path.join(self.coll_dir, "stac", "S2_MSI_L1C", "collection.json"),
            _collection_json("S2_MSI_L1C"),
        )

        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=self.meta):
            n = self.handler.harvest("S2_MSI_L1C", overwrite=True)

        self.assertEqual(n, 1)
        flat_item_path = os.path.join(self.coll_dir, "stac", "S2_MSI_L1C", "items", f"{_S2_ID}.json")
        self.assertFalse(os.path.exists(flat_item_path))  # rewritten in place, not a new duplicate
        with open(dated_item_path) as f:
            self.assertEqual(json.load(f)["id"], _S2_ID)


class TestHarvestWithoutASeparateDataSubdirectory(unittest.TestCase):
    """<collection_root>/{files directly here, no data/ split}/ + <collection_root>/stac/"""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.coll_dir = os.path.join(self.root, "S2_MSI_L1C")
        self.safe = os.path.join(self.coll_dir, f"{_S2_ID}.SAFE")
        os.makedirs(self.safe)
        open(os.path.join(self.safe, "MTD_MSIL1C.xml"), "w").close()
        self.handler = SatelliteOfflineCallHandler(ScrappiContext(), archive_path=self.root)
        self.meta = {"geometry": Polygon([(0, 0), (2, 0), (2, 2), (0, 2)]), "start_time": "2023-06-07T10:46:21Z"}

    def test_reharvesting_does_not_walk_its_own_stac_output_as_product_data(self):
        """Regression test: with no separate data/ subdirectory, _data_dir() falls
        back to the collection root itself -- the same directory harvest() writes
        stac/ into. Without excluding that stac/ tree from the data walk, a
        re-harvest indexed its own item/collection json as if they were candidate
        products, and (since real archives commonly don't have eoio installed --
        querying an already-harvested archive is explicitly supported without it)
        blew up with an uncaught ImportError on the second call."""
        with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=self.meta):
            n_first = self.handler.harvest("S2_MSI_L1C")
        self.assertEqual(n_first, 1)

        # second call: eoio "not installed" (raises, as the real import does) --
        # must not even be reached for the handler's own stac/collection json
        with unittest.mock.patch.object(
            self.handler, "_metadata_via_eoio", side_effect=ImportError("eoio not installed")
        ):
            n_second = self.handler.harvest("S2_MSI_L1C")
        self.assertEqual(n_second, 0)


_HIVE_ID = "HIVE_L1C_SBA02_20260703T115605Z_A715C2314D_20260903T142658Z"


class TestGenericProductDiscovery(unittest.TestCase):
    """harvest() decides what a product is by asking eoio (not a per-collection table), and records
    where it found it so a query resolves it exactly -- whatever the product's layout."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.coll_dir = os.path.join(self.root, "CONSTELLR_HIVE")
        self.site_dir = os.path.join(self.coll_dir, "data", "gobabeb")
        self.product = os.path.join(self.site_dir, _HIVE_ID)  # a plain directory: no .SAFE-style suffix
        os.makedirs(self.product)
        for name in ("vnir02.tiff", "vnir02_qa.tiff", "metadata.json"):
            open(os.path.join(self.product, name), "w").close()
        self.handler = SatelliteOfflineCallHandler(ScrappiContext(), archive_path=self.root)
        self.meta = {
            "geometry": Polygon([(0, 0), (2, 0), (2, 2), (0, 2)]),
            "start_time": "2026-07-03T11:56:05",
            "platform": "Skybee",
            "constellation": "HIVE",
            "cloud_fraction": 60.1,
        }
        self.read_for = unittest.mock.patch.object(
            self.handler, "_has_eoio_reader", side_effect=lambda name: name.startswith("HIVE_L1C_")
        )
        self.meta_for = unittest.mock.patch.object(self.handler, "_metadata_via_eoio", return_value=self.meta)

    def _query(self):
        return {"collection": "CONSTELLR_HIVE", "start_time": datetime(2026, 7, 1), "stop_time": datetime(2026, 7, 31)}

    def _item_path(self):
        return os.path.join(self.coll_dir, "stac", "CONSTELLR_HIVE", "items", f"{_HIVE_ID}.json")

    def test_a_directory_product_is_one_product_not_its_files(self):
        with self.read_for, self.meta_for as read_meta:
            n = self.handler.harvest("CONSTELLR_HIVE")
        self.assertEqual(n, 1)
        self.assertEqual([c.args[0] for c in read_meta.call_args_list], [self.product])
        self.assertTrue(os.path.exists(self._item_path()))

    def test_platform_and_constellation_come_from_eoio_when_the_name_is_not_recognised(self):
        with self.read_for, self.meta_for:
            self.handler.harvest("CONSTELLR_HIVE")
        (p,) = self.handler.perform_query(self._query())
        self.assertEqual((p.platform, p.constellation), ("Skybee", "HIVE"))
        self.assertEqual(p.cloud_fraction, 60.1)

    def test_item_records_the_product_location_relative_to_the_data_dir(self):
        with self.read_for, self.meta_for:
            self.handler.harvest("CONSTELLR_HIVE")
        with open(self._item_path()) as f:
            self.assertEqual(json.load(f)["properties"]["scrappi:archive_path"], f"gobabeb/{_HIVE_ID}")

    def test_download_resolves_the_directory_from_the_recorded_location(self):
        with self.read_for, self.meta_for:
            self.handler.harvest("CONSTELLR_HIVE")
        (p,) = self.handler.perform_query(self._query())
        with unittest.mock.patch.object(self.handler, "_index_of", side_effect=AssertionError("walked")):
            path = self.handler.download_product(p)
        self.assertEqual(os.path.normpath(path), os.path.normpath(self.product))

    def test_a_recorded_location_outside_the_data_dir_is_ignored(self):
        with self.read_for, self.meta_for:
            self.handler.harvest("CONSTELLR_HIVE")
        with open(self._item_path()) as f:
            item = json.load(f)
        item["properties"]["scrappi:archive_path"] = "../../../etc"
        with open(self._item_path(), "w") as f:
            json.dump(item, f)
        self.handler.clear_cache()
        (p,) = self.handler.perform_query(self._query())
        self.assertIsNone(self.handler._recorded_path(p, os.path.join(self.coll_dir, "data")))

    def test_a_product_rebuilt_elsewhere_still_resolves_by_id(self):
        """eomatch rebuilds products from its own catalogue (no scrappi:archive_path, possibly no
        prod_dict) before asking the handler to download them."""
        with self.read_for, self.meta_for:
            self.handler.harvest("CONSTELLR_HIVE")
        (p,) = self.handler.perform_query(self._query())
        p.prod_dict = None
        path = self.handler.download_product(p)
        self.assertEqual(os.path.normpath(path), os.path.normpath(self.product))

    def test_a_non_product_directory_that_matches_a_reader_by_accident_is_searched(self):
        """eoio's factory patterns are loose (e.g. any name containing "nc"): a folder it claims,
        whose metadata can't be read, is walked into rather than skipped with its contents."""
        wrapper = os.path.join(self.coll_dir, "data", "lancaster")
        os.makedirs(wrapper)
        os.rename(self.site_dir, os.path.join(wrapper, "gobabeb"))
        has_reader = lambda name: name.startswith("HIVE_L1C_") or name == "lancaster"  # noqa: E731

        def meta_for(path):
            return self.meta if os.path.basename(path).startswith("HIVE_L1C_") else None

        with unittest.mock.patch.object(self.handler, "_has_eoio_reader", side_effect=has_reader):
            with unittest.mock.patch.object(self.handler, "_metadata_via_eoio", side_effect=meta_for):
                n = self.handler.harvest("CONSTELLR_HIVE")
        self.assertEqual(n, 1)

    def test_files_and_directories_eoio_has_no_reader_for_are_ignored_silently(self):
        open(os.path.join(self.site_dir, "notes.txt"), "w").close()
        os.makedirs(os.path.join(self.site_dir, "scratch"))
        with self.read_for, self.meta_for as read_meta:
            with unittest.mock.patch("warnings.warn") as warn:
                n = self.handler.harvest("CONSTELLR_HIVE")
        self.assertEqual(n, 1)
        self.assertEqual(read_meta.call_count, 1)
        warn.assert_not_called()

    def test_a_file_product_is_found_too(self):
        os.rename(self.product, os.path.join(self.site_dir, "scene_x"))
        scene = os.path.join(self.site_dir, "SCENE_1_8b.tif")
        open(scene, "w").close()
        with unittest.mock.patch.object(self.handler, "_has_eoio_reader", side_effect=lambda n: n.endswith("8b.tif")):
            with self.meta_for:
                n = self.handler.harvest("CONSTELLR_HIVE")
        self.assertEqual(n, 1)
        (p,) = self.handler.perform_query(self._query())
        self.assertEqual(os.path.normpath(self.handler.download_product(p)), os.path.normpath(scene))

    def test_nothing_eoio_can_read_warns(self):
        with unittest.mock.patch.object(self.handler, "_has_eoio_reader", return_value=False):
            with self.assertWarns(UserWarning):
                self.assertEqual(self.handler.harvest("CONSTELLR_HIVE"), 0)

    def test_reharvest_does_not_need_eoio(self):
        with self.read_for, self.meta_for:
            self.handler.harvest("CONSTELLR_HIVE")
        with unittest.mock.patch.dict(sys.modules, {"eoio": None, "eoio.readers": None, "eoio.readers.factory": None}):
            self.assertEqual(self.handler.harvest("CONSTELLR_HIVE"), 0)

    def test_missing_eoio_is_a_clear_import_error(self):
        with unittest.mock.patch.dict(sys.modules, {"eoio": None, "eoio.readers": None, "eoio.readers.factory": None}):
            with self.assertRaisesRegex(ImportError, "scrappi\\[satellite_offline\\]"):
                self.handler.harvest("CONSTELLR_HIVE")

    def test_uses_eoios_own_reader_factory(self):
        try:
            from eoio.readers.factory import ReaderFactory  # noqa: F401
        except ImportError:
            self.skipTest("eoio not installed")
        self.assertTrue(self.handler._has_eoio_reader(f"{_S2_ID}.SAFE"))
        self.assertFalse(self.handler._has_eoio_reader("notes.txt"))


if __name__ == "__main__":
    unittest.main()
