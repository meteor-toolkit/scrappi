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


from typing import Any, Dict, Optional, Tuple, Union
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
        # Cache key -> (context reference, handler instance), for
        # get_api_call_handler(..., use_cache=True) -- see its docstring. The stored
        # context reference is never read back for its own sake, only to (a) keep the
        # context object alive for as long as its handler is cached (see the identity
        # check below) and (b) let clear_cache() drop entries regardless of key shape.
        self._handler_cache: Dict[Any, Tuple[Optional[ScrappiContext], BaseAPICallHandler]] = {}

    def get_api_call_handler(
        self, name: Union[str, BaseAPICallHandler], context: Optional[ScrappiContext] = None, use_cache: bool = True
    ):
        """
        Return specified API call handler

        :param name: selected API (e.g. ``"eodag"``)
        :param context: optional `ScrappiContext` to pass to the handler
        :param use_cache: if ``True`` (default), a previously built handler may be reused
            instead of constructing a new one. ``"eodag"`` is cached by name alone,
            regardless of *context*: its ``__init__`` builds a fresh
            ``eodag.EODataAccessGateway``, which reads and prunes every provider config on
            every construction -- a few hundred ms each time -- and its per-run context
            differences (the preferred provider) are applied at query time, not
            construction. Every other handler is cheap to build and *is*
            context-sensitive (credentials, RadCalNet ``site_definitions``, an offline
            archive path, ...), so it's cached by ``(name, id(context))`` instead: a
            *different* context object always gets its own freshly built handler (so a
            context-free handler built by e.g. ``is_insitu_collection()`` -- which only
            needs to type-check ``list_collections()`` -- is never handed back to a
            later, context-aware caller), but repeated calls within one run that reuse
            the *same* context object (the common case -- one context built once and
            passed to every query) reuse one handler and its live session instead of
            rebuilding, and re-authenticating, on every single call. Pass
            ``use_cache=False`` to force a rebuild in every case.
        :return: instance of a `BaseAPICallHandler` subclass
        """
        if isinstance(name, BaseAPICallHandler):
            return name

        # eodag: cache by name alone, regardless of context (see above). Everything
        # else: cache by (name, identity of context) -- a different context object
        # always misses, but the same one reused across calls hits.
        is_eodag = name.split(":")[0].lower() == "eodag"
        cache_key = name if is_eodag else (name, id(context))

        if use_cache:
            cached = self._handler_cache.get(cache_key)
            if cached is not None:
                cached_context, handler = cached
                # For the non-eodag, identity-keyed case, id() values can be recycled
                # once an object is garbage collected -- confirm identity (not just a
                # matching id()) before trusting the hit. Storing *context* in the cache
                # entry (below) also prevents this by keeping it alive for as long as
                # its handler is cached. Always true for eodag, served regardless of
                # context by design (see above).
                if is_eodag or cached_context is context:
                    return handler

        handler = self._build_api_call_handler(name, context)

        if use_cache:
            self._handler_cache[cache_key] = (context, handler)

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
