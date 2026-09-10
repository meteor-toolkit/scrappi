"""Base class for API call handlers that resolve products from a local archive.

An *offline* handler exposes the same query/download interface as a network one
(:py:class:`~scrappi.api.base.BaseAPICallHandler`) but reads product files from a
directory tree the user already holds, rather than fetching them from a service.
This is orthogonal to what *kind* of product it serves: the same mechanics --
archive-path resolution, a flat per-product filesystem, re-locating a file by id
for a product rebuilt from a catalogue, a no-network ``download_product`` -- apply
whether the products are in-situ (RadCalNet, HYPERNETS) or satellite scenes.

:py:class:`OfflineArchiveHandler` captures those mechanics once. A concrete
handler subclasses it (via :py:class:`~scrappi.api.insitubase.InSituOfflineCallHandler`
for an in-situ one, or directly for a satellite one) and supplies only the
provider-specific parts: :py:meth:`perform_query`, :py:meth:`list_collections`,
:py:data:`ARCHIVE_PATH_CONTEXT_KEYS`, and (if there is one) a default archive path.
"""

from __future__ import annotations

import os
import warnings
from abc import abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union

from scrappi.api.base import BaseAPICallHandler
from scrappi.fs.stacfilesystem import STACFileSystem
from scrappi.product import ProductItem, ProductItemSet

__author__ = ["Maddie Stedman <maddie.stedman@npl.co.uk>"]
__all__ = ["OfflineArchiveHandler"]


class OfflineArchiveHandler(BaseAPICallHandler):
    """Abstract base for handlers that resolve products from a local archive.

    Subclasses must implement :py:meth:`perform_query` and
    :py:meth:`list_collections` (both abstract on
    :py:class:`~scrappi.api.base.BaseAPICallHandler`), and should:

    - set :py:data:`ARCHIVE_PATH_CONTEXT_KEYS` to the nested context keys the
      archive root is read from when it isn't passed to ``__init__`` explicitly
      (e.g. ``("RadCalNet", "offline_archive_path")``);
    - override :py:meth:`_default_archive_path` if there is a sensible fallback
      when neither the argument nor the context supplies one;
    - build each :py:class:`~scrappi.product.ProductItem` in :py:meth:`perform_query`
      with ``filesystem=self._flat_filesystem(<the file's own directory>)``;
    - set :py:data:`INDEX_DIRECTORY_SUFFIXES` if whole products are directories
      (``.SAFE`` / ``.SEN3``), so :py:meth:`_index_of` treats each as one entry;
    - use :py:meth:`_index_of` (rather than :py:attr:`_archive_index`) with a
      per-collection subdirectory if the archive is large enough that walking the
      whole thing per query is too slow -- see
      :py:class:`~scrappi.api.satellite_offline.SatelliteOfflineCallHandler`.

    :py:meth:`download_product` and :py:meth:`_archive_path_for` are then provided
    for free and need no per-provider code. An in-situ handler subclasses this via
    :py:class:`~scrappi.api.insitubase.InSituOfflineCallHandler`; a satellite one
    subclasses it directly (or via
    :py:class:`~scrappi.api.satellite_offline.SatelliteOfflineCallHandler`).
    """

    #: Nested context keys the archive root is read from when ``archive_path`` is
    #: not passed to ``__init__`` -- e.g. ``("RadCalNet", "offline_archive_path")``
    #: resolves ``context["RadCalNet"]["offline_archive_path"]``. Empty (the
    #: default) means "always use :py:meth:`_default_archive_path`".
    ARCHIVE_PATH_CONTEXT_KEYS: Tuple[str, ...] = ()

    #: Directory-name suffixes that are themselves whole products rather than
    #: folders of loose files -- e.g. ``(".SAFE", ".SEN3")`` for Sentinel scenes.
    #: When set, :py:meth:`_index_of` records the *directory* under one of these
    #: names as a single archive entry and does not descend into it (so a ``.SAFE``
    #: contributes one entry, not its thousands of granule files). In-situ handlers
    #: leave this empty and are unaffected.
    INDEX_DIRECTORY_SUFFIXES: Tuple[str, ...] = ()

    #: Suffixes an archived product's on-disk name may carry that its ``id`` does
    #: not (an id of ``S2A_...`` may sit on disk as ``S2A_....zip`` / ``.SAFE`` /
    #: ``.SAFE/``). :py:meth:`_archive_path_for` tries the bare id, then the id
    #: plus each of these, then a stem match. Mirrors the set
    #: :py:meth:`scrappi.fs.localfilesystem.LocalFileSystem.check_any_path_exists`
    #: probes.
    PRODUCT_NAME_SUFFIXES: Tuple[str, ...] = (
        ".zip",
        ".SAFE",
        ".SEN3",
        ".nc",
        ".tar",
        ".tar.gz",
        ".json",
    )

    def __init__(self, context: Any = None, *args: Any, archive_path: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(context, *args, **kwargs)
        self.archive_path: str = self._resolve_archive_path(archive_path)

    # ------------------------------------------------------------------ config
    def _resolve_archive_path(self, archive_path: Optional[str]) -> str:
        """The archive root: *archive_path* if given, else the value at
        :py:data:`ARCHIVE_PATH_CONTEXT_KEYS` in the context, else
        :py:meth:`_default_archive_path`."""
        if archive_path is not None:
            return archive_path
        node: Any = self.context if self.ARCHIVE_PATH_CONTEXT_KEYS else None
        for key in self.ARCHIVE_PATH_CONTEXT_KEYS:
            node = node.get(key) if (node is not None and hasattr(node, "get")) else None
        return node or self._default_archive_path()

    def _default_archive_path(self) -> str:
        """Fallback archive root when neither the constructor argument nor the
        context supplies one. Subclasses with a sensible default (e.g. a fixed
        location on shared infrastructure) override this; the base raises."""
        raise NotImplementedError(
            f"{type(self).__name__}: no archive_path given, none set at "
            f"context{list(self.ARCHIVE_PATH_CONTEXT_KEYS)}, and no _default_archive_path()."
        )

    # --------------------------------------------------------------- archive scan
    def _index_of(self, root: str) -> Dict[str, str]:
        """``name -> absolute path`` for every file under *root* (and every
        directory whose name ends with one of :py:data:`INDEX_DIRECTORY_SUFFIXES`),
        built once per *root* by a single :py:func:`os.walk` and cached on the
        instance.

        A handler instance is short-lived (one query or one download batch), and the
        archive doesn't change under it mid-batch, so caching is safe and turns an
        ``os.walk``-per-product (a real cost on a large networked archive) into one
        walk per root. If two entries share a name, the first found wins -- a
        subclass that cares about which (e.g. product versions) does its own
        selection in :py:meth:`perform_query`.

        :param root: directory to walk. :py:meth:`perform_query` on a satellite
            handler passes a per-collection subdirectory here rather than the whole
            archive; :py:attr:`_archive_index` passes :py:attr:`archive_path`.
        """
        cache: Dict[str, Dict[str, str]] = self.__dict__.setdefault("_index_cache", {})
        idx = cache.get(root)
        if idx is None:
            idx = {}
            if os.path.isdir(root):
                for dirpath, dirnames, filenames in os.walk(root):
                    if self.INDEX_DIRECTORY_SUFFIXES:
                        container = [d for d in dirnames if d.endswith(self.INDEX_DIRECTORY_SUFFIXES)]
                        for d in container:
                            idx.setdefault(d, os.path.join(dirpath, d))
                        # don't descend into a product directory's own contents
                        dirnames[:] = [d for d in dirnames if d not in container]
                    for filename in filenames:
                        idx.setdefault(filename, os.path.join(dirpath, filename))
            cache[root] = idx
        return idx

    @property
    def _archive_index(self) -> Dict[str, str]:
        """:py:meth:`_index_of` for the whole :py:attr:`archive_path`. Kept as the
        name in-situ handlers already use."""
        return self._index_of(self.archive_path)

    # -------------------------------------------------------------- filesystem
    def _flat_filesystem(self, dirpath: str, read_only: Optional[bool] = None) -> STACFileSystem:
        """A flat-layout :py:class:`~scrappi.fs.stacfilesystem.STACFileSystem` pinned
        to *dirpath* -- the directory an archived file actually sits in. Flat so the
        file resolves at ``<dirpath>/<id>`` regardless of how the archive is laid
        out, and so nothing is reorganised from product metadata (the file is
        already where it is). ``organise_data`` is scoped to this instance, never
        the shared context.

        :param read_only: passed straight through to
            :py:class:`~scrappi.fs.stacfilesystem.STACFileSystem`; ``None`` (default)
            leaves it at that class's own default. Pass ``True`` for an archive a
            handler should never write back to.
        """
        return STACFileSystem(path=dirpath, context=self.context, flat=True, read_only=read_only)

    def _archive_path_for(self, product: ProductItem) -> Optional[str]:
        """Absolute path of *product*'s file within :py:attr:`archive_path`, or
        ``None`` if it isn't there.

        :py:meth:`perform_query` attaches a correct per-file filesystem to every
        product it returns, but a product rebuilt from a STAC catalogue (eomatch's
        ``product_item_from_stac``) arrives with none, so :py:meth:`download_product`
        re-resolves it here rather than trusting ``product.filesystem``. Resolved via
        :py:meth:`_index_of` (one walk, cached).

        Matching is on the product name with any container suffix ignored on both
        sides: the bare ``id`` and ``id`` minus a known suffix are each tried
        exactly, then plus each of :py:data:`PRODUCT_NAME_SUFFIXES`, then against
        every index entry with its own suffix stripped. So an id of ``S2A_...``
        finds ``S2A_....zip`` / ``S2A_....SAFE``, and an id of ``S2A_....SAFE``
        finds a bare ``S2A_...`` or ``S2A_....zip``. Subclasses whose ids don't map
        onto on-disk names this way (or that want a collection-scoped search)
        override this.
        """
        return self._resolve_in_index(product, self._archive_index)

    def _resolve_in_index(self, product: ProductItem, index: Dict[str, str]) -> Optional[str]:
        """:py:meth:`_archive_path_for`'s name matching, against an arbitrary
        *index* (a satellite handler passes a collection-scoped one)."""
        target = getattr(product, "id", None)
        if not target:
            return None
        stem = self._strip_product_suffix(target)
        for candidate in (target, stem):
            if candidate in index:
                return index[candidate]
            for suffix in self.PRODUCT_NAME_SUFFIXES:
                if candidate + suffix in index:
                    return index[candidate + suffix]
        for name, path in index.items():
            if self._strip_product_suffix(name) == stem:
                return path
        return None

    @classmethod
    def _strip_product_suffix(cls, name: str) -> str:
        """*name* with a single trailing :py:data:`PRODUCT_NAME_SUFFIXES` entry
        removed (longest match first, so ``.tar.gz`` wins over ``.gz``)."""
        for suffix in sorted(cls.PRODUCT_NAME_SUFFIXES, key=len, reverse=True):
            if name.endswith(suffix):
                return name[: -len(suffix)]
        return name

    # ---------------------------------------------------------------- download
    def download_product(self, product: Union[str, ProductItem, ProductItemSet]) -> Optional[Union[list, str]]:
        """Resolve *product* to its on-disk path in the archive -- no network, no copy.

        "Download" is a misnomer for an offline handler: the file is already local.
        This locates it under :py:attr:`archive_path` (see :py:meth:`_archive_path_for`)
        and returns that path, repinning ``product.filesystem`` to the file's own
        directory so :py:meth:`~scrappi.product.ProductItem.get_path` and any STAC
        registration still work for a product rebuilt from a catalogue.

        :param product: a :py:class:`~scrappi.product.ProductItem` or
            :py:class:`~scrappi.product.ProductItemSet`. Anything else warns and
            returns ``None``, matching
            :py:meth:`~scrappi.api.base.BaseAPICallHandler.download_product`.
        :return: absolute path to the archived file (or list thereof), or ``None``.
        :raises FileNotFoundError: if the archive doesn't contain the file.
        """
        if isinstance(product, ProductItemSet):
            return [self.download_product(p) for p in product]  # type: ignore[misc]
        if not isinstance(product, ProductItem):
            warnings.warn(
                f"{type(self).__name__}.download_product: expected a ProductItem, got {type(product).__name__}"
            )
            return None

        src = self._archive_path_for(product)
        if src is None:
            raise FileNotFoundError(
                f"{product.id!r} not found under the {type(self).__name__} archive {self.archive_path!r}"
            )
        product.filesystem = self._flat_filesystem(os.path.dirname(src))
        return src

    # ------------------------------------------------------------ still abstract
    @abstractmethod
    def perform_query(self, query: dict) -> ProductItemSet:
        """Return every archived product matching *query* (see the online sibling
        handler for the query shape)."""

    @abstractmethod
    def list_collections(self, fetch_update: Optional[bool] = False) -> List[str]:
        """The collection ids this handler serves."""
