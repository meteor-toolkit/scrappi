"""HYPERNETS API handlers for in-situ product discovery and download.

This module contains both online and offline HYPERNETS call handlers which
implement the `InSituCallHandler` interface to query HYPERNETS catalogues
and resolve product downloads.
"""

import datetime
import os

from shapely.geometry import Polygon
from typing import Any, Dict, Optional, Union, List
from processor_tools import Context

from scrappi.api.insitubase import InSituOfflineCallHandler, InSituCallHandler
from scrappi.product import ProductItem, ProductItemSet
from scrappi.utils.utils import generate_bounding_lat_lon

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
]
__all__ = ["HYPERNETSOfflineCallHandler"]

HYPERNETS_DEFAULT_ROI = {
    "GHNA": generate_bounding_lat_lon(-23.60153, 15.12589, 100),
    "WWUK": {
        "latitude_minimum": 51.77632771952633,
        "longitude_minimum": -1.3399758460979756,
        "latitude_maximum": 51.77808426115803,
        "longitude_maximum": -1.3370120963843524,
    },
    "PEAN": [
        -71.94130941393267,
        23.3038867960562,
        -71.93894657967229,
        23.30663303562398,
    ],
    "BASP": Polygon(
        [
            [-2.0770842203487048, 39.048247138903605],
            [-2.0747497502977192, 39.048247138903605],
            [-2.0747497502977192, 39.05003084892345],
            [-2.0770842203487048, 39.05003084892345],
            [-2.0770842203487048, 39.048247138903605],
        ]
    ),
}

COLLECTIONS = [
    "LHYP_L2B_REF",
    "LHYP_L1D_RAD",
    "LHYP_L1D_IRR",
    "LHYP_L2A_REF",
    "LHYP_L1B_RAD",
    "LHYP_L1B_IRR",
]


class HYPERNETSCallHandler(InSituCallHandler):
    """Online HYPERNETS call handler.

    Use this handler to query the HYPERNETS web API and download files. API
    credentials are provided via the scrappi context under the ``hypernets``
    configuration key.
    """

    name = "hypernets"
    sites: List[str] = list(HYPERNETS_DEFAULT_ROI.keys())
    DEFAULT_SITE_DEFINITIONS: dict = HYPERNETS_DEFAULT_ROI
    collections: List[str] = COLLECTIONS
    _default_geometries: Dict[str, Polygon] = {}

    def __init__(self, context: Optional[Union[str, List, Context]] = None, api_key=None):
        super().__init__(context, HYPERNETS_DEFAULT_ROI)
        if api_key is None:
            api_key = self.context["hypernets"]["credentials"]["apikey"]
        # lazy import of hypernets_api
        try:
            from hypernets_api import HYPERNETSAPI

            self.api = HYPERNETSAPI(api_key)
        except Exception as e:  # pragma: no cover - environment dependent
            raise RuntimeError("hypernets_api package is required to use HYPERNETSCallHandler: %s" % e)

    def get_constellation(self, prod_dict: dict) -> str:
        """
        Function to extract constellation identifier

        :param prod_dict: product dictionary
        :return: constellation identifier
        """
        return "HYPERNETS"

    def get_platform(self, prod_dict: dict) -> str:
        """
        Function to extract platform identifier

        :param prod_dict: product dictionary
        :return: platform identifier
        """
        return prod_dict["site_id"]

    def list_collections(self, fetch_update: Optional[bool] = False) -> List[str]:
        """
        Function to extract collection identifier

        :param fetch_update: unused; included for API compatibility
        :return: collection identifier
        """
        return self.collections

    # def _get_product_type(self, query_collection: str) -> tuple:
    #     """
    #     Get the product type associated with collection.
    #     Returns collection if collection is a valid product type for the api.

    #     :param query_collection: collection id of the query
    #     :return: site id, collection id if valid (else ValueError is raised)
    #     """
    #     # first check if query_collection is one of the site names
    #     if query_collection in self.sites:
    #         return query_collection, query_collection
    #     # Next check if the start of the collection is site name
    #     elif query_collection[0:4] in self.sites:
    #         return query_collection[0:4], query_collection
    #     elif "HYPERNETS" in query_collection:
    #         return "HYPERNETS", query_collection
    #     else:
    #         raise ValueError(
    #             "Selected Dataset '{}' not found in {} api.".format(
    #                 query_collection, self.name
    #             )
    #         )

    def list_sites(self) -> list:
        """
        Return list of sites available in API

        :return: list of site names
        """
        return self.sites

    def perform_query(
        self,
        query: dict,
    ) -> ProductItemSet:
        """
        Return ProductItemSet containing ProductItems that satisfy query

        :param query: catalogue query
        :returns: ProductItemSet
        """

        if query["collection"].startswith("LHYP"):
            query["collection"] = query["collection"][5::]

        if "platform" in query.keys() and "site" not in query.keys():
            query["site"] = query.pop("platform")

        hypernets_results = self.api.query(query)

        product_list = []
        for feature in hypernets_results["features"]:
            props = feature["properties"]
            asset = feature["assets"]["data"]

            href = asset["href"]
            product_name = href.split("/")[-1]

            product_list.append(
                ProductItem(
                    constellation="HYPERNETS",
                    platform=props["site_id"],
                    collection="LHYP_" + query["collection"],
                    id=product_name,
                    geometry=self.get_roi_shapely(props["site_id"]),
                    start_time=self._get_datetime(props["start_datetime"]),
                    stop_time=self._get_datetime(props["end_datetime"]),
                    prod_dict=props,
                    url=href,
                    quicklook="",
                    api=self,
                    context=self.context,
                )
            )

        return ProductItemSet(product_list)

    def download_file(
        self, prod: Union[str, ProductItem], dest: Optional[Union[str, Any]] = None
    ) -> Optional[Union[list, str]]:
        """
        Download the file at URL into dest using class credentials for basic auth
        :param prod: HYPERNETS ProductItem
        :param dest: destination folder for downloaded file
        """
        if not isinstance(prod, ProductItem):
            raise TypeError("prod must be a ProductItem")
        if dest is None:
            raise ValueError("dest must be provided")
        dest_str = str(dest)
        href: str = prod.url or ""

        if not os.path.exists(os.path.dirname(dest_str)):
            os.makedirs(os.path.dirname(dest_str))

        self.api.client.download_asset(href, os.path.dirname(dest_str))

        return os.path.join(dest_str, os.path.basename(href))


class HYPERNETSOfflineCallHandler(InSituOfflineCallHandler):
    """Offline HYPERNETS handler for archived HYPERNETS data.

    This handler reads from a local archive created by HYPERNETS and exposes
    the same query interface as the online handler, but resolves product files
    from the local archive rather than downloading them.
    """

    name = "hypernets_offline"
    sites: List[str] = list(HYPERNETS_DEFAULT_ROI.keys())
    DEFAULT_SITE_DEFINITIONS: dict = HYPERNETS_DEFAULT_ROI
    collections: List[str] = COLLECTIONS
    _default_geometries: Dict[str, Polygon] = {}
    #: OfflineArchiveHandler reads the archive root from context["fs"]["path"] when
    #: it isn't passed to __init__.
    ARCHIVE_PATH_CONTEXT_KEYS = ("fs", "path")

    def __init__(self, context: Optional[Union[str, List, Context]] = None, archive_path=None):
        # OfflineArchiveHandler resolves self.archive_path (arg -> context["fs"]["path"])
        # and provides download_product / _archive_path_for; InSituCallHandler takes
        # the roi_dict. No context mutation for organise_data -- perform_query builds
        # each per-product filesystem flat.
        super().__init__(context, roi_dict=HYPERNETS_DEFAULT_ROI, archive_path=archive_path)
        # lazy import of hypernets_api offline API
        try:
            from hypernets_api import OfflineHYPERNETSAPI

            if archive_path == "tdrive":
                archive_path = os.path.abspath(r"T:\\ECO\\EOServer\\data\\insitu\\hypernets\\archive")
                
            self.api = OfflineHYPERNETSAPI(archive_path)
        except Exception as e:  # pragma: no cover - environment dependent
            raise RuntimeError("hypernets_api (offline) is required to use HYPERNETSOfflineCallHandler: %s" % e)

    def get_constellation(self, prod_dict: dict) -> str:
        """
        Function to extract constellation identifier

        :param prod_dict: product dictionary
        :return: constellation identifier
        """
        return "HYPERNETS"

    def get_platform(self, prod_dict: dict) -> str:
        """
        Function to extract platform identifier

        :param prod_dict: product dictionary
        :return: platform identifier
        """
        return prod_dict["site_id"]

    def list_collections(self, fetch_update: Optional[bool] = False) -> List[str]:
        """
        Function to extract collection identifier

        :param fetch_update: unused; included for API compatibility
        :return: collection identifier
        """
        return self.collections

    # def _get_product_type(self, query_collection: str) -> tuple:
    #     """
    #     Get the product type associated with collection.
    #     Returns collection if collection is a valid product type for the api.

    #     :param query_collection: collection id of the query
    #     :return: site id, collection id if valid (else ValueError is raised)
    #     """
    #     # first check if query_collection is one of the site names
    #     if query_collection in self.sites:
    #         return query_collection, query_collection
    #     # Next check if the start of the collection is site name
    #     elif query_collection[0:4] in self.sites:
    #         return query_collection[0:4], query_collection
    #     elif "HYPERNETS" in query_collection:
    #         return "HYPERNETS", query_collection
    #     else:
    #         raise ValueError(
    #             "Selected Dataset '{}' not found in {} api.".format(
    #                 query_collection, self.name
    #             )
    #         )

    def perform_query(
        self,
        query: dict,
    ) -> ProductItemSet:
        """
        Return ProductItemSet containing ProductItems that satisfy query

        :param query: catalogue query
        :returns: ProductItemSet
        """
        query = dict(query)  # don't mutate the caller's dict
        if query["collection"].startswith("LHYP"):
            query["collection"] = query["collection"][5::]

        if "platform" in query.keys() and "site" not in query.keys():
            query["site"] = query.pop("platform")

        hypernets_results = self.api.query(query)

        product_list = []
        for prod in hypernets_results:
            product_list.append(
                ProductItem(
                    constellation="HYPERNETS",
                    platform=prod["site_id"],
                    collection="LHYP_" + query["collection"],
                    id=prod["product_name"] + ".nc",
                    geometry=self.get_roi_shapely(prod["site_id"]),
                    start_time=self._get_datetime(prod["datetime_start"]) if prod["datetime_start"] != '1970-01-01 01:00:00.000000' else self._get_datetime(prod["datetime_SEQ"]) + datetime.timedelta(hours = 1),
                    stop_time=self._get_datetime(prod["datetime_end"]),
                    prod_dict=prod,
                    filter_dict=self.extract_filter_attributes(prod),
                    # Flat filesystem (STACFileSystem, not plain LocalFileSystem) pinned
                    # to the product's own archive directory: the file is already there,
                    # so organise_data (which would rebuild a reorganised path from
                    # product metadata) is off, and the archive is not ours to write to.
                    # STACFileSystem (rather than LocalFileSystem) so
                    # ProductItem.to_stac_item() -- called when a matchup is added to a
                    # catalogue -- has return_stac_item_path (see the identical fix for
                    # RadcalnetOfflineCallHandler).
                    filesystem=self._flat_filesystem(
                        os.path.join(self.api.archive_path, prod["rel_product_dir"]),
                        read_only=True,
                    ),
                    url=prod["sequence_name"],
                    quicklook="",
                    api=self,
                )
            )

        return ProductItemSet(product_list)

    def extract_filter_attributes(self, prod_dict: dict) -> dict:
        """
        Function to extract information that can later be used for filtering,
        and convert the name from the provider specific attribute, to that expected by matchmaker.

        :param prod_dict: eodag product dictionary
        :return: dictionary with filter attributes
        """
        filter_dict: Dict[str, Any] = {}

        return filter_dict
    
    def _default_archive_path(self):
        return os.path.abspath(r"T:\\ECO\\EOServer\\data\\insitu\\hypernets\\archive\\")

    def _resolve_archive_path(self, archive_path: Optional[str]) -> str:
        """The archive root: *archive_path* if given, else the value at
        :py:data:`ARCHIVE_PATH_CONTEXT_KEYS` in the context, else
        :py:meth:`_default_archive_path`."""
        if archive_path is not None:
            return archive_path
        else:
            return self._default_archive_path()
    
    def _archive_path_for(self, product: ProductItem) -> Optional[str]:
        """Absolute path of *product*'s file within :py:attr:`archive_path`, by
        matching its ``id`` against filenames in the tree -- or ``None`` if it
        isn't there.

        :py:meth:`perform_query` attaches a correct per-file filesystem to every
        product it returns, but a product rebuilt from a STAC catalogue (eomatch's
        ``product_item_from_stac``) arrives with none, so :py:meth:`download_product`
        re-resolves it here rather than trusting ``product.filesystem``. Resolved via
        :py:attr:`_archive_index` (one walk, cached); subclasses whose ids don't map
        1:1 to filenames override this.
        """
        target = getattr(product, "id", None)
        target_dir = os.path.join(self.archive_path, product.platform, target.split("_")[-3][:4], target.split("_")[-3][4:6], target.split("_")[-3][6:8])
        for dirpath, _dirnames, filenames in os.walk(target_dir):
            for filename in filenames:
                if filename == target:
                    if os.path.exists(os.path.join(dirpath, filename)):
                        return os.path.join(dirpath, filename)
                    else:
                        return None

if __name__ == "__main__":
    pass
