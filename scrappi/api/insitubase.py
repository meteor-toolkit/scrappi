"""Base classes for in-situ (ground) API call handlers.

Defines shared abstractions for in-situ data providers (for example
RadCalNet or HYPERNETS). These base classes provide ROI management and
common download helpers used by concrete in-situ handlers.
"""

import warnings
from abc import abstractmethod
from typing import Optional, Union, List, Any

from scrappi.api.base import BaseAPICallHandler
from scrappi.api.offlinebase import OfflineArchiveHandler
from scrappi.product import ProductItem, ProductItemSet
from scrappi.utils.utils import convert_geom_shapely, convert_geom_and_check, generate_bounding_lat_lon
from scrappi.fs.base import BaseFileSystem
from processor_tools import Context

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
]
__all__ = ["InSituOfflineCallHandler"]


class InSituCallHandler(BaseAPICallHandler):
    """Abstract base for in-situ (ground) data API handlers.

    Subclasses should provide a mapping of site identifiers to region-of-interest
    geometries (`roi_dict`) and implement `list_collections`, `perform_query`
    and `download_file`.

    :param roi_dict: mapping of site -> geometry used to resolve site extents
    """

    name: str

    def __init__(self, context: Optional[Union[str, List, Context]] = None, roi_dict: Optional[dict] = None):
        super().__init__(context)
        self.roi_dict: dict = roi_dict if roi_dict is not None else {}
        self.sites = list(self.roi_dict.keys())

    def _roi_or_raise(self, site: str):
        """*site*'s raw ROI geometry from :py:attr:`roi_dict`, or a ``KeyError`` that
        actually says what's wrong (the bare ``roi_dict[site]`` lookup just raised
        ``KeyError: '<site>'``, which gives no hint that the fix is a config entry)."""
        try:
            return self.roi_dict[site]
        except KeyError:
            raise KeyError(
                f"in-situ site {site!r} is not registered with {type(self).__name__} -- "
                f"known sites: {sorted(self.roi_dict)}. If this is a RadCalNet site that "
                f"isn't on the built-in list, add its latitude/longitude/default_roi under "
                f"context['RadCalNet']['site_definitions']."
            ) from None

    def get_roi(self, site: str):
        return convert_geom_and_check(self._roi_or_raise(site))

    def set_roi(self, site: str, geom: Any):
        self.roi_dict[site] = geom

    def set_roi_bounding_box(
        self,
        site: str,
        lat: float,
        lon: float,
        distance: float,
        crs: Optional[str] = None,
    ):
        """Set *site*'s ROI to a square box of *distance* metres either side of (*lat*, *lon*).

        :param site: site identifier to set the ROI for.
        :param lat: centre latitude of the box.
        :param lon: centre longitude of the box.
        :param distance: distance in metres from the centre to each side of the box.
        :param crs: optional projected CRS to buffer in; defaults to a local
            Azimuthal Equidistant projection centred on the point -- see
            :py:func:`~scrappi.utils.utils.generate_bounding_lat_lon` for why.
        """
        self.roi_dict[site] = generate_bounding_lat_lon(lat, lon, distance, crs=crs)

    @abstractmethod
    def list_collections(self, fetch_update: Optional[bool] = False):
        """
        Function to extract collection identifiers

        :param fetch_update: set to True to fetch online collection names instead of offline version.
        :return: list of collection identifiers
        """
        pass

    @abstractmethod
    def perform_query(self, query: dict) -> ProductItemSet:
        """
        Return catalogue product objects that satisfy query

        :param query: catalogue query
        :returns: product urls satisfying query
        """
        pass

    @abstractmethod
    def download_file(
        self,
        prod: Union[str, ProductItem],
        dest: Optional[Union[str, BaseFileSystem]] = None,
    ) -> Optional[Union[list, str]]:
        """
        Download the file at URL into dest using class credentials for basic auth
        :param prod: ProductItem
        :param dest: destination folder for downloaded file or filesystem
        """
        pass

    def download_product(self, product: Union[str, ProductItem, ProductItemSet]) -> Optional[Union[list, str]]:
        """
        Download catalogue product(s) at defined URL to local path

        :param product: product object
        :param fs: file system to use when writing the data. Alternatively, an existing product path can be provided as a string. If nothing is provided, it defaults to the path of scrappi/examples/downloaded_data
        :param organise_data: When a path is provided as a string (or when using default) instead of a filesystem, the organise_data boolean decides whether the data is organised by collection/year/month/day or not. Defaults to True.
        :return: path (or list of paths) to downloaded product(s)
        """
        if isinstance(product, ProductItemSet):  # recursion
            return [self.download_product(prod) for prod in product]

        elif product is None:
            warnings.warn("no product was provided to download")
            return None

        elif isinstance(product, ProductItem):
            if product.filesystem is None:
                product.set_fs(product.filesystem_init, context=product.context)     
            path, exists = product.filesystem.return_path(product, check_exists=True)

            if exists:
                print(f"{path} exists")
                return path

            else:
                print(f"{product.id} needs downloading")
                return self.download_file(product, path)

        return None


class InSituOfflineCallHandler(OfflineArchiveHandler, InSituCallHandler):
    """Base for in-situ API handlers that resolve products from a local archive.

    Combines :py:class:`~scrappi.api.offlinebase.OfflineArchiveHandler` (archive-path
    resolution, a flat per-product filesystem, a no-network ``download_product`` that
    re-locates a file by id) with :py:class:`InSituCallHandler` (the site -> ROI
    machinery). Concrete handlers (RadCalNet, HYPERNETS) implement only
    :py:meth:`perform_query`, :py:meth:`list_collections`, and their own filename
    grammar; see :py:class:`~scrappi.api.offlinebase.OfflineArchiveHandler` for what
    else to set. A satellite offline handler subclasses ``OfflineArchiveHandler``
    directly instead of this.

    :param roi_dict: mapping of site -> geometry (see :py:class:`InSituCallHandler`).
    :param archive_path: root directory to search (see
        :py:meth:`~scrappi.api.offlinebase.OfflineArchiveHandler._resolve_archive_path`).
    """

    @abstractmethod
    def perform_query(self, query: dict) -> ProductItemSet:
        """
        Return catalogue product objects that satisfy query

        :param query: catalogue query
        :returns: product urls satisfying query
        """
        pass

    def download_file(
        self,
        product: Union[str, ProductItem],
        fs: Optional[Union[str, BaseFileSystem]] = None,
    ) -> Union[list, str]:
        """Path to *product*'s already-local file.

        Lower-level than :py:meth:`~scrappi.api.offlinebase.OfflineArchiveHandler.download_product`
        (which callers should prefer -- it also re-locates a catalogue-rebuilt
        product). Kept because :py:class:`InSituCallHandler` declares it abstract.

        :param product: a :py:class:`~scrappi.product.ProductItem`.
        :param fs: if given, copy the product onto this filesystem first.
        :returns: the resolved path.
        """
        if not isinstance(product, ProductItem):
            raise TypeError("product must be a ProductItem for InSituOfflineCallHandler.download_file")
        if fs is not None:
            product.move_product(fs, copy=True)

        return product.get_path()


if __name__ == "__main__":
    pass
