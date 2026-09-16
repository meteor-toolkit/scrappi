"""HYPERNETS API handlers for in-situ product discovery and download.

This module contains both online and offline HYPERNETS call handlers which
implement the `InSituCallHandler` interface to query HYPERNETS catalogues
and resolve product downloads.
"""

import os

import shapely
from shapely.geometry import Polygon
from typing import Any, Dict, Optional, Union, List
from processor_tools import Context

from scrappi.api.insitubase import InSituOfflineCallHandler, InSituCallHandler
from scrappi.product import ProductItem, ProductItemSet
from scrappi.utils.utils import generate_bounding_lat_lon
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
    "INSIF_RADIRRREF",
    "INSIF_ALLIDX",
    "INSIF_RAW",
]


class INSIFCallHandler(InSituCallHandler):
    """Online INSIF call handler.

    Use this handler to query the INSIF web API and download files. API
    credentials are provided via the scrappi context under the ``hypernets``
    configuration key.
    """

    name = "insif"
    sites: List[str] = list(HYPERNETS_DEFAULT_ROI.keys())
    DEFAULT_SITE_DEFINITIONS: dict = HYPERNETS_DEFAULT_ROI
    collections: List[str] = COLLECTIONS
    _default_geometries: Dict[str, Polygon] = {}

    def __init__(self, context: Optional[Union[str, List, Context]] = None):
        super().__init__(context, HYPERNETS_DEFAULT_ROI)
        # lazy import of GeoDBClient
        try:
            from xcube_geodb.core.geodb import GeoDBClient
            os.environ["GEODB_AUTH_DOMAIN"] = "https://winchester.production.brockmann-consult.de/winchester"

            server_url = "http://80.158.77.185"
            server_port = 80

            username = self.context["insif"]["credentials"]["username"]
            password = self.context["insif"]["credentials"]["password"]

            self.DATABASE = "deflox"

            geodb = GeoDBClient(client_id=username,
                                client_secret=password,
                                server_url=server_url,
                                server_port=server_port)
            geodb.whoami

            print(list(geodb.get_my_collections(self.DATABASE)["collection"]))

            self.api = geodb
            
        except Exception as e:  # pragma: no cover - environment dependent
            raise RuntimeError("xcube_geodb package is required to use GeoDBClient: %s" % e)

    def get_constellation(self, prod_dict: dict) -> str:
        """
        Function to extract constellation identifier

        :param prod_dict: product dictionary
        :return: constellation identifier
        """
        return "INSIF"

    def get_platform(self, collection) -> str:
        """
        Function to extract platform identifier

        :param prod_dict: product dictionary
        :return: platform identifier
        """
        return 

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
        return [col for col in list(self.api.get_my_collections(self.DATABASE)["collection"]) if "-proc" in col]

    def get_sites_from_roi(self, roi):
        # get metadata of all collections and filter out those who don't intersect
        intersecting_collections = []
        collection_names = [col for col in list(self.api.get_my_collections(self.DATABASE)["collection"]) if col.endswith("-raw")]

        for col in collection_names:
            md = self.api.get_metadata(collection=col, database=self.DATABASE)
            if len(md.spatial_extent) > 1:
                # Collection does not have a valid bounding box yet
                continue
            else:
                col_bb = shapely.box(md.spatial_extent[0][0], md.spatial_extent[0][1], md.spatial_extent[0][2],
                                    md.spatial_extent[0][3])

            if col_bb.intersects(roi):
                intersecting_collections.append(col)

        return intersecting_collections

    def get_default_variables(self, collection):
        if collection=="INSIF_RADIRRREF":
            return "utc_time,L,E,R,u_systematic_L,u_random_R,u_systematic_R"
        elif collection=="INSIF_ALLIDX":
            return "utc_time,sfm_fld_o2a,sfm_fld_o2b"
        elif collection=="INSIF_RAW":
            return "utc_time,data"
        else:
            raise ValueError("Collection not recognised")

    def _perform_query(self, query):
        if "variables" not in query:
            variables = self.get_default_variables(query["collection"])
        variables = ""
        variables += "utc_time,sfm_fld_o2a,sfm_fld_o2b"

        where_str = ""
        where_str = "utc_time > '%s'::timestamp AND utc_time < '%s'::timestamp"%(query["start_time"],query["stop_time"])

        insif_collection = "JB-010-ES-idx"

        results = self.api.get_collection_pg(insif_collection,
                                      select=variables,
                                      where=where_str,
                                      database=self.DATABASE)
        return results

    def perform_query(
        self,
        query: dict,
    ) -> ProductItemSet:
        """
        Return ProductItemSet containing ProductItems that satisfy query

        :param query: catalogue query
        :returns: ProductItemSet
        """

        if "platform" in query.keys() and "site" not in query.keys():
            query["site"] = query.pop("platform")

        insif_results = self._perform_query(query)

        product_list = []
        for feature in insif_results["features"]:
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

