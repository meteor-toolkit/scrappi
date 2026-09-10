"""Offline (archive-backed) handler for satellite scenes.

**Status: skeleton.** The structure, base-class wiring and query/download flow are
in place; the parts marked ``TODO`` below need decisions from a real archive
layout before this is production-ready. See
``docs/content/developer/api.rst`` and the design notes on the
``offline-satellite-archive`` branch.

What this is
------------
The satellite counterpart to
:py:class:`~scrappi.api.radcalnet_api_client.RadcalnetOfflineCallHandler` /
:py:class:`~scrappi.api.hypernets.HYPERNETSOfflineCallHandler`: it answers the
same ``perform_query`` / ``download_product`` interface as the online eodag
handler but reads scenes from a local directory tree the user already holds,
for use as a fallback in the candidate-API fan-out (registered after
``"eodag"`` in :py:mod:`scrappi.api.factory`).

Unlike the in-situ offline handlers, a satellite scene's footprint polygon,
acquisition times and cloud cover are **not** derivable from its filename or a
site registry -- they need a metadata record per product. This handler reads
that record from **scrappi's own STAC catalogue tree**.

The STAC-tree requirement
-------------------------
scrappi writes a STAC item (and collection/root catalogue) for every product it
downloads **when** ``context["fs"]["register_stac_items"]`` is true -- which is
the default (see ``scrappi/etc/defaults.yaml``). So an archive that scrappi
itself populated has, alongside the data tree::

    <root>/data/<constellation>/<platform>/<collection>/<yyyy>/<mm>/<dd>/<product>
    <root>/stac/<collection>/items/<yyyy>/<mm>/<dd>/<product>.json
    <root>/stac/<collection>/collection.json
    <root>/stac/catalog.json

This handler reads those ``*.json`` item files, rebuilds each into a
:py:class:`~scrappi.product.ProductItem` with
:py:func:`~scrappi.product.product_item_from_stac`, and applies the query
filters client-side with
:py:func:`~scrappi.api.offline_query.product_matches_query`.

An archive of **bare product files with no ``stac/`` tree is not served by this
handler** -- :py:meth:`perform_query` returns an empty set and warns. Options for
that case (not implemented here): point the online eodag handler at a local
STAC via its ``StaticStacSearch`` plugin, or add a filename-only degraded mode
(``_parse_product_name``) as a follow-up.
"""

from __future__ import annotations

import json
import os
import warnings
from typing import Any, List, Optional, Tuple

from scrappi.api.offlinebase import OfflineArchiveHandler
from scrappi.api.offline_query import product_matches_query, query_collections
from scrappi.product import ProductItem, ProductItemSet, product_item_from_stac

__author__ = ["Maddie Stedman <maddie.stedman@npl.co.uk>"]
__all__ = ["SatelliteOfflineCallHandler"]

#: names that are catalogue nodes, not product items, when walking the stac tree
_NON_ITEM_JSON = frozenset({"catalog.json", "collection.json"})


class SatelliteOfflineCallHandler(OfflineArchiveHandler):
    """Resolve satellite scenes from a local archive that carries scrappi's STAC tree.

    :param context: :py:class:`~scrappi.ScrappiContext`.
    :param archive_path: archive root. Falls back to
        ``context["api"]["offline_archive_path"]``, then
        :py:meth:`_default_archive_path` (unset by default -- there's no sensible
        NPL-wide default for "all satellite data").
    """

    name = "eodag_offline"

    #: read from context["api"]["offline_archive_path"] when archive_path isn't given
    ARCHIVE_PATH_CONTEXT_KEYS: Tuple[str, ...] = ("api", "offline_archive_path")

    #: extracted Sentinel scenes are whole-product directories
    INDEX_DIRECTORY_SUFFIXES: Tuple[str, ...] = (".SAFE", ".SEN3")

    def _default_archive_path(self) -> str:
        """No built-in default -- there's no sensible NPL-wide "all satellite data"
        location. Returns ``""`` (rather than raising like the base) so that an
        unconfigured handler is simply *inert* -- :py:meth:`list_collections`
        returns ``[]`` and :py:meth:`perform_query` returns an empty set -- instead
        of breaking every :py:func:`scrappi.get_api_name` call that probes it.
        Configure via ``archive_path=`` or ``context["api"]["offline_archive_path"]``.
        """
        return ""

    @property
    def _configured(self) -> bool:
        return bool(self.archive_path) and os.path.isdir(self.archive_path)

    # ------------------------------------------------------------------ roots
    def _collection_root(self, collection: str) -> str:
        """The directory to search for *collection*'s STAC items.

        Precedence:

        1. an explicit per-collection path in
           ``context["api"]["offline_archive_paths"][collection]`` (user override);
        2. ``<archive_path>/<collection>`` if that directory exists (the "one
           subdirectory per collection" convention);
        3. ``<archive_path>`` itself.

        Scoping the walk to one collection's subtree is what keeps a query off a
        multi-terabyte shared archive from walking the whole thing.
        """
        overrides: Any = {}
        try:
            overrides = self.context["api"].get("offline_archive_paths") or {}
        except Exception:
            overrides = {}
        if collection in overrides:
            return overrides[collection]

        per_collection = os.path.join(self.archive_path, collection)
        if os.path.isdir(per_collection):
            return per_collection
        return self.archive_path

    # ------------------------------------------------------------------ discovery
    def _stac_item_paths(self, root: str) -> List[str]:
        """Absolute paths of every STAC *item* JSON under *root* (excludes
        ``catalog.json`` / ``collection.json``). Uses the cached
        :py:meth:`~scrappi.api.offlinebase.OfflineArchiveHandler._index_of` walk."""
        return [
            path
            for name, path in self._index_of(root).items()
            if name.endswith(".json") and name not in _NON_ITEM_JSON
        ]

    def list_collections(self, fetch_update: Optional[bool] = False) -> List[str]:
        """Collection ids the archive holds -- read from every ``collection.json``
        under :py:attr:`archive_path`, falling back to top-level subdirectory names.

        :param fetch_update: unused; kept for interface compatibility.
        """
        if not self._configured:
            return []
        found: List[str] = []
        for name, path in self._index_of(self.archive_path).items():
            if name != "collection.json":
                continue
            try:
                found.append(json.loads(open(path).read())["id"])
            except Exception:
                continue
        if found:
            return sorted(set(found))

        # fallback: assume <archive_path>/<collection>/ layout
        if os.path.isdir(self.archive_path):
            return sorted(
                d for d in os.listdir(self.archive_path) if os.path.isdir(os.path.join(self.archive_path, d))
            )
        return []

    # ------------------------------------------------------------------ query
    def perform_query(self, query: dict) -> ProductItemSet:
        """Every archived scene whose STAC item satisfies *query*.

        :param query: same shape as :py:meth:`scrappi.api.eodag.EODAGCallHandler.perform_query`
            (``collection``/``collections``, ``geom``, ``start_time``, ``stop_time``,
            optional ``platform``); see :py:func:`~scrappi.api.offline_query.product_matches_query`.
        :returns: matching products (empty, with a warning, if the archive has no
            STAC tree for the requested collection).
        """
        query = dict(query)

        if not self._configured:
            warnings.warn(
                f"{type(self).__name__}: archive_path {self.archive_path!r} is not a directory "
                f"(set archive_path= or context['api']['offline_archive_path'])"
            )
            return ProductItemSet()

        collections = query_collections(query) or self.list_collections()
        if not collections:
            warnings.warn(
                f"{type(self).__name__}: no collection in the query and none discoverable "
                f"under {self.archive_path!r}"
            )
            return ProductItemSet()

        products: List[ProductItem] = []
        for collection in collections:
            root = self._collection_root(collection)
            item_paths = self._stac_item_paths(root)
            if not item_paths:
                warnings.warn(
                    f"{type(self).__name__}: no STAC items found for collection {collection!r} under "
                    f"{root!r}. This handler needs scrappi's stac/ tree (written on download when "
                    f"context['fs']['register_stac_items'] is true); a bare archive of product files "
                    f"is not supported."
                )
                continue

            for item_path in item_paths:
                product = self._product_from_item(item_path, collection)
                if product is None:
                    continue
                if product_matches_query(product, {**query, "collection": collection}):
                    products.append(product)

        return ProductItemSet(products)

    # ------------------------------------------------------------------ item -> product
    def _product_from_item(self, item_path: str, collection: str) -> Optional[ProductItem]:
        """Rebuild one :py:class:`~scrappi.product.ProductItem` from a STAC item
        JSON and pin its filesystem to wherever the data file actually is."""
        try:
            product = product_item_from_stac(item_path, self.context)
        except Exception as exc:  # a stray / malformed json shouldn't abort the query
            warnings.warn(f"{type(self).__name__}: could not read STAC item {item_path!r}: {exc}")
            return None

        if not product.collection:
            product.collection = collection

        # Pin the filesystem to the data file's own directory. The STAC item's
        # asset href may be logical (asset://...) or relative, so rather than
        # resolving it we locate the file by id in the archive (one cached walk).
        data_path = self._archive_path_for(product)
        if data_path is not None:
            product.filesystem = self._flat_filesystem(os.path.dirname(data_path), read_only=True)
        else:
            # data not (yet) in the archive -- keep a filesystem so to_stac_item()
            # etc. still work, pinned at the collection root.
            product.filesystem = self._flat_filesystem(self._collection_root(collection), read_only=True)
        product.api = self
        return product

    # ------------------------------------------------------------------ download
    def _archive_path_for(self, product: ProductItem) -> Optional[str]:
        """Locate *product*'s data file, scoped to its collection's subtree rather
        than the whole archive (the base walks all of ``archive_path``).

        Matching (bare id, id +/- a container suffix, stem match) and the
        ``.SAFE`` / ``.SEN3`` directory handling are the base's -- see
        :py:meth:`~scrappi.api.offlinebase.OfflineArchiveHandler._resolve_in_index`.
        ``download_product`` (inherited) then re-pins the filesystem and returns
        the path, no network.

        TODO: if a real archive's id <-> on-disk-name mapping needs more than the
        suffix logic, resolve via the STAC item's ``data`` asset href relative to
        ``<collection_root>`` instead.
        """
        collection = getattr(product, "collection", None)
        root = self._collection_root(collection) if collection else self.archive_path
        return self._resolve_in_index(product, self._index_of(root))
