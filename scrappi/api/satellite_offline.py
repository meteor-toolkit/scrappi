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

Which entries of a data directory are products is not configured per collection either:
:py:meth:`harvest` asks eoio's reader factory (:py:meth:`_has_eoio_reader`), so a file or a
plain directory that eoio can read is a product -- a directory is one product, its contents
are not walked -- and anything else is ignored. Each item records the product's location
relative to the data directory (:py:data:`ARCHIVE_PATH_PROPERTY`), so a query resolves it
exactly instead of guessing an on-disk name from the id.

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

:py:meth:`harvest` looks for an existing STAC item **anywhere** under a
collection's ``stac/`` tree, not just the flat path it writes new items at, so
re-running it never duplicates an item an online download already wrote at its
own organised, dated path -- it's skipped (or overwritten in place with
``overwrite=True``) instead. A single product's metadata extraction failing (a
corrupt file, an unsupported format) is warned and skipped without aborting the
rest of the batch; a failure actually writing a STAC item is let to propagate,
since that's likely to recur for every remaining product too. Because
:py:meth:`harvest` and :py:meth:`perform_query` both cache archive discovery on
``self``, a handler instance that queried before an out-of-process
:py:meth:`harvest` run (or a *different* cached handler instance, e.g. one
:py:class:`~scrappi.interface.APICallHandlerFactory` reused) needs its own
:py:meth:`~scrappi.api.offlinebase.OfflineArchiveHandler.clear_cache` call to
see the newly-harvested collection.

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

#: STAC item property harvest records a product's location in: its path relative to the
#: collection's data directory (POSIX separators), whatever the product is -- a file, an
#: extracted directory with or without a ``.SAFE``-style suffix. Queries resolve a product by
#: this rather than by guessing an on-disk name from its id.
ARCHIVE_PATH_PROPERTY = "scrappi:archive_path"


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

    #: harvest() writes its own STAC tree into <collection_root>/stac -- the same
    #: root _data_dir searches when there's no separate data/ subdirectory. Without
    #: this, a re-harvest (or an ordinary query's _archive_path_for) would walk that
    #: output back in as if it were product data.
    INDEX_EXCLUDE_DIRNAMES: Tuple[str, ...] = ("stac",)

    #: a STAC item id is the product name without an extension; on disk the data
    #: may carry one of these (never ``.json`` -- that's the item sidecar).
    PRODUCT_NAME_SUFFIXES: Tuple[str, ...] = (".SAFE", ".SEN3", ".zip", ".nc", ".tar.gz", ".tar", ".tif")

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
        self.__dict__.pop("_recorded_cache", None)
        self.__dict__.pop("_recorded_scanned", None)

    @property
    def _configured(self) -> bool:
        """``True`` if there's anywhere to look: either the base archive root, or --
        even with no base root set at all -- at least one per-collection
        ``offline_archive_paths`` override (a documented, standalone-valid config; see
        :py:meth:`_collection_root`'s precedence docstring). :py:meth:`_discover`
        gates its whole scan (and so :py:meth:`list_collections`) on this, so an
        override-only config that fails this check silently looks collection-less to
        callers like :py:func:`scrappi.interface.get_api_name` -- which only honours
        ``preferred_api`` for a collection actually in ``list_collections()`` -- even
        though :py:meth:`_collection_root`/:py:meth:`harvest` themselves already
        resolve that override just fine."""
        if self.archive_path and os.path.isdir(self.archive_path):
            return True
        return any(os.path.isdir(p) for p in self._path_overrides().values())

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
                # remembered even when empty (an online download's item), so that isn't rescanned
                self.__dict__.setdefault("_recorded_cache", {}).setdefault(product.collection, {})[product.id] = (
                    self._read_recorded(item_path) or ""
                )
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
    def _data_dir(self, collection: Optional[str], *, root: Optional[str] = None) -> str:
        """*collection*'s data subtree: ``<collection_root>/data`` if that exists,
        else ``<collection_root>`` itself (which -- see :py:data:`INDEX_EXCLUDE_DIRNAMES`
        -- excludes this handler's own ``stac/`` output from any walk of it, so a
        collection with no separate ``data/`` folder is still searched safely).
        Shared by :py:meth:`_archive_path_for` (locating an already-indexed product)
        and :py:meth:`harvest` (finding product files with no STAC item yet) -- the
        same directory, for the same reason: it's where the actual files are,
        regardless of whether a STAC tree has been built for them.

        :param root: the collection's already-resolved root, if the caller has one
            (:py:meth:`harvest` does) -- avoids a redundant
            :py:meth:`_collection_root` call. Resolved from *collection* if omitted.
        """
        if root is None:
            root = self._collection_root(collection) if collection else self.archive_path
        data_dir = os.path.join(root, "data")
        return data_dir if os.path.isdir(data_dir) else root

    def _read_recorded(self, item_path: str) -> Optional[str]:
        """The :py:data:`ARCHIVE_PATH_PROPERTY` in the STAC item json at *item_path*, if any."""
        try:
            with open(item_path) as f:
                relative = (json.load(f).get("properties") or {}).get(ARCHIVE_PATH_PROPERTY)
        except (OSError, ValueError):
            return None
        return str(relative) if relative else None

    def _recorded_relpath(self, collection: str, pid: str) -> Optional[str]:
        """Where :py:meth:`harvest` recorded product *pid* of *collection*, relative to the data
        directory. Read from the item json under the collection's ``stac/`` tree -- not from the
        :py:class:`ProductItem`, which may have been rebuilt from another catalogue (eomatch's)
        and carry none of it. :py:meth:`perform_query` fills the cache for the products it returns;
        otherwise one bounded walk of the collection's items fills it for all of them. Cached (see
        :py:meth:`clear_cache`)."""
        cache: Dict[str, Dict[str, str]] = self.__dict__.setdefault("_recorded_cache", {})
        scanned: Set[str] = self.__dict__.setdefault("_recorded_scanned", set())
        known = cache.setdefault(collection, {})
        if pid not in known and collection not in scanned:
            stac_dir = os.path.join(self._collection_root(collection), "stac", collection)
            for item_path in self._stac_item_paths(stac_dir):
                relative = self._read_recorded(item_path)
                if relative:
                    known[os.path.basename(item_path)[: -len(".json")]] = relative
            scanned.add(collection)
        return known.get(pid) or None

    def _recorded_path(self, product: ProductItem, data_dir: str) -> Optional[str]:
        """The location :py:meth:`harvest` recorded for *product* (see :py:meth:`_recorded_relpath`),
        if there is one, it stays inside *data_dir* and it still exists; else ``None``."""
        relative = self._recorded_relpath(getattr(product, "collection", None) or "", product.id)
        if not relative:
            return None
        path = os.path.normpath(os.path.join(data_dir, *relative.split("/")))
        inside = os.path.commonpath([os.path.abspath(path), os.path.abspath(data_dir)]) == os.path.abspath(data_dir)
        return path if inside and os.path.exists(path) else None

    def _archive_path_for(self, product: ProductItem) -> Optional[str]:
        """Locate *product*'s data file or directory, scoped to its collection's data
        subtree rather than the whole archive.

        First the location :py:meth:`harvest` recorded in the product's STAC item
        (:py:data:`ARCHIVE_PATH_PROPERTY`) -- exact for any product layout, and no walk
        of the archive. Items without it (written by an online download, or by an older
        harvest) fall back to name matching: bare id, id + a container suffix from
        :py:data:`PRODUCT_NAME_SUFFIXES`, ``.SAFE`` / ``.SEN3`` directories
        (the base's
        :py:meth:`~scrappi.api.offlinebase.OfflineArchiveHandler._resolve_in_index`).
        """
        collection = getattr(product, "collection", None)
        data_dir = self._data_dir(collection)
        recorded = self._recorded_path(product, data_dir)
        if recorded is not None:
            return recorded
        return self._resolve_in_index(product, self._index_of(data_dir))

    # download_product is inherited from OfflineArchiveHandler: it calls
    # _archive_path_for (above), re-pins product.filesystem via _flat_filesystem
    # (carrying ARCHIVE_READ_ONLY), and returns the path -- no network.

    # ------------------------------------------------------------------ harvest
    def _has_eoio_reader(self, name: str) -> bool:
        """Whether eoio has a reader for a product called *name* -- the single source of truth for
        which products exist, so a new mission needs no edit here once eoio can read it. Decided
        from the name alone (eoio's reader factory), without opening anything.

        :raises ImportError: eoio isn't installed -- ``pip install 'scrappi[satellite_offline]'``.
        """
        try:
            from eoio.readers.factory import ReaderFactory
        except ImportError as exc:
            raise ImportError(
                "eoio is required to harvest an archive: it decides which files and directories are "
                "products. Install it with: pip install 'scrappi[satellite_offline]'"
            ) from exc
        try:
            ReaderFactory.get_reader(name)
        except ValueError:  # the factory's "no known product format"
            return False
        except Exception as exc:  # a reader that cannot be imported; don't let it abort the batch
            warnings.warn(f"{type(self).__name__}: eoio reader lookup for {name!r} failed: {exc}")
            return False
        return True

    def _is_product(self, name: str, is_dir: bool) -> bool:
        """Whether the on-disk entry *name* is a product :py:meth:`harvest` should build a STAC
        item for: a ``.SAFE``-style container directory (no eoio needed to say so), or anything
        eoio has a reader for -- see :py:meth:`_has_eoio_reader`."""
        if is_dir and name.endswith(self.INDEX_DIRECTORY_SUFFIXES):
            return True
        return self._has_eoio_reader(name)

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
            import eoio
        except ImportError as exc:
            raise ImportError(
                "eoio is required to harvest metadata for products whose footprint/time "
                "can't be determined from the filename alone. Install it with: "
                "pip install 'scrappi[satellite_offline]'"
            ) from exc

        try:
            # eoio.read is the one common entry point every reader is meant to be
            # used through -- it already handles archive extraction (and cleanup)
            # internally, so no setup_file/extraction handling belongs here at all.
            # vars_sel turns off every raster/mask/aux read (this method never
            # touches product data, just its manifest -- see the docstring above),
            # and metadata_level=True is what makes a reader actually attach
            # metadata to the returned Dataset's .attrs (PRODUCT_NAME_SUFFIXES lets
            # an archive keep a collection's products zipped -- e.g. THEOS, never
            # pre-extracted -- which is exactly the case eoio.read's own extraction
            # handles transparently).
            ds = eoio.read(
                path,
                vars_sel={"meas": None, "mask": None, "aux": None},
                read_params={"metadata_level": True},
            )
            basic = ds.attrs
        except Exception as exc:
            warnings.warn(f"{type(self).__name__}: eoio could not read metadata for {path!r}: {exc}")
            return None

        footprint = basic.get("footprint") or {}
        geometry = footprint.get("geometry") if isinstance(footprint, dict) else None
        start_time = basic.get("product_datetime")
        if geometry is None or not start_time:
            warnings.warn(f"{type(self).__name__}: eoio metadata for {path!r} has no geometry/datetime -- skipped")
            return None

        product_md = basic.get("product_metadata") or {}
        # S2 reports cloudy_pixel_percentage; Planet (and other readers) cloud_area_fraction
        cloud_fraction = product_md.get("cloudy_pixel_percentage")
        if cloud_fraction is None:
            cloud_fraction = product_md.get("cloud_area_fraction")

        return {
            "geometry": geometry,
            "start_time": start_time,
            "stop_time": product_md.get("sensing_time") or start_time,
            "platform": basic.get("platform"),
            "constellation": basic.get("constellation"),
            "cloud_fraction": cloud_fraction,
        }

    @staticmethod
    def _valid_meta(meta: Optional[Dict[str, Any]]) -> bool:
        """Whether *meta* actually has the two fields a
        :py:class:`~scrappi.product.ProductItem` can't do without -- ``geometry``
        and ``start_time``. Applied to *both* metadata sources so an incomplete
        :py:meth:`_fast_metadata_from_name` override (a non-empty dict missing
        ``start_time``, say) is treated the same as incomplete eoio metadata:
        rejected, rather than reaching ``meta["start_time"]`` in
        :py:meth:`_build_product_item` and raising ``KeyError``."""
        return bool(meta) and meta.get("geometry") is not None and bool(meta.get("start_time"))

    def _build_product_item(self, path: str, pid: str, collection: str) -> Optional[ProductItem]:
        """A :py:class:`~scrappi.product.ProductItem` for the file/directory at
        *path* (with id *pid* -- :py:meth:`harvest` already has it, having derived
        it from the same on-disk name this method would otherwise recompute), from
        :py:meth:`_fast_metadata_from_name` if it has a complete answer, else
        :py:meth:`_metadata_via_eoio`. ``None`` if neither does.
        """
        meta = self._fast_metadata_from_name(path, collection)
        if not self._valid_meta(meta):
            meta = self._metadata_via_eoio(path)
        if not self._valid_meta(meta):
            return None

        try:
            platform = self.parse_platform_from_name(pid)
        except NotImplementedError:
            platform = meta.get("platform") or ""
        try:
            constellation = self.parse_constellation_from_name(pid)
        except NotImplementedError:
            constellation = meta.get("constellation") or ""

        return ProductItem(
            constellation=constellation,
            platform=platform,
            collection=collection,
            id=pid,
            geometry=meta["geometry"],
            start_time=meta["start_time"],
            stop_time=meta.get("stop_time") or meta["start_time"],
            cloud_fraction=self.normalize_cloud_fraction(meta.get("cloud_fraction")),
            url="",
            quicklook="",
            context=self.context,
        )

    def _write_stac_item(self, product: ProductItem, item_path: str, source_path: str, data_dir: str) -> None:
        """Write *product* as a STAC item json at *item_path*. The item is built
        via a flat filesystem pinned to *source_path*'s own directory (so its asset
        href resolves correctly there), independent of where *item_path* itself
        sits -- :py:meth:`_pin_filesystem` re-locates the data file by id at query
        time regardless, so that href is informational, not load-bearing. What a query
        does rely on is the :py:data:`ARCHIVE_PATH_PROPERTY` recorded here, relative to
        *data_dir*."""
        fs = self._flat_filesystem(os.path.dirname(source_path), read_only=True)
        item = product.to_new_stac_item(fs)
        item.properties[ARCHIVE_PATH_PROPERTY] = os.path.relpath(source_path, data_dir).replace(os.sep, "/")
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
        # matches ProductItem.register_in_filesystem_catalog's own collection.json,
        # so a harvested collection isn't missing fields an online-downloaded one has
        coll.extra_fields["constellation"] = sample_product.constellation
        coll.extra_fields["platform"] = sample_product.platform
        coll.save_object(dest_href=path)

    def harvest(self, collection: str, *, overwrite: bool = False) -> int:
        """Build (or extend) the STAC index :py:meth:`perform_query` reads, for
        *collection*'s data files that don't have a STAC item yet.

        A one-off (or periodically re-run) maintenance step -- **not** run
        automatically during :py:meth:`perform_query`, which only ever reads an
        already-built index; see the module docstring. Imports ``eoio`` lazily, to
        recognise which entries are products and (unless
        :py:meth:`_fast_metadata_from_name` can answer) to read their metadata --
        install with ``pip install 'scrappi[satellite_offline]'``. Re-harvesting an
        archive whose products all have items already does not need it.

        Deliberately bypasses :py:data:`~scrappi.api.offlinebase.OfflineArchiveHandler.ARCHIVE_READ_ONLY`:
        writing the STAC tree is this method's entire job, an explicit call the
        user makes to prepare an archive for querying -- unlike
        :py:meth:`perform_query`'s read-only default, which guards against
        *incidental* writes during ordinary querying (see the fix for
        ``ProductItem.register_in_filesystem_catalog`` writing into a read-only
        archive by accident).

        A per-product metadata-extraction failure (a corrupt file, an unsupported
        format) is warned and skipped, same as :py:meth:`_load_item` does for a
        malformed STAC item at query time -- one bad product doesn't abort the
        whole run. A failure actually *writing* the STAC item (permissions, a full
        disk) is not caught: it's likely to recur for every remaining product too,
        so it's let to propagate immediately rather than retried uselessly once per
        product. Either way, whatever succeeded before the failure is still
        committed (``collection.json`` written, caches cleared) rather than lost.

        If the same product already has a STAC item **anywhere** under
        ``<collection_root>/stac/<collection>/`` -- including one an online
        download wrote at its own organised, dated path, not just the flat path
        this method writes new items at -- it's treated as already harvested
        (skipped, or overwritten in place with ``overwrite=True``) rather than
        harvested again at a second, duplicate location.

        Only run against this handler's own instance cache
        (:py:meth:`clear_cache`) -- if a *different*, already-constructed
        ``SatelliteOfflineCallHandler`` (e.g. one cached by
        :py:class:`~scrappi.api.factory.APICallHandlerFactory` and reused by
        :py:mod:`scrappi.interface`'s candidate fan-out, its default) queries the
        same archive afterwards, call ``clear_cache()`` on *that* instance too (or
        pass ``use_cache=False`` to ``get_api_call_handler``) so it notices the
        newly-harvested collection.

        :param collection: the collection id to harvest. Required, not
            discovered: before any harvesting there is no STAC tree yet for
            :py:meth:`list_collections` to find one in, and a data directory's own
            name is not guaranteed to match a STAC collection id (see
            :py:meth:`_collection_root`'s docstring) -- so which collection a given
            data subtree represents is something only the caller can know.
        :param overwrite: re-harvest (and overwrite the STAC item for) a product
            that already has one.
        :return: number of STAC items written.
        :raises ValueError: *collection* is empty/``None``.
        """
        if not collection:
            raise ValueError(f"{type(self).__name__}.harvest: collection is required, got {collection!r}")

        collection_root = self._collection_root(collection)
        data_dir = self._data_dir(collection, root=collection_root)
        stac_root = os.path.join(collection_root, "stac")

        # id -> path of every STAC item *this collection* already has, wherever it
        # sits within stac_root/<collection>/ (flat, or an online download's
        # organised/dated layout) -- one bounded walk, reused as both the "already
        # harvested" check and, for overwrite, where to write back to (never
        # creating a second, duplicate item for an id that already has one
        # somewhere else in the tree). Scoped to this collection's own subtree, not
        # all of stac_root, since collection_root -- and so stac_root -- may be
        # shared with other collections (see _collection_root's docstring).
        existing_items = {
            os.path.basename(p)[: -len(".json")]: p for p in self._stac_item_paths(os.path.join(stac_root, collection))
        }

        sample_product: Optional[ProductItem] = None
        n = 0  # items written
        found = 0  # products recognised, whether or not they needed an item
        seen: Set[str] = set()
        eoio_missing: Optional[ImportError] = None

        def handle(name: str, path: str, is_dir: bool) -> bool:
            """Harvest the entry *path* if it is a product. Returns ``False`` only when the
            walk should look inside it instead: a directory that is not a product, or whose
            metadata could not be read (a directory name can match a reader's pattern by
            accident)."""
            nonlocal sample_product, n, found, eoio_missing
            pid = self._strip_container_suffix(name)
            if pid in seen:
                return True  # same product twice in the archive -- the first one wins
            existing_item_path = existing_items.get(pid)
            if existing_item_path is not None and not overwrite:
                seen.add(pid)
                found += 1
                return True
            try:
                is_product = self._is_product(name, is_dir)
            except ImportError as exc:  # can't tell what is a product; reported once the walk is done
                eoio_missing = exc
                return False
            if not is_product:
                return False
            seen.add(pid)
            found += 1
            # a .SAFE-style container is opaque; any other directory is searched if it yields nothing
            descend = is_dir and not name.endswith(self.INDEX_DIRECTORY_SUFFIXES)

            try:
                product = self._build_product_item(path, pid, collection)
            except Exception as exc:
                warnings.warn(f"{type(self).__name__}.harvest: could not extract metadata for {path!r}: {exc}")
                return not descend
            if product is None:
                return not descend

            item_path = existing_item_path or os.path.join(stac_root, collection, "items", f"{pid}.json")
            self._write_stac_item(product, item_path, path, data_dir)  # not caught -- see docstring
            sample_product = sample_product or product
            n += 1
            return True

        try:
            pending = [data_dir]
            while pending:
                directory = pending.pop(0)
                try:
                    entries = sorted(os.scandir(directory), key=lambda e: e.name)
                except OSError:
                    continue
                for entry in entries:
                    is_dir = entry.is_dir(follow_symlinks=False)
                    if is_dir and entry.name in self.INDEX_EXCLUDE_DIRNAMES:
                        continue
                    if not (is_dir or entry.is_file()):
                        continue
                    if not handle(entry.name, entry.path, is_dir) and is_dir:
                        pending.append(entry.path)
            if eoio_missing is not None:
                if not found:
                    raise eoio_missing
                warnings.warn(
                    f"{type(self).__name__}.harvest: eoio is not installed, so products without a STAC item "
                    f"yet could not be recognised under {data_dir!r} (already-harvested ones are unaffected)"
                )
            elif not found:
                warnings.warn(
                    f"{type(self).__name__}.harvest: no product eoio can read found under {data_dir!r} "
                    f"for collection {collection!r} -- nothing to harvest"
                )
        finally:
            if sample_product is not None:
                self._ensure_collection_json(collection, stac_root, sample_product)
            # this instance's cached discovery / archive-index walks are now stale
            # regardless of n (even a zero-new-items run leaves data_dir's listing
            # cached, which would otherwise hide a file that arrives before the
            # next harvest() call) or of a mid-run failure (whatever did succeed
            # before it shouldn't be hidden by a stale cache either)
            self.clear_cache()

        return n
