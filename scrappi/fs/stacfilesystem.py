"""STAC-enabled filesystem adapter.

`STACFileSystem` extends `LocalFileSystem` to support repositories that
provide a STAC layout (separate "stac" and "data" roots). The class
offers helpers for deriving STAC item JSON paths and logical HREFs used by
the STAC integration in scrappi.
"""

import os
from pathlib import Path
from urllib.parse import urljoin
from typing import Optional, Union, Any, List, Tuple
from scrappi.fs.localfilesystem import LocalFileSystem
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


class STACFileSystem(LocalFileSystem):
    """Adapter for filesystems that expose STAC catalogs alongside data.

    The adapter can resolve both data asset locations and STAC item JSON
    paths and provides `stac://` and `asset://` logical HREF helpers.
    """

    def __init__(
        self,
        path: str = "./",
        path_stac: str = None,
        context: ScrappiContext = None,
    ):
        if not context:
            context = ScrappiContext()

        super().__init__(path, context)

        if path_stac is None:
            if "path_stac" in context["fs"].keys():
                path_stac = context["fs"]["path_stac"]
            else:
                path_stac = path

        # check if path already ends with "data", if so remove this from path
        if os.path.basename(path) == "data":
            path = os.path.dirname(path)

        # check if path_stac already ends with "stac", if so remove this from path_stac
        if os.path.basename(path_stac) == "stac":
            path_stac = os.path.dirname(path_stac)

        self.directory = path
        self.directory_stac = path_stac

        self.data_root = os.path.join(self.directory, "data")
        self.stac_root = os.path.join(self.directory_stac, "stac")

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

        rel_path = os.path.join("data", constellation, platform, collection, year, month, day)

        # Resolve to full directory under this filesystem, then check for
        # product file/folder with known extensions (zip, SAFE, nc, etc.).
        full_dir = os.path.join(self.directory, rel_path)
        path_out, path_exists = self.check_any_path_exists(full_dir, product_item.id)

        return path_out

    def return_stac_item_path(self, product_item: ProductItem, check_exists: bool = False):
        """
        Returns path from info in ProductItem
        The function automatically checks if a file exists with ".zip", ".SAFE", ".nc" and if so, the returned path will include this extension.

        :param product_item: ProductItem defining info, including ``"product_name"`` and ``"datetime"``
        :param check_exists: if true, returns None if product not in archive
        :return: product path (optionally followed with bool of whether path exists)
        """
        if self.organise_data:
            path = os.path.join(
                self.directory_stac,
                self.return_organised_stac_item_path(product_item),
            )

        else:
            path = os.path.join(self.directory_stac, "stac", "items")

        path_out, path_exists = self.check_any_path_exists(path, product_item.id)

        if not path_out[-5::] == ".json":
            if path_out[-3::] == ".nc":
                path_out = path_out.replace(".nc", ".json")
            elif path_out[-4::] == "zip":
                path_out = path_out.replace(".zip", ".json")
            elif path_out[-5::] == ".SAFE":
                path_out = path_out.replace(".SAFE", ".json")
            else:
                path_out = path_out + ".json"

        path_exists = os.path.exists(path_out)

        if check_exists:
            return path_out, path_exists
        else:
            return path_out

    def return_organised_stac_item_path(self, product_item: ProductItem):
        """
        Returns relative path in standard organised format for stac item with defined info

        :param product_info: stac item defining info, including ``"product_name"`` and ``"datetime"``
        :return: stac item path
        """
        collection = product_item.collection
        start_time = product_item.start_time
        day = start_time.strftime("%d")
        month = start_time.strftime("%m")
        year = start_time.strftime("%Y")

        return os.path.join("stac", collection, "items", year, month, day)

    @staticmethod
    def stac_href(*parts: str) -> str:
        return "stac://" + "/".join(p.strip("/") for p in parts)

    @staticmethod
    def asset_href(*parts: str) -> str:
        return "asset://" + "/".join(p.strip("/") for p in parts)
