"""scrappi.api.base - base class for API call handler implementations.

This module defines the abstract `BaseAPICallHandler` which provides a
small, consistent interface that all API-specific handlers must implement.

Handlers are responsible for: discovering available collections,
translating user queries to API-specific formats, returning `ProductItemSet`
results and downloading products to a target filesystem.
"""

import datetime as dt
import warnings

from abc import ABC, abstractmethod
from typing import Optional, Any, Union, List
from dateutil.parser import parse

from scrappi.product import ProductItemSet, ProductItem
from scrappi.fs.factory import FSCallHandlerFactory
from scrappi.fs.base import BaseFileSystem
from scrappi.utils.utils import *
from scrappi.fs.localfilesystem import LocalFileSystem
from scrappi import ScrappiContext

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]
__all__ = ["BaseAPICallHandler"]


class BaseAPICallHandler(ABC):
    """Abstract base for API call handlers.

    Subclass this for each external catalogue or API (for example EODAG,
    RadCalNet, HYPERNETS, STAC). Subclasses must implement the abstract
    operations `perform_query` and `download_product` and should provide a
    `platforms` mapping where relevant.

    The handler stores a `ScrappiContext` in `self.context` and provides
    helper methods to normalise datetimes, geometries and to verify filesystems.
    """

    name: str

    def __init__(self, context, *args, **kwargs):
        self._FSFactory = FSCallHandlerFactory()
        if isinstance(context, ScrappiContext):
            self.context = context
        else:
            self.context = ScrappiContext(context)

    def parse_platform_from_name(self, name):
        if name[0:4] in ["LC08", "LO08"]:
            return "Landsat-8"
        elif name[0:4] in ["LC09", "LO09"]:
            return "Landsat-9"
        elif name[0:4] in ["CAMS", "ERA5", "REAN"]:
            return name[0:4]
        elif name[0:3] in ["S2A", "S2B", "S2C", "S3A", "S3B"]:
            return name[0:3]
        elif name[0:3] in ["MOD"]:
            return "Terra"
        elif name[0:3] in ["MYD"]:
            return "Aqua"
        else:
            raise NotImplementedError("platform name could not be parsed")

    def parse_constellation_from_name(self, name):
        if name[0:4] in ["LC08", "LO08", "LC09", "LO09"]:
            return "Landsat"
        elif name[0:4] in ["CAMS", "ERA5", "REAN"]:
            return "ECMWF"
        elif name[0:3] in ["S2A", "S2B", "S2C"]:
            return "Sentinel-2"
        elif name[0:3] in ["S3A", "S3B"]:
            return "Sentinel-3"
        elif name[0:3] in ["MOD", "MYD"]:
            return "MODIS"

        else:
            raise NotImplementedError("constellation name could not be parsed")

    @staticmethod
    def _get_datetime(date_time: Union[dt.datetime, dt.date, str]) -> dt.datetime:
        """
        Get the datetimes to use to query the api

        :param date_time: datetime in any accepted format (datetime.datetime, datetime.date or string)
        :returns: datetime in datetime.datetime format
        """
        return convert_datetime(date_time)

    @staticmethod
    def _get_geom(geom: Any) -> Any:
        """
        Get the geometry to use to query the api

        :param geom: geometry in any accepted format
        :returns: geometry in converted format
        """
        return convert_geom(geom)

    def _get_product_type(self, collection: str) -> str:
        """
        Get the product type associated with collection.
        Returns collection if collection is a valid product type for the api.

        :param collection: collection id of dataset
        :return: collection id if valid (else ValueError is raised)
        """
        if collection in self.list_collections():
            return collection
        else:
            warnings.warn(
                "Selected collection '{}' not automatically found in {} api. You can try setting context['api']['preferred_api] to circumvent this.".format(
                    collection, self.name
                )
            )
            return collection

    def check_fs(
        self,
        fs: Union[str, BaseFileSystem],
        organise_data: bool,
        product: Union[str, ProductItem, ProductItemSet],
    ) -> BaseFileSystem:
        """
        Checks whether the provided fs is a valid filesystem, and if not builds the correct fs

        :param fs: filesystem or path to existing folder
        :param organise_data: bool to indicate if data should be organised by platform/collection/year/month/day. Only used if fs is provided as path.
        :param product: ProductItem which contains filesystem as attribute. Only used if fs is provided as None.
        :return: valid filesystem
        """
        # first make sure fs is set to correct filesystem object
        if isinstance(product, ProductItem):
            fs = product.filesystem

        elif fs is None:
            fs = LocalFileSystem()

        elif isinstance(fs, str):
            fs = self._FSFactory.get_fs_call_handler(fs, organise_data=organise_data)

        if isinstance(fs, BaseFileSystem):
            return fs

        else:
            raise ValueError("provided filesystem is not valid")

    @abstractmethod
    def list_collections(self) -> List[str]:
        """
        Function to extract collection identifiers

        :return: list of collection identifiers
        """
        pass

    @abstractmethod
    def perform_query(self, query: dict) -> ProductItemSet:
        """
        Return ProductItemSet of catalogue products that satisfy query

        :param query: catalogue query
        :returns: ProductItemSet of catalogue products
        """
        pass

    def download_metadata(
        self,
        product: Union[str, ProductItem, ProductItemSet],
        fs: Optional[Union[str, BaseFileSystem]],
    ) -> None:
        """
        Download catalogue product(s) metadata at defined URL to local path

        :param product: search result from a product query
        :param path: local path to write metadata to
        """
        raise NotImplementedError

    @abstractmethod
    def download_product(
        self,
        product: Union[str, ProductItem, ProductItemSet],
    ) -> Union[list, str]:
        """
        Download catalogue product(s) at defined URL to local path

        :param product: ProductItem of ProductItemSet from a product query
        :param fs: filesystem (can be path or file system object (BaseFileSystem)). Defaults to None, in which case product.filesystem is used.
        :returns: path (or list of paths) to the relevant (downloaded) file(s)
        """
        pass


if __name__ == "__main__":
    pass
