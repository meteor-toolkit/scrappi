"""Factory for API call handler classes.

Provides a simple factory, `APICallHandlerFactory`, to obtain an instance of
an API call handler by name (for example ``"eodag"`` or ``"radcalnet"``).
The factory ensures a `ScrappiContext` is passed to the handler instance.
"""

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]
__all__ = ["APICallHandlerFactory"]

from scrappi import ScrappiContext
from scrappi.api.earthaccess_api import EarthaccessCallHandler
from scrappi.api.eodag import EODAGCallHandler
from scrappi.api.hypernets import HYPERNETSOfflineCallHandler, HYPERNETSCallHandler
from scrappi.api.radcalnet_api_client import RadcalnetCallHandler
from scrappi.api.base import BaseAPICallHandler
from scrappi.api.stac_api import STACAPICallHandler

# API call handlers by name
API_CALL_HANDLERS = {
    "eodag": EODAGCallHandler,
    "earthaccess": EarthaccessCallHandler,
    "hypernets": HYPERNETSCallHandler,
    "radcalnet": RadcalnetCallHandler,
    "stac": STACAPICallHandler,
}


class APICallHandlerFactory:
    def __init__(self):
        self.api_call_handlers = API_CALL_HANDLERS

    def get_api_call_handler(self, name: str, context: ScrappiContext = None):
        """
        Return specified API call handler

        :param name: selected API (e.g. ``"eodag"``)
        :param context: optional `ScrappiContext` to pass to the handler
        :return: instance of a `BaseAPICallHandler` subclass
        """
        if context is None:
            context = ScrappiContext()

        if isinstance(name, BaseAPICallHandler):
            return name

        elif ":" in name:
            name_parts = name.split(":")
            if name_parts[0] == "eodag":
                context["api"]["preferred_provider"] = name_parts[1]
                return self.api_call_handlers[name_parts[0].lower()](context=context)
            else:
                raise IOError(
                    "only eodag allows to optionally include preffered provider using a `:'. This is not relevant for other api's.  "
                    "For eodag the preferred provider can also be set in config_dict."
                )

        elif name in self.api_call_handlers.keys():
            return self.api_call_handlers[name.lower()](context=context)

        else:
            raise IOError("api name (%s) not one of the recognised apis (%s)." % (name, self.api_call_handlers.keys()))


if __name__ == "__main__":
    pass
