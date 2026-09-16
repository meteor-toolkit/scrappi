"""Offline (archive-backed) handler for satellite scenes.

What this is
------------
The satellite counterpart to
:py:class:`~scrappi.api.radcalnet_api_client.RadcalnetOfflineCallHandler` /
:py:class:`~scrappi.api.hypernets.HYPERNETSOfflineCallHandler`: it answers the
same ``perform_query`` / ``download_product`` interface as the online eodag
handler but reads scenes from a local directory tree the user already holds, for
use as a fallback in the candidate-API fan-out (registered after ``"eodag"`` in
:py:mod:`scrappi.api.factory`).

Unlike the in-situ offline handlers, a satellite scene's footprint polygon,
acquisition times and cloud cover are **not** derivable from its filename or a
site registry -- they need a metadata record per product. This handler reads that
record from a **STAC catalogue tree** -- either the one scrappi writes
automatically on an online download, or one built for an archive scrappi never
downloaded by calling :py:meth:`SatelliteOfflineCallHandler.harvest` once.

Two phases, deliberately kept separate
---------------------------------------
:py:meth:`perform_query` **never reads a product file**. It only ever reads
already-built STAC item json -- a `pystac` parse of a small file, independent of
product size or format. This is what keeps a query fast regardless of archive
size, and it's why this handler has no dependency on anything beyond scrappi's
own core (``pystac``, already a hard dependency).

:py:meth:`harvest` is the (comparatively slow, one-off or periodically re-run)
step that *builds* that STAC tree for an archive of bare product files -- data
scrappi never downloaded, so nothing wrote a STAC record for it, e.g. data
received directly from a provider with no online API to query. For a scene whose
footprint/time genuinely isn't in its filename, harvesting reads the product's own
manifest via **eoio** (a lazy import, and an optional extra --
``pip install 'scrappi[satellite_offline]'`` -- not needed at all for querying an
already-harvested archive, nor for any other scrappi API). eoio's metadata
extractors parse the product's XML/JSON manifest only -- footprint and
acquisition time, no raster access -- so harvesting one product is a small,
bounded cost, but it is still a per-product cost, which is exactly why it happens
once (:py:meth:`harvest`) rather than on every :py:meth:`perform_query`.

Before reaching for eoio, :py:meth:`_fast_metadata_from_name` gets first refusal:
a hook for a mission-specific *filename-only* parse (no file read at all), the
same shape as the in-situ offline handlers deriving everything from a filename
grammar plus a site registry. It returns ``None`` by default (no mission is wired
up yet) and harvesting falls through to eoio; a subclass -- or a future
contribution here -- can override it for a mission whose filename plus e.g. a
static tile grid fully determines footprint + time without opening the file at
all.

The resulting tree is the same shape scrappi writes on an online download::

    <collection_root>/data/...                          # untouched -- already there
    <collection_root>/stac/<collection>/items/<id>.json
    <collection_root>/stac/<collection>/collection.json

An archive with **no** ``stac/`` tree at all for a requested collection --
harvested or otherwise -- is not served by :py:meth:`perform_query`: it returns an
empty set and warns, naming :py:meth:`harvest` as the fix.

Per-collection roots
--------------------
So a query doesn't walk a whole shared archive, each collection is searched under
its own subtree:

1. ``context["api"]["offline_archive_paths"][collection]`` -- explicit override;
2. wherever :py:meth:`_discover` (a bounded ``collection.json`` glob, not a full
   walk) already found this collection's STAC tree;
3. ``<archive_path>/<collection>/`` if that directory exists at all -- not
   conditional on a ``stac/`` dir already being there, since :py:meth:`harvest`
   uses this same resolution to find a not-yet-harvested collection's data;
4. ``<archive_path>`` itself.
"""

from __future__ import annotations

import glob
import json
import math
import os
import warnings
from typing import Any, Dict, List, Optional, Set, Tuple

import pystac

from scrappi.api.offlinebase import OfflineArchiveHandler
from scrappi.api.offline_query import compile_query, query_collections
from scrappi.product import ProductItem, ProductItemSet, product_item_from_stac

__author__ = ["Maddie Stedman <maddie.stedman@npl.co.uk>"]
__all__ = ["SatelliteOfflineCallHandler"]

#: json filenames that are catalogue nodes, not product items
_NON_ITEM_JSON = frozenset({"catalog.json", "collection.json"})


def _collection_of(item_path: str) -> Optional[str]:
    """The collection id from a STAC item path laid out ``.../stac/<collection>/...``
    -- ``product_item_from_stac`` leaves ``ProductItem.collection`` unset for a
    standalone item whose collection is only a top-level ``"collection"`` key.

    Uses the *last* ``stac`` path segment, not the first: the archive root itself
    may legitimately contain a directory literally named ``stac`` (e.g.
    ``archive_path=".../stac_archives/sentinel2"``) before the one scrappi's own
    tree introduces: ``.../stac_archives/sentinel2/stac/S2_MSI_L1C/items/...``.
    """
    parts = os.path.normpath(item_path).split(os.sep)
    stac_positions = [i for i, p in enumerate(parts) if p == "stac"]
    if not stac_positions or stac_positions[-1] + 1 >= len(parts):
        return None
    return parts[stac_positions[-1] + 1]


class SatelliteOfflineCallHandler(OfflineArchiveHandler):
    """Resolve satellite scenes from a local archive carrying scrappi's STAC tree.

    :param context: :py:class:`~scrappi.ScrappiContext`.
    :param archive_path: archive root. Falls back to
        ``context["api"]["offline_archive_path"]``; there is no built-in default,
        and an unconfigured handler is inert (see :py:meth:`_default_archive_path`).
    """

    name = "eodag_offline"

    #: archive root read from here when archive_path isn't passed to __init__
    ARCHIVE_PATH_CONTEXT_KEYS: Tuple[str, ...] = ("api", "offline_archive_path")

    #: extracted Sentinel scenes are whole-product directories
    INDEX_DIRECTORY_SUFFIXES: Tuple[str, ...] = (".SAFE", ".SEN3")

    #: a STAC item id is the product name without an extension; on disk the data
    #: may carry one of these (never ``.json`` -- that's the item sidecar).
    PRODUCT_NAME_SUFFIXES: Tuple[str, ...] = (".SAFE", ".SEN3", ".zip", ".nc", ".tar.gz", ".tar")

    def _default_archive_path(self) -> str:
        """No built-in default -- there is no sensible NPL-wide "all satellite
        data" location. Returns ``""`` (rather than raising like the base) so an
        unconfigured handler is *inert*: :py:meth:`list_collections` returns ``[]``
        and :py:meth:`perform_query` an empty set, instead of every
        :py:func:`scrappi.get_api_name` probe raising and warning."""
        return ""

    def clear_cache(self) -> None:
        """Drop the cached walk indexes *and* the discovered collections/roots."""
        super().clear_cache()
        self.__dict__.pop("_collections_cache", None)
        self.__dict__.pop("_collection_roots_cache", None)

    @property
    def _configured(self) -> bool:
        return bool(self.archive_path) and os.path.isdir(self.archive_path)

    # ------------------------------------------------------------------ roots
    def _path_overrides(self) -> Dict[str, str]:
        try:
            return dict(self.context["api"].get("offline_archive_paths") or {})
        except Exception:
            return {}

    def _collection_root(self, collection: str) -> str:
        """The directory holding *collection*'s ``stac/`` + data trees.

        Precedence: an explicit override; else wherever :py:meth:`_discover` (the
        same scan :py:meth:`list_collections` uses) actually found this collection's
        ``collection.json`` -- so the two never disagree about a collection that
        exists under a directory not named after the collection id itself (e.g.
        ``<archive_path>/sentinel2/stac/S2_MSI_L1C/...``); else the
        ``<archive_path>/<collection>`` convention if that directory exists at all
        (**not** conditional on a ``stac/`` subdir already being there: before the
        first :py:meth:`harvest` of a bare archive there is no ``stac/`` anywhere
        yet, and this is exactly how ``harvest`` itself locates the data to index);
        else ``<archive_path>`` itself.
        """
        override = self._path_overrides().get(collection)
        if override:
            return override
        discovered = self._discover().get(collection)
        if discovered:
            return discovered
        per_collection = os.path.join(self.archive_path, collection)
        if os.path.isdir(per_collection):
            return per_collection
        return self.archive_path

    def _candidate_roots(self) -> Set[str]:
        """Every directory that might hold a ``stac/`` tree: the archive root,
        its immediate subdirectories, and any configured override path."""
        roots: Set[str] = {self.archive_path}
        roots.update(self._path_overrides().values())
        try:
            roots.update(
                os.path.join(self.archive_path, d)
                for d in os.listdir(self.archive_path)
                if os.path.isdir(os.path.join(self.archive_path, d))
            )
        except OSError:
            pass
        return roots

    # ------------------------------------------------------------------ discovery
    def _collection_ids_at(self, root: str) -> Dict[str, str]:
        """``collection id -> path of its collection.json`` for every
        ``<root>/stac/<collection>/collection.json``."""
        out: Dict[str, str] = {}
        for cj in glob.glob(os.path.join(root, "stac", "*", "collection.json")):
            try:
                with open(cj) as f:
                    cid = json.load(f).get("id")
            except (OSError, ValueError):
                continue
            if cid:
                out.setdefault(cid, cj)
        return out

    def _discover(self) -> Dict[str, str]:
        """``collection id -> the directory holding its stac/ + data trees``, from
        a single scan of :py:meth:`_candidate_roots`. Cached (see
        :py:meth:`clear_cache`); backs both :py:meth:`list_collections` and
        :py:meth:`_collection_root`, so the two can never disagree about where a
        discovered collection actually lives -- unlike resolving each independently
        (``list_collections`` finding a collection by the ``id`` inside its
        ``collection.json`` while ``_collection_root`` separately assumed the
        containing directory was named after that id)."""
        cached = self.__dict__.get("_collection_roots_cache")
        if cached is not None:
            return cached
        roots: Dict[str, str] = {}
        if self._configured:
            for root in self._candidate_roots():
                for cid in self._collection_ids_at(root):
                    roots.setdefault(cid, root)
        self.__dict__["_collection_roots_cache"] = roots
        self.__dict__["_collections_cache"] = sorted(roots)
        return roots

    def list_collections(self, fetch_update: Optional[bool] = False) -> List[str]:
        """Collection ids the archive holds, from every ``stac/*/collection.json``
        under the archive root or a configured path. ``[]`` if the handler is
        unconfigured or there is no STAC tree. Cached (see :py:meth:`clear_cache`).

        :param fetch_update: unused; kept for interface compatibility.
        """
        self._discover()
        return self.__dict__["_collections_cache"]

    def _stac_item_paths(self, stac_root: str) -> List[str]:
        """Absolute paths of every STAC *item* json under *stac_root* (a
        ``<...>/stac`` directory), excluding ``catalog.json`` / ``collection.json``.
        A bounded walk -- ``stac/`` holds only json."""
        if not os.path.isdir(stac_root):
            return []
        out: List[str] = []
        for dirpath, _dirnames, filenames in os.walk(stac_root):
            out.extend(
                os.path.join(dirpath, fn) for fn in filenames if fn.endswith(".json") and fn not in _NON_ITEM_JSON
            )
        return out

    # ------------------------------------------------------------------ query
    def perform_query(self, query: dict) -> ProductItemSet:
        """Every archived scene whose STAC item satisfies *query*.

        :param query: same shape as
            :py:meth:`scrappi.api.eodag.EODAGCallHandler.perform_query`
            (``collection`` / ``collections``, ``geom``, ``start_time``,
            ``stop_time``, optional ``platform``, ``cloud_cover_max``); see
            :py:class:`~scrappi.api.offline_query.CompiledQuery`.
        :returns: matching products; empty (with a warning) if unconfigured, if no
            collection can be resolved, or if the archive has no ``stac/`` tree.
        """
        if not self._configured:
            warnings.warn(
                f"{type(self).__name__}: archive_path {self.archive_path!r} is not a directory "
                f"(set archive_path= or context['api']['offline_archive_path'])"
            )
            return ProductItemSet()

        wanted = query_collections(query) or self.list_collections()
        if not wanted:
            warnings.warn(
                f"{type(self).__name__}: no collection in the query and none discoverable under "
                f"{self.archive_path!r} (needs scrappi's stac/ tree, written on download when "
                f"context['fs']['register_stac_items'] is true)"
            )
            return ProductItemSet()

        compiled = compile_query(query)

        # group collections by the root they resolve to, so a shared root is walked once
        by_root: Dict[str, Set[str]] = {}
        for collection in wanted:
            by_root.setdefault(self._collection_root(collection), set()).add(collection)

        products: List[ProductItem] = []
        found_any_stac = False
        for root, collections in by_root.items():
            item_paths = self._stac_item_paths(os.path.join(root, "stac"))
            if item_paths:
                found_any_stac = True
            for item_path in item_paths:
                product = self._load_item(item_path, collections)
                if product is None or not compiled.matches(product):
                    continue
                self._pin_filesystem(product)
                products.append(product)

        if not found_any_stac:
            warnings.warn(
                f"{type(self).__name__}: no STAC items found for {sorted(wanted)} under "
                f"{sorted(by_root)}. A bare archive of product files with no stac/ tree is "
                f"not supported by this handler."
            )
        return ProductItemSet(products)

    # ------------------------------------------------------------------ item -> product
    def _load_item(self, item_path: str, collections: Set[str]) -> Optional[ProductItem]:
        """Rebuild a :py:class:`~scrappi.product.ProductItem` from a STAC item json
        (no filesystem yet -- :py:meth:`_pin_filesystem` does that only for the
        products a query keeps). Returns ``None`` for a json that won't parse or
        that belongs to a collection outside *collections*."""
        try:
            product = product_item_from_stac(item_path, self.context)
        except Exception as exc:  # a stray / malformed json shouldn't abort the query
            warnings.warn(f"{type(self).__name__}: could not read STAC item {item_path!r}: {exc}")
            return None
        if not product.collection:
            product.collection = _collection_of(item_path) or ((product.prod_dict or {}).get("collection"))
        if product.collection not in collections:
            return None
        product.api = self
        return product

    def _pin_filesystem(self, product: ProductItem) -> None:
        """Attach a flat, read-only :py:class:`~scrappi.fs.stacfilesystem.STACFileSystem`
        pinned to the data file's own directory (or the collection root if the data
        isn't in the archive yet, so :py:meth:`~scrappi.product.ProductItem.to_stac_item`
        still resolves)."""
        data_path = self._archive_path_for(product)
        pin_dir = os.path.dirname(data_path) if data_path else self._collection_root(product.collection)
        product.filesystem = self._flat_filesystem(pin_dir)

    # ------------------------------------------------------------------ download
    def _data_dir(self, collection: Optional[str]) -> str:
        """*collection*'s data subtree: ``<collection_root>/data`` if that exists,
        else ``<collection_root>`` itself. Shared by :py:meth:`_archive_path_for`
        (locating an already-indexed product) and :py:meth:`harvest` (finding
        product files with no STAC item yet) -- the same directory, for the same
        reason: it's where the actual files are, regardless of whether a STAC tree
        has been built for them."""
        root = self._collection_root(collection) if collection else self.archive_path
        data_dir = os.path.join(root, "data")
        return data_dir if os.path.isdir(data_dir) else root

    def _archive_path_for(self, product: ProductItem) -> Optional[str]:
        """Locate *product*'s data file, scoped to its collection's data subtree
        rather than the whole archive. Matching (bare id, id + a container suffix
        from :py:data:`PRODUCT_NAME_SUFFIXES`, ``.SAFE`` / ``.SEN3`` directories) is
        the base's
        :py:meth:`~scrappi.api.offlinebase.OfflineArchiveHandler._resolve_in_index`.

        TODO: if a real archive's id <-> on-disk-name mapping needs more than the
        suffix logic, resolve via the STAC item's ``data`` asset href instead.
        """
        collection = getattr(product, "collection", None)
        return self._resolve_in_index(product, self._index_of(self._data_dir(collection)))

    # download_product is inherited from OfflineArchiveHandler: it calls
    # _archive_path_for (above), re-pins product.filesystem via _flat_filesystem
    # (carrying ARCHIVE_READ_ONLY), and returns the path -- no network.

    # ------------------------------------------------------------------ harvest
    def _strip_container_suffix(self, name: str) -> str:
        """*name* with a single trailing :py:data:`PRODUCT_NAME_SUFFIXES` entry
        removed (longest match first, so ``.tar.gz`` wins over ``.tar``) -- a STAC
        item's ``id`` is the bare product name; the on-disk file/directory may
        carry one of these."""
        for suffix in sorted(self.PRODUCT_NAME_SUFFIXES, key=len, reverse=True):
            if name.endswith(suffix):
                return name[: -len(suffix)]
        return name

    def _fast_metadata_from_name(self, path: str, collection: str) -> Optional[Dict[str, Any]]:
        """Hook: a mission-specific, filename-only metadata parse (no file read).
        ``None`` (the default -- no mission is wired up here) falls through to
        :py:meth:`_metadata_via_eoio`. Override for a mission whose filename plus
        e.g. a static tile grid fully determines footprint + time; return a dict
        shaped like :py:meth:`_metadata_via_eoio`'s (``geometry``, ``start_time``,
        optionally ``stop_time`` / ``platform`` / ``cloud_fraction``)."""
        return None

    def _metadata_via_eoio(self, path: str) -> Optional[Dict[str, Any]]:
        """Extract footprint/time/platform/cloud-cover by reading *path*'s own
        manifest via eoio -- no raster access, but a real per-product cost, which
        is why only :py:meth:`harvest` calls this, never :py:meth:`perform_query`.

        :raises ImportError: eoio isn't installed -- ``pip install
            'scrappi[satellite_offline]'``.
        :returns: ``None`` (with a warning) if eoio has no reader for *path*, or
            the reader's metadata is missing a footprint/time.
        """
        try:
            from eoio.readers.factory import ReaderFactory
        except ImportError as exc:
            raise ImportError(
                "eoio is required to harvest metadata for products whose footprint/time "
                "can't be determined from the filename alone. Install it with: "
                "pip install 'scrappi[satellite_offline]'"
            ) from exc

        try:
            reader_cls = ReaderFactory.get_reader(path)
            reader = reader_cls(path)
            basic = reader.mtd.basic_metadata
        except Exception as exc:
            warnings.warn(f"{type(self).__name__}: eoio could not read metadata for {path!r}: {exc}")
            return None

        footprint = basic.get("footprint") or {}
        geometry = footprint.get("geometry") if isinstance(footprint, dict) else None
        start_time = basic.get("product_datetime")
        if geometry is None or not start_time:
            warnings.warn(f"{type(self).__name__}: eoio metadata for {path!r} has no geometry/datetime -- skipped")
            return None

        try:
            product_md = reader.mtd.product_metadata
        except Exception:
            product_md = {}

        return {
            "geometry": geometry,
            "start_time": start_time,
            "stop_time": product_md.get("sensing_time") or start_time,
            "platform": basic.get("platform"),
            "cloud_fraction": product_md.get("cloudy_pixel_percentage"),
        }

    def _build_product_item(self, path: str, collection: str) -> Optional[ProductItem]:
        """A :py:class:`~scrappi.product.ProductItem` for the file/directory at
        *path*, from :py:meth:`_fast_metadata_from_name` if it has an answer, else
        :py:meth:`_metadata_via_eoio`. ``None`` if neither does."""
        meta = self._fast_metadata_from_name(path, collection) or self._metadata_via_eoio(path)
        if not meta:
            return None

        pid = self._strip_container_suffix(os.path.basename(path))

        try:
            platform = self.parse_platform_from_name(pid)
        except NotImplementedError:
            platform = meta.get("platform") or ""
        try:
            constellation = self.parse_constellation_from_name(pid)
        except NotImplementedError:
            constellation = ""

        cloud_fraction = meta.get("cloud_fraction")
        if cloud_fraction == -1:
            # USGS/Landsat-style "not calculated" sentinel -- see EODAGCallHandler.
            # perform_query's identical normalisation; cloud cover can't be
            # negative, so a literal -1 would look like the clearest scene there is.
            cloud_fraction = math.nan

        return ProductItem(
            constellation=constellation,
            platform=platform,
            collection=collection,
            id=pid,
            geometry=meta["geometry"],
            start_time=meta["start_time"],
            stop_time=meta.get("stop_time") or meta["start_time"],
            cloud_fraction=cloud_fraction,
            url="",
            quicklook="",
            context=self.context,
        )

    def _write_stac_item(self, product: ProductItem, item_path: str, source_path: str) -> None:
        """Write *product* as a STAC item json at *item_path*. The item is built
        via a flat filesystem pinned to *source_path*'s own directory (so its asset
        href resolves correctly there), independent of where *item_path* itself
        sits -- :py:meth:`_pin_filesystem` re-locates the data file by id at query
        time regardless, so that href is informational, not load-bearing."""
        fs = self._flat_filesystem(os.path.dirname(source_path), read_only=True)
        item = product.to_new_stac_item(fs)
        os.makedirs(os.path.dirname(item_path), exist_ok=True)
        item.save_object(dest_href=item_path)

    def _ensure_collection_json(self, collection: str, stac_root: str, sample_product: ProductItem) -> None:
        """Write ``<stac_root>/<collection>/collection.json`` if it doesn't exist
        yet, so :py:meth:`list_collections` / :py:meth:`_collection_root` can
        discover this collection. Extent is seeded from *sample_product* (any one
        harvested product) -- the same "first product sets the extent" pattern
        :py:meth:`~scrappi.product.ProductItem.register_in_filesystem_catalog`
        uses; not kept precisely up to date on every later harvest, since nothing
        in this handler reads a collection's extent.

        Doesn't build root ``catalog.json`` or link collection/item/catalog
        together -- :py:meth:`perform_query` discovers purely by filesystem glob
        and walk, never by following STAC links, so that linkage isn't needed for
        this handler to work; a TODO for full STAC-spec compliance / other tools.
        """
        path = os.path.join(stac_root, collection, "collection.json")
        if os.path.exists(path):
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        coll = pystac.Collection(
            id=collection,
            description=f"Collection {collection}",
            extent=pystac.Extent(
                spatial=pystac.SpatialExtent([list(sample_product.geometry.bounds)]),
                temporal=pystac.TemporalExtent([[sample_product.start_time, sample_product.stop_time]]),
            ),
            license="other",
        )
        coll.save_object(dest_href=path)

    def harvest(self, collection: str, *, overwrite: bool = False) -> int:
        """Build (or extend) the STAC index :py:meth:`perform_query` reads, for
        *collection*'s data files that don't have a STAC item yet.

        A one-off (or periodically re-run) maintenance step -- **not** run
        automatically during :py:meth:`perform_query`, which only ever reads an
        already-built index; see the module docstring. May import ``eoio`` (lazily,
        only for a product :py:meth:`_fast_metadata_from_name` can't handle) --
        install with ``pip install 'scrappi[satellite_offline]'``.

        Deliberately bypasses :py:data:`~scrappi.api.offlinebase.OfflineArchiveHandler.ARCHIVE_READ_ONLY`:
        writing the STAC tree is this method's entire job, an explicit call the
        user makes to prepare an archive for querying -- unlike
        :py:meth:`perform_query`'s read-only default, which guards against
        *incidental* writes during ordinary querying (see the fix for
        ``ProductItem.register_in_filesystem_catalog`` writing into a read-only
        archive by accident).

        :param collection: the collection id to harvest. Required, not
            discovered: before any harvesting there is no STAC tree yet for
            :py:meth:`list_collections` to find one in, and a data directory's own
            name is not guaranteed to match a STAC collection id (see
            :py:meth:`_collection_root`'s docstring) -- so which collection a given
            data subtree represents is something only the caller can know.
        :param overwrite: re-harvest (and overwrite the STAC item for) a product
            that already has one.
        :return: number of STAC items written.
        """
        collection_root = self._collection_root(collection)
        data_dir = self._data_dir(collection)
        stac_root = os.path.join(collection_root, "stac")

        sample_product: Optional[ProductItem] = None
        n = 0
        for name, path in self._index_of(data_dir).items():
            pid = self._strip_container_suffix(name)
            item_path = os.path.join(stac_root, collection, "items", f"{pid}.json")
            if os.path.exists(item_path) and not overwrite:
                continue

            product = self._build_product_item(path, collection)
            if product is None:
                continue

            self._write_stac_item(product, item_path, path)
            sample_product = sample_product or product
            n += 1

        if sample_product is not None:
            self._ensure_collection_json(collection, stac_root, sample_product)
        if n:
            # this instance's cached discovery / archive-index walks are now stale
            self.clear_cache()
        return n
