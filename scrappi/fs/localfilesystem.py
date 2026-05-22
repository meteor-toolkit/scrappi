"""Local filesystem adapter used to locate and manage archived products.

This module implements `LocalFileSystem`, a concrete `BaseFileSystem` that
resolves product paths from a local directory tree. The resolver supports
several common product filename/dir conventions (zip, SAFE, nc, json).
"""

import os
import re
import csv
import datetime as dt
import requests
from typing import Optional, Union, Any, List, Tuple
from scrappi.fs.base import BaseFileSystem
from scrappi.product import ProductItem
from scrappi import ScrappiContext

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]
__all__ = ["LocalFileSystem"]


class LocalFileSystem(BaseFileSystem):
    """Filesystem adapter for local product archives.

    The adapter can return organized paths based on product metadata or a
    flat directory layout. It also contains helpers to detect common file
    suffixes and to produce STAC HREFs used elsewhere in scrappi.
    """

    def __init__(
        self,
        path: str = None,
        context: ScrappiContext = None,
    ):
        if not context:
            context = ScrappiContext()
        if path:
            directory = path
        else:
            directory = context["fs"]["path"]
        super().__init__(directory)
        self.organise_data = context["fs"]["organise_data"]
        self.read_only = context["fs"]["read_only"]

    def return_path(self, product_item: ProductItem, check_exists: bool = False):
        """
        Returns path from info in ProductItem
        The function automatically checks if a file exists with ".zip", ".SAFE", ".nc" and if so, the returned path will include this extension.

        :param product_item: ProductItem defining info, including ``"product_name"`` and ``"datetime"``
        :param check_exists: if true, returns None if product not in archive
        :return: product path (optionally followed with bool of whether path exists)
        """
        if self.organise_data:
            rel = self.return_organised_product_path(product_item)
            # Normalize directory and organiser return to avoid duplicate
            # base directories or mixed-slash absolute paths produced by
            # some backends. If `rel` is an absolute path or already
            # begins with the filesystem directory, use it directly.
            norm_dir = os.path.normpath(self.directory)
            rel_str = str(rel)
            norm_rel = os.path.normpath(rel_str)
            if os.path.isabs(norm_rel) or norm_rel.startswith(norm_dir):
                path = norm_rel
            else:
                path = os.path.normpath(os.path.join(self.directory, rel_str))
        else:
            path = self.directory

        # If `path` already appears to point to a file return it directly to avoid appending the product id again
        lower = path.lower()
        if (
            os.path.isfile(path)
            or lower.endswith(".tar.gz")
            or any(lower.endswith(ext) for ext in (".zip", ".SAFE", ".nc", ".json", ".SEN3", ".tar"))
        ):
            path_out = path
            path_exists = os.path.exists(path_out)
            if check_exists:
                return path_out, path_exists
            return path_out

        # If the path already ends with the product id, avoid appending it again
        if os.path.basename(path) == product_item.id:
            path_out = path
            path_exists = os.path.exists(path_out)
            if check_exists:
                return path_out, path_exists
            return path_out

        path_out, path_exists = self.check_any_path_exists(path, product_item.id)

        if check_exists:
            return path_out, path_exists
        else:
            return path_out

    def check_any_path_exists(self, path, id):
        """
        check whether either a path based on the id, a zipped file of the id, or an id.SAFE path exists.

        :param path: directory to check whether path exists in.
        :param id: id of the path (file or folder) to be checked
        :return: tuple with path, boolean to indicate whether path exists or not
        """
        path_id = os.path.join(path, id)

        path_zip = os.path.join(path, id + ".zip")

        path_SAFE = os.path.join(path, id + ".SAFE")

        path_nc = os.path.join(path, id + ".nc")

        path_json = os.path.join(path, id + ".json")

        path_SEN3 = os.path.join(path, id + ".SEN3")

        path_tar = os.path.join(path, id + ".tar")

        path_tar_gz = os.path.join(path, id + ".tar.gz")

        if os.path.exists(path_id):
            path_out = path_id
            path_exists = True
        elif os.path.exists(path_zip):
            path_out = path_zip
            path_exists = True
        elif os.path.exists(path_SAFE):
            path_out = path_SAFE
            path_exists = True
        elif os.path.exists(path_nc):
            path_out = path_nc
            path_exists = True
        elif os.path.exists(path_json):
            path_out = path_json
            path_exists = True
        elif os.path.exists(path_SEN3):
            path_out = path_SEN3
            path_exists = True
        elif os.path.exists(path_tar):
            path_out = path_tar
            path_exists = True
        elif os.path.exists(path_tar_gz):
            path_out = path_tar_gz
            path_exists = True
        else:
            path_out = path_id
            path_exists = False

        return path_out, path_exists

    def return_organised_product_path(self, product_item: ProductItem):
        """
        Returns relative path in standard organised format for product with defined info

        :param product_info: product defining info, including ``"product_name"`` and ``"datetime"``
        :return: product path
        """
        constellation = product_item.constellation
        platform = product_item.platform
        collection = product_item.collection
        start_time = product_item.start_time
        day = start_time.strftime("%d")
        month = start_time.strftime("%m")
        year = start_time.strftime("%Y")

        return self.return_path_constellation_platform_collection_year_month_day(
            constellation, platform, collection, year, month, day
        )

    def return_path_constellation_platform_collection_year_month_day(
        self,
        constellation: str,
        platform: str,
        collection: str,
        year: str,
        month: str,
        day: str,
    ):
        """
        Returns path from provided info

        :param constellation: id of the constellation (i.e. the satellite constellation)
        :param platform: id of the platform (i.e. the satellite)
        :param collection: id of collection of data
        :param year: year of observation
        :param month: month of observation
        :param day: day of observation
        :return: product path
        """
        return os.path.join(constellation, platform, collection, year, month, day)
