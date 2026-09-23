"""T-drive temporary filesystem adapter.

`TdriveTempFileSystem` is a variant of `TdriveFileSystem` configured to point
to a temporary area on T-drive. It sets context flags appropriate for a
writable archive where files are organised by collection/date, and shares
`STACFileSystem`'s "data/"-prefixed layout so a product moved between the
main and temp T-drive archives (see `ProductItem.move_product`) keeps the
same relative structure.
"""

import os
from scrappi.fs.stacfilesystem import STACFileSystem
from scrappi import ScrappiContext
import socket

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk>",
]
__all__ = ["TdriveTempFileSystem"]


class TdriveTempFileSystem(STACFileSystem):
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
        super().__init__(path=path, path_stac=path, context=context, organise_data=True, read_only=False)
