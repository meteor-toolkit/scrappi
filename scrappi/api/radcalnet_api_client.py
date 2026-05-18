#!/usr/bin/env python3
# -------------------------------------------------------------------
# RadCalNet api client
# -------------------------------------------------------------------

"""RadCalNet API client handlers for scrappi.

Provides `RadcalnetCallHandler` and `RadcalnetOfflineCallHandler` to search
and retrieve in-situ RadCalNet products. The online handler uses RadCalNet's
JSON API with basic auth, while the offline handler resolves files from a
local archive.
"""

import os
import platform
import datetime as dt
import requests
from shapely.geometry import Polygon
from typing import Optional, Any, Union, List
import warnings
import numpy as np
import socket
from processor_tools import Context

from scrappi.api.base import BaseAPICallHandler
from scrappi.api.insitubase import InSituCallHandler, InSituOfflineCallHandler
from scrappi.product import ProductItemSet, ProductItem
from scrappi.utils.utils import generate_bounding_lat_lon, convert_geom_shapely
from scrappi.fs.base import BaseFileSystem

__author__ = [
    "Ashley James Ramsay <ashley.ramsay@npl.co.uk",
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
]
__all__ = ["RadcalnetCallHandler", "RadcalnetOfflineCallHandler"]


class RadcalnetCallHandler(InSituCallHandler):
    """Handler for RadCalNet online API.

    Credentials may be provided via the scrappi context under the
    ``RadCalNet.credentials`` mapping or read from the environment variables
    ``RADCALNET_USERNAME`` and ``RADCALNET_REMOVED_PASSWORD``.
    """

    url_base: str = "https://www.radcalnet.org/api/json/"
    DEFAULT_SITE_DEFINITIONS: dict[str : dict[str:float]] = {
        "GONA": {
            "latitude": -23.600200982764363,
            "longitude": 15.119555974379182,
            "default_roi": 250,
        },
        "BTCN": {"latitude": 40.851307, "longitude": 109.62922, "default_roi": 5},
        "BSCN": {"latitude": 40.8658, "longitude": 109.6155, "default_roi": 150},
        "LCFR": {"latitude": 43.558889, "longitude": 4.864167, "default_roi": 30},
        "RVUS": {
            "latitude": 38.497,
            "longitude": -115.690,
            "default_roi": 500,
        },  # default_roi values are 1/2 side len
    }
    _default_geometries: dict[str:Polygon] = {}

    COLLECTIONS = ["RCN_TOA", "RCN_BOA"]

    name = "radcalnet"

    def __init__(
        self,
        context: Optional[Union[str, List, Context]] = None,
    ):
        
        self._set_Polygons()  # convert ROI to Polygons
        # self.api = OfflineRcnAPI(archives_path)
        super(RadcalnetCallHandler, self).__init__(
            context, self._default_geometries
        )  # Runs the init that is in the base class

        credentials = self.context["RadCalNet"]["credentials"]
        if credentials:
            try:
                # set environment variables (when credentials provided)
                os.environ["RADCALNET_USERNAME"] = credentials["username"]
                os.environ["RADCALNET_REMOVED_PASSWORD"] = credentials["password"]
            except:
                warnings.warn(
                    "Provided RADCALNET credentials could not be set in environment variables."
                )
            self.session = requests.session()
            self.session.auth = (credentials["username"], credentials["password"])

        else:
            try:
                # retrieve credentials from environment variables (if no credentials provided)
                username = os.environ["RADCALNET_USERNAME"]
                password = os.environ["RADCALNET_REMOVED_PASSWORD"]
            except KeyError:
                raise ValueError("No credentials found to initialise api.")
            else:
                # initialise api for search and download
                self.session = requests.session()
                self.session.auth = (username, password)

    def list_collections(self) -> List[str]:
        """
        Function to extract collection identifiers

        :return: list of collection identifiers
        """
        return self.COLLECTIONS

    def list_sites(self) -> List[str]:
        """Return the known RadCalNet site identifiers.

        :return: iterable of site identifiers (e.g. 'GONA', 'BTCN')
        """
        return self.DEFAULT_SITE_DEFINITIONS.keys()

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

        date1 = self._get_datetime(query["start_time"])
        date2 = self._get_datetime(query["stop_time"])

        if date1 > date2:
            warnings.warn("the query stop_time was after the start_time")
            return []

        filelist = self.get_files_list(query["site"], query["collection"], date1, date2)

        product_list = []

        for filename in filelist:
            site_instrument, year, doy, version = self.parse_name(filename)
            site = site_instrument[0:4]
            geom = self._default_geometries[
                site
            ]  # get default geometry for site as Polygon
            product_list.append(
                ProductItem(
                    constellation="RadCalNet",
                    platform=site,
                    collection=query["collection"],
                    id=filename,
                    geometry=geom,
                    start_time=dt.datetime(year, 1, 1)
                    + dt.timedelta(days=doy - 1, hours=8),
                    stop_time=dt.datetime(year, 1, 1)
                    + dt.timedelta(days=doy - 1, hours=14),
                    url="",
                    quicklook="",
                    api="radcalnet",
                    context=self.context,
                )
            )

        return ProductItemSet(product_list)

    def check_date_in_range(
        self, year: int, doy: int, date1: dt.date, date2: dt.date
    ) -> bool:
        """
        Function to check whether date of file is between the query dates.

        :param year: year of RCN file
        :param doy: day of year of RCN file
        :param date1: start datetime in query
        :param date2: stop datetime in query
        :return: boolean indicated whether date is in query range or not
        """
        # Handle offset-aware datetimes by creating baselines with matching tzinfo
        tz1 = getattr(date1, "tzinfo", None)
        tz2 = getattr(date2, "tzinfo", None)
        baseline1 = dt.datetime(date1.year, 1, 1, 0, 0, tzinfo=tz1)
        baseline2 = dt.datetime(date2.year, 1, 1, 0, 0, tzinfo=tz2)
        doy1 = (date1 - baseline1).days
        doy2 = (date2 - baseline2).days

        if date1.year == date2.year:
            if year == date1.year and doy1 <= doy <= doy2:
                return True

        elif date1.year == year and doy1 <= doy:
            return True

        elif date2.year == year and doy <= doy2:
            return True

        elif date1.year < year < date2.year:
            return True

        else:
            return False

    def return_info(self, products) -> Optional[list]:
        """
        Return product info in common format for catalogue product(s)

        :param products: catalogue query
        :returns: list of product info as dictionary
        """
        raise NotImplementedError("not currently available for rcn files")

    def download_metadata(self, product, path: str) -> Optional[list[Any]]:
        """
        Download catalogue product(s) metadata at defined URL to local path

        :param product: search result from a product query
        :param path: local path to write metadata to
        """
        # No metadata can be downloaded for rcn products via available api
        # metadata is included in the rcn file instead
        raise NotImplementedError("not currently available for rcn files")

    def download_file(self, prod: ProductItem, dest: str) -> None:
        """
        Download the file at URL into dest using class credentials for basic auth
        :param prod: rcn ProductItem
        :param dest: destination folder for downloaded file
        """
        filename = prod.id
        site = prod.platform
        url = self.url_base + site + "/data/" + filename
        if not os.path.exists(os.path.dirname(dest)):
            os.makedirs(os.path.dirname(dest))
        with self.session.get(url, stream=True) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return os.path.join(dest, os.path.basename(url))

    def get_files_list(
        self, site: str, collection: str, start_date: dt.date, end_date: dt.date
    ) -> list:
        """
        generates a list of files between two dates
         :param site: name of rcn site: [BTCN, BSCN, GHNA, GONA, RVUS, LCFR]
         :param collection: name of collection (<site>, <site>_BOA or <site>_TOA)
         :param start_date: start date of acquisitions
         :param end_date: end date of acquisitions
        """

        if site not in self.sites:
            raise ValueError(
                "site {} unknown. Valid sites are {}".format(
                    site, ", ".join(self.sites)
                )
            )
        if start_date > end_date:
            return []
        url = self.url_base + site + "/data/"
        # get the list of all files for the site
        r = self.session.get(url)
        r.raise_for_status()
        filelist = [file["name"] for file in r.json()]

        mask = np.zeros(len(filelist))
        for ifile, filename in enumerate(filelist):
            if "TOA" in collection and ".input" in filename:
                mask[ifile] = 1
            elif "BOA" in collection and ".output" in filename:
                mask[ifile] = 1

            site_instrument, year, doy, version = self.parse_name(filename)
            if not self.check_date_in_range(year, doy, start_date, end_date):
                mask[ifile] = 1

        return [filelist[i] for i in range(len(filelist)) if mask[i] == 0]

    @staticmethod
    def parse_name(filename: str) -> tuple[str, int, int, str]:
        """
        split rcn filename into site, year, day of year and version number
        :param filename: name of rcn file
        """

        site_instrument, year, doy, version = filename.split("_")
        return (site_instrument, int(year), int(doy), version)

    def set_default_site_definitions(self, ROI: dict[str : Union[int, float]]) -> None:
        """
        :param ROI: dictionary ROIs per site
        """
        for site in self.DEFAULT_SITE_DEFINITIONS:
            if site in ROI:
                self.DEFAULT_SITE_DEFINITIONS[site]["default_roi"] = ROI[site]

        self._set_Polygons()

    def _set_Polygons(self) -> None:
        """
        convert site lat/lon and ROI into Polygons
        """
        _default_geometries: dict[str:Polygon] = {}
        for site, definition in self.DEFAULT_SITE_DEFINITIONS.items():
            self._default_geometries[site] = convert_geom_shapely(
                generate_bounding_lat_lon(
                    definition["latitude"],
                    definition["longitude"],
                    definition["default_roi"],
                )
            )


class RadcalnetOfflineCallHandler(InSituOfflineCallHandler):
    """
    Offline api handler for RadCalNet data

    :param name:
    :param local_path:
    """

    def __init__(self, archive_path=None):
        if archive_path is None:
            if platform.system() == "Linux":
                if socket.gethostname() == "eoserver.npl.co.uk":
                    archive_path = os.path.abspath(
                        os.path.join(r"/home", "data", "insitu", "radcalnet", "archive")
                    )
                else:
                    archive_path = os.path.abspath(
                        os.path.join(
                            r"/mnt", "t", "data", "insitu", "radcalnet", "archive"
                        )
                    )
            else:
                archive_path = os.path.abspath(
                    os.path.join(
                        r"T:\ECO", "EOServer", "data", "insitu", "radcalnet", "archive"
                    )
                )  # r"\\eoserver", "home", "data", "insitu", "radcalnet", "archive"

        self.archive_path = archive_path

    def perform_query(self, query: dict) -> ProductItemSet:
        """
        Return catalogue product objects that satisfy query

        :param query: catalogue query
        :returns: ProductItemSet satisfying query
        """
        pass
