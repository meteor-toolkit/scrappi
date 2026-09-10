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


from typing import Dict, Optional, Union
from scrappi import ScrappiContext
from scrappi.api.eodag import EODAGCallHandler
from scrappi.api.radcalnet_api_client import RadcalnetCallHandler, RadcalnetOfflineCallHandler
from scrappi.api.base import BaseAPICallHandler
from scrappi.api.stac_api import STACAPICallHandler
from scrappi.api.aws import AWSCallHandler
from scrappi.api.satellite_offline import SatelliteOfflineCallHandler

all_api_list = [
    "eodag",
    "eodag_offline",
    "earthaccess",
    "hypernets",
    "hypernets_offline",
    "radcalnet",
    "radcalnet_offline",
    "stac",
    "eumdac",
    "aws",
]

# API call handlers by name
API_CALL_HANDLERS = {
    "eodag": EODAGCallHandler,
    # "earthaccess": EarthaccessCallHandler,  #handled separately below to allow lazy import
    # "eumdac": EUMDACCallHandler,  #handled separately below to allow lazy import
    # "hypernets": HYPERNETSCallHandler, #handled separately below to allow lazy import
    "eodag_offline": SatelliteOfflineCallHandler,
    "radcalnet": RadcalnetCallHandler,
    "radcalnet_offline": RadcalnetOfflineCallHandler,
    "stac": STACAPICallHandler,
    "aws": AWSCallHandler,
}


class APICallHandlerFactory:
    def __init__(self):
        self.api_call_handlers = API_CALL_HANDLERS
        self.all_api_list = all_api_list
        # name (e.g. "eodag", or "eodag:some_provider") -> handler instance,
        # for get_api_call_handler(..., use_cache=True) -- see its docstring.
        self._handler_cache: Dict[str, BaseAPICallHandler] = {}

    def get_api_call_handler(
        self, name: Union[str, BaseAPICallHandler], context: Optional[ScrappiContext] = None, use_cache: bool = True
    ):
        """
        Return specified API call handler

        :param name: selected API (e.g. ``"eodag"``)
        :param context: optional `ScrappiContext` to pass to the handler
        :param use_cache: if ``True`` (default), reuse a previously built handler for
            the same *name* instead of constructing a new one on every call. This
            matters most for ``"eodag"``: its handler's ``__init__`` builds a fresh
            ``eodag.EODataAccessGateway``, which reads and prunes every provider
            config on every construction -- a few hundred ms each time, dominating
            callers (e.g. ``is_insitu_collection``) that resolve a handler by name
            repeatedly. A cached handler keeps whatever *context* it was first built
            with -- pass ``use_cache=False`` (or call :py:meth:`clear_cache` first)
            if you need a handler rebuilt from a specific, possibly different,
            *context* (e.g. different credentials).
        :return: instance of a `BaseAPICallHandler` subclass
        """
        if isinstance(name, BaseAPICallHandler):
            return name

        if use_cache:
            cached = self._handler_cache.get(name)
            if cached is not None:
                return cached

        handler = self._build_api_call_handler(name, context)

        if use_cache:
            self._handler_cache[name] = handler

        return handler

    def _build_api_call_handler(self, name: str, context: Optional[ScrappiContext]) -> BaseAPICallHandler:
        """Construct a fresh handler for *name* -- the uncached part of :py:meth:`get_api_call_handler`."""
        if context is None:
            context = ScrappiContext()

        if ":" in name:
            name_parts = name.split(":")
            if name_parts[0] == "eodag":
                context["api"]["preferred_provider"] = name_parts[1]
                return self.api_call_handlers[name_parts[0].lower()](context=context)
            else:
                raise IOError(
                    "only eodag allows to optionally include preffered provider using a `:'. This is not relevant for other api's.  "
                    "For eodag the preferred provider can also be set in config_dict."
                )

        elif name.lower() == "hypernets":
            from scrappi.api.hypernets import HYPERNETSCallHandler

            return HYPERNETSCallHandler(context=context)

        elif name.lower() == "hypernets_offline":
            from scrappi.api.hypernets import HYPERNETSOfflineCallHandler

            return HYPERNETSOfflineCallHandler(context=context)

        elif name.lower() == "earthaccess":
            from scrappi.api.earthaccess_api import EarthaccessCallHandler

            return EarthaccessCallHandler(context=context)

        elif name.lower() == "eumdac":
            from scrappi.api.eumdac import EUMDACCallHandler

            return EUMDACCallHandler(context=context)

        elif name in self.api_call_handlers.keys():
            return self.api_call_handlers[name.lower()](context=context)

        else:
            raise IOError("api name (%s) not one of the recognised apis (%s)." % (name, self.api_call_handlers.keys()))

    def clear_cache(self) -> None:
        """Drop all cached handler instances (see ``get_api_call_handler``'s ``use_cache``).

        Call this after changing credentials/config for an API you've already
        resolved a handler for, so the next ``get_api_call_handler`` call
        rebuilds it from the current context instead of reusing the stale one.
        """
        self._handler_cache.clear()


if __name__ == "__main__":
    pass
