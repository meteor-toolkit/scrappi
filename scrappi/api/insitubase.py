"""Base classes for in-situ (ground) API call handlers.

Defines shared abstractions for in-situ data providers (for example
RadCalNet or HYPERNETS). These base classes provide ROI management and
common download helpers used by concrete in-situ handlers.
"""

from abc import ABC, abstractmethod
from scrappi.api.base import BaseAPICallHandler
from scrappi.product import ProductItem, ProductItemSet
from scrappi.utils.utils import *
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

    def __init__(
        self, context: Optional[Union[str, List, Context]] = None, roi_dict: dict = None
    ):
        super().__init__(context)
        self.roi_dict = roi_dict
        self.sites = list(roi_dict.keys())

    def get_roi_shapely(self, site: str):
        return convert_geom_shapely(self.roi_dict[site])

    def get_roi(self, site: str):
        return convert_geom(self.roi_dict[site])

    def set_roi(self, site: str, geom: Any):
        self.roi_dict[site] = geom

    def set_roi_bounding_box(
        self,
        site: str,
        lat: float,
        lon: float,
        distance: float,
        crs: str = "EPSG:32630",
    ):
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
    def perform_query(self, query: dict) -> list:
        """
        Return catalogue product objects that satisfy query

        :param query: catalogue query
        :returns: product urls satisfying query
        """
        pass

    @abstractmethod
    def download_file(self, prod: ProductItem, dest: str) -> None:
        """
        Download the file at URL into dest using class credentials for basic auth
        :param prod: rcn ProductItem
        :param dest: destination folder for downloaded file
        """
        pass

    def download_product(
        self, product: Union[ProductItemSet, ProductItem]
    ) -> Union[list, str]:
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
            path, exists = product.filesystem.return_path(product, check_exists=True)

            if exists:
                print(f"{path} exists")
                return path

            else:
                print(f"{product.id} needs downloading")
                return self.download_file(product, path)


class InSituOfflineCallHandler(InSituCallHandler):
    """
    Class for offline insitu call handler implementations.

    InSituOfflineCallHandlers require a ROI dictionary and

    Subclasses must implement abstract methods.

    :param roi_dict: dictionary with the ROI for the different sites included in the in situ API
    """

    @abstractmethod
    def perform_query(self, query: dict) -> list:
        """
        Return catalogue product objects that satisfy query

        :param query: catalogue query
        :returns: product urls satisfying query
        """
        pass

    def download_file(
        self,
        product: Union[str, ProductItem],
        fs: Optional[Union[None, str, BaseFileSystem]] = None,
    ) -> Union[list, str]:
        """
        return path to product for the provided filesystem (one could also just use the ProductItem.get_path() function

        :param product: ProductItem of ProductItemSet from a product query
        :param fs: filesystem (can be path or file system object (BaseFileSystem)). Defaults to None, in which case product.filesystem is used.
        :returns: path (or list of paths) to the relevant file(s)
        """
        if fs is not None:
            product.move_product(fs, copy=True)

        return product.get_path()


if __name__ == "__main__":
    pass
