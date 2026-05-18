"""T-drive temporary filesystem adapter.

`TdriveTempFileSystem` is a variant of `LocalFileSystem` configured to point
to a temporary area on T-drive. It sets context flags appropriate for a
writable archive where files are organised by collection/date.
"""

import os
import re
import csv
import datetime as dt
import requests
from typing import Optional, Union, Any, List, Tuple
from scrappi.fs.localfilesystem import LocalFileSystem
from scrappi.product import ProductItem
from scrappi import ScrappiContext
import socket

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk>",
]
__all__ = ["TdriveTempFileSystem"]


class TdriveTempFileSystem(LocalFileSystem):
    """Filesystem adapter for temporary T-drive product storage."""

    def __init__(self, context: ScrappiContext):
        if (
            socket.gethostname() == "eoserver.npl.co.uk"
            or socket.gethostname() == "lyon.npl.co.uk"
            or socket.gethostname() == "leipzig.npl.co.uk"
        ):
            path = os.path.join("/mnt/t/data/product_archive_temp")
        else:
            path = os.path.join("T:", "ECO", "EOServer", "data", "product_archive_temp")
        context["fs"]["organise_data"] = True
        context["fs"]["read_only"] = False
        super().__init__(path=path, path_stac=path, context=context)
