"""HYPERNETS API handlers for in-situ product discovery and download.

This module contains both online and offline HYPERNETS call handlers which
implement the `InSituCallHandler` interface to query HYPERNETS catalogues
and resolve product downloads.
"""

import os
import re
import csv
import warnings

import shapely
import shapely.wkt
from shapely.geometry import Polygon
import datetime as dt
import requests
from typing import Optional, Union, Any, List, Tuple
from processor_tools import Context

from scrappi.api.insitubase import InSituOfflineCallHandler, InSituCallHandler
from scrappi.product import ProductItem, ProductItemSet
from scrappi.utils.utils import *
from scrappi.fs.base import BaseFileSystem
from scrappi.fs.localfilesystem import LocalFileSystem

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
    "LHYP_REF_L2B",
    "LHYP_RAD_L1D",
    "LHYP_IRR_L1D",
    "LHYP_REF_L2A",
    "LHYP_RAD_L1B",
    "LHYP_IRR_L1B",
]


class HYPERNETSCallHandler(InSituCallHandler):
    """Online HYPERNETS call handler.

    Use this handler to query the HYPERNETS web API and download files. API
    credentials are provided via the scrappi context under the ``hypernets``
    configuration key.
    """

    name = "hypernets"
    sites: list[str] = HYPERNETS_DEFAULT_ROI.keys()
    DEFAULT_SITE_DEFINITIONS: dict = HYPERNETS_DEFAULT_ROI
    collections: list[str] = COLLECTIONS
    _default_geometries: dict[str:Polygon] = {}

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

    def list_collections(self) -> List[str]:
        """
        Function to extract collection identifier

        :param prod_dict: product dictionary
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

    def download_file(self, prod: ProductItem, dest: str) -> None:
        """
        Download the file at URL into dest using class credentials for basic auth
        :param prod: rcn ProductItem
        :param dest: destination folder for downloaded file
        """

        href = prod.url

        if not os.path.exists(os.path.dirname(dest)):
            os.makedirs(os.path.dirname(dest))

        self.api.client.download_asset(href, os.path.dirname(dest))

        return os.path.join(dest, os.path.basename(href))


class HYPERNETSOfflineCallHandler(InSituOfflineCallHandler):
    """Offline HYPERNETS handler for archived HYPERNETS data.

    This handler reads from a local archive created by HYPERNETS and exposes
    the same query interface as the online handler, but resolves product files
    from the local archive rather than downloading them.
    """

    name = "hypernets_offline"
    sites: list[str] = HYPERNETS_DEFAULT_ROI.keys()
    DEFAULT_SITE_DEFINITIONS: dict = HYPERNETS_DEFAULT_ROI
    collections: list[str] = COLLECTIONS
    _default_geometries: dict[str:Polygon] = {}

    def __init__(self, context: Optional[Union[str, List, Context]] = None, archive_path=None):
        super().__init__(context, HYPERNETS_DEFAULT_ROI)
        # lazy import of hypernets_api offline API
        try:
            from hypernets_api import OfflineHYPERNETSAPI

            self.api = OfflineHYPERNETSAPI(archive_path)
        except Exception as e:  # pragma: no cover - environment dependent
            raise RuntimeError("hypernets_api (offline) is required to use HYPERNETSOfflineCallHandler: %s" % e)
        self.context["fs"]["organise_data"] = False

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

    def list_collections(self) -> List[str]:
        """
        Function to extract collection identifier

        :param prod_dict: product dictionary
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

        hypernets_results = self.api.query(query)

        product_list = []
        for prod in hypernets_results:
            product_list.append(
                ProductItem(
                    constellation="HYPERNETS",
                    platform=prod["site_id"],
                    collection=query["collection"],
                    id=prod["product_name"] + ".nc",
                    geometry=self.get_roi_shapely(prod["site_id"]),
                    start_time=self._get_datetime(prod["datetime_start"]),
                    stop_time=self._get_datetime(prod["datetime_end"]),
                    prod_dict=prod,
                    filter_dict=self.extract_filter_attributes(prod),
                    filesystem=LocalFileSystem(
                        os.path.join(self.api.archive_path, prod["rel_product_dir"]),
                        self.context,
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
        filter_dict = {}

        return filter_dict


if __name__ == "__main__":
    pass
