"""T-drive filesystem adapter.

`TdriveFileSystem` is a convenience adapter preconfigured for the T-drive
archive layout used in some deployment environments. It inherits from
`STACFileSystem` and sets sane defaults for `fs` context flags.
"""

import os
import socket

from scrappi import ScrappiContext
from scrappi.fs.stacfilesystem import STACFileSystem

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

        super().__init__(path=path, path_stac=path, context=context, organise_data=True, read_only=False)
