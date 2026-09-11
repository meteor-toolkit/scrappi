"""Offline (archive-backed) handler for satellite scenes.

**Status: skeleton.** The structure, base-class wiring and query/download flow are
in place; the ``TODO``\\ s below need decisions from a real archive layout before
this is production-ready. See ``docs/content/developer/api.rst``.

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
record from **scrappi's own STAC catalogue tree**.

The STAC-tree requirement
-------------------------
scrappi writes a STAC item (and collection / root catalogue) for every product it
downloads **when** ``context["fs"]["register_stac_items"]`` is true -- the default
(see ``scrappi/etc/defaults.yaml``). So an archive scrappi itself populated has,
alongside the data tree::

    <root>/data/<constellation>/<platform>/<collection>/<yyyy>/<mm>/<dd>/<product>
    <root>/stac/<collection>/items/<yyyy>/<mm>/<dd>/<product>.json
    <root>/stac/<collection>/collection.json
    <root>/stac/catalog.json

This handler reads those item ``*.json`` files, rebuilds each into a
:py:class:`~scrappi.product.ProductItem` with
:py:func:`~scrappi.product.product_item_from_stac`, and filters them client-side
with a :py:class:`~scrappi.api.offline_query.CompiledQuery`.

An archive of **bare product files with no ``stac/`` tree is not served by this
handler** -- :py:meth:`perform_query` returns an empty set and warns. Options for
that case (not implemented): the online eodag handler's ``StaticStacSearch``
plugin, or a filename-only degraded mode.

Per-collection roots
--------------------
So a query doesn't walk a whole shared archive, each collection is searched under
its own subtree:

1. ``context["api"]["offline_archive_paths"][collection]`` -- explicit override;
2. ``<archive_path>/<collection>/`` if it holds a ``stac/`` dir;
3. ``<archive_path>`` itself.
"""

from __future__ import annotations

import glob
import json
import os
import warnings
from typing import Dict, List, Optional, Set, Tuple

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
        ``<archive_path>/<collection>`` convention if it holds a ``stac/`` dir
        (covers a collection not yet discovered, e.g. no ``collection.json`` written
        yet); else ``<archive_path>`` itself.
        """
        override = self._path_overrides().get(collection)
        if override:
            return override
        discovered = self._discover().get(collection)
        if discovered:
            return discovered
        per_collection = os.path.join(self.archive_path, collection)
        if os.path.isdir(os.path.join(per_collection, "stac")):
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
    def _archive_path_for(self, product: ProductItem) -> Optional[str]:
        """Locate *product*'s data file, scoped to its collection's data subtree
        (``<collection_root>/data`` if present, else ``<collection_root>``) rather
        than the whole archive. Matching (bare id, id + a container suffix from
        :py:data:`PRODUCT_NAME_SUFFIXES`, ``.SAFE`` / ``.SEN3`` directories) is the
        base's :py:meth:`~scrappi.api.offlinebase.OfflineArchiveHandler._resolve_in_index`.

        TODO: if a real archive's id <-> on-disk-name mapping needs more than the
        suffix logic, resolve via the STAC item's ``data`` asset href instead.
        """
        collection = getattr(product, "collection", None)
        root = self._collection_root(collection) if collection else self.archive_path
        data_dir = os.path.join(root, "data")
        search = data_dir if os.path.isdir(data_dir) else root
        return self._resolve_in_index(product, self._index_of(search))

    # download_product is inherited from OfflineArchiveHandler: it calls
    # _archive_path_for (above), re-pins product.filesystem via _flat_filesystem
    # (carrying ARCHIVE_READ_ONLY), and returns the path -- no network.
