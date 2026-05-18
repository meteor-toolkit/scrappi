"""Jasmin filesystem adapter (placeholder).

`JasminFileSystem` is a small adapter intended for Jasmin-hosted archives.
Paths are currently TODO; the adapter exists as a convenience and mirrors
the STAC filesystem behaviour for read-only archives.
"""

import os
import re
import csv
import datetime as dt
import requests
from typing import Optional, Union, Any, List, Tuple
from scrappi.fs.stacfilesystem import STACFileSystem
from scrappi.product import ProductItem
import socket
from scrappi import ScrappiContext

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]
__all__ = ["JasminFileSystem"]


class JasminFileSystem(STACFileSystem):
    """
    UNDER DEVELOPMENT - NOT READY FOR USE

    Filesystem adapter for Jasmin-hosted product archives (read-only).
    """

    def __init__(self, context: ScrappiContext):
        path = os.path.join("")  # TODO: add path to jasmin archive here
        path_stac = os.path.join("")  # TODO: add path to jasmin stac here
        context["fs"]["organise_data"] = True
        context["fs"]["read_only"] = True
        super().__init__(path=path, path_stac=path_stac, context=context)

    def return_organised_product_path(self, product_item: ProductItem):
        """
        Returns relative path in standard organised format for product with defined info

        :param product_info: product defining info, including ``"product_name"`` and ``"datetime"``
        :return: product path
        """
        start_time = product_item.start_time
        day = start_time.strftime("%d")
        month = start_time.strftime("%m")
        year = start_time.strftime("%Y")

        return os.path.join(year, month, day)

    def return_organised_stac_item_path(self, product_item: ProductItem):
        """
        Returns relative path in standard organised format for stac item with defined info

        :param product_info: stac item defining info, including ``"product_name"`` and ``"datetime"``
        :return: stac item path
        """
        start_time = product_item.start_time
        day = start_time.strftime("%d")
        month = start_time.strftime("%m")
        year = start_time.strftime("%Y")

        return os.path.join("stac", "items", year, month, day)
