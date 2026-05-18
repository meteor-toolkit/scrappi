"""T-drive filesystem adapter.

`TdriveFileSystem` is a convenience adapter preconfigured for the T-drive
archive layout used in some deployment environments. It inherits from
`STACFileSystem` and sets sane defaults for `fs` context flags.
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
    "Pieter De Vis <pieter.de.vis@npl.co.uk>",
]
__all__ = ["TdriveFileSystem"]


class TdriveFileSystem(STACFileSystem):
    """Filesystem adapter configured for T-drive product archives."""

    def __init__(self, context: ScrappiContext):
        if socket.gethostname().split(".")[0].lower() in [
            "eoserver",
            "leiden",
            "leipzig",
            "lyon",
        ]:
            path = os.path.join("/mnt/t/data/product_archive")
        else:
            path = os.path.join("T:\\", "ECO", "EOServer", "data", "product_archive")

        context["fs"]["organise_data"] = True
        context["fs"]["read_only"] = False
        super().__init__(path=path, path_stac=path, context=context)
