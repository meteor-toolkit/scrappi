"""Factory to obtain filesystem adapter instances.

`FSCallHandlerFactory` provides a simple mapping from short names or
filesystem paths to concrete `BaseFileSystem` subclasses. If a path exists
on disk the factory will return a `LocalFileSystem` or `STACFileSystem`
depending on context settings.
"""

from scrappi.fs.base import BaseFileSystem
from scrappi.fs.localfilesystem import LocalFileSystem
from scrappi.fs.stacfilesystem import STACFileSystem
from scrappi.fs.tdrive import TdriveFileSystem
from scrappi.fs.tdrive_temp import TdriveTempFileSystem
from scrappi.fs.jasmin import JasminFileSystem
from scrappi import ScrappiContext
import os
from typing import Optional, Union, List, Dict, Any

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]
__all__ = ["FSCallHandlerFactory"]

# API call handlers by name
# use lower case names in this dictionary (Use of capitals in interface will automatically be converted)
FS_CALL_HANDLERS = {
    "tdrive": TdriveFileSystem,
    "t-drive": TdriveFileSystem,
    "t-drive-temp": TdriveTempFileSystem,
    # "jasmin": JasminFileSystem,
}


class FSCallHandlerFactory:
    def __init__(self):
        self.fs_call_handlers = FS_CALL_HANDLERS

    def get_fs_call_handler(self, name: Union[str, BaseFileSystem], context: ScrappiContext = None) -> BaseFileSystem:
        """
        Return specified FS call handler,

        :param name: selected FS (e.g. CEDA archive)
        :param context: optional `ScrappiContext` used to configure returned handler
        :return: instance of `BaseFileSystem`
        """
        if context is None:
            context = ScrappiContext()

        if name is None:
            return TdriveFileSystem(context=context)
        elif isinstance(name, BaseFileSystem):
            return name
        elif name.lower() in self.fs_call_handlers.keys():
            return self.fs_call_handlers[name.lower()](context=context)
        elif os.path.exists(name):
            if context["fs"]["stac"]:
                return STACFileSystem(path=name, context=context)
            else:
                return LocalFileSystem(path=name, context=context)
        else:
            raise ValueError(
                "The provided filesystem name (%s) is not one of the recognised filesystems (%s) nor "
                "an existing directory." % (name, self.fs_call_handlers.keys())
            )


if __name__ == "__main__":
    pass
