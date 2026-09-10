"""Client-side query matching for offline (archive-backed) handlers.

An online handler pushes the query filters (collection, time range, footprint,
platform, cloud cover) to the remote catalogue and trusts what comes back. An
offline handler has to apply the same filters itself, to every
:py:class:`~scrappi.product.ProductItem` it reconstructs from the archive.

:py:class:`CompiledQuery` is that filter. Parse the query once
(:py:func:`compile_query`), then call :py:meth:`CompiledQuery.matches` per
product -- the query geometry / datetimes are converted a single time, not once
per candidate. :py:func:`product_matches_query` is the one-shot convenience form.

Query shape -- the same dict the online ``perform_query`` handlers accept:

- ``collection`` (str) or ``collections`` (str | list[str]) -- product collection must be one of them
- ``start_time`` / ``stop_time`` -- product's ``[start, stop]`` must overlap this window
- ``geom`` -- WKT / shapely / ``{latitude_minimum, ...}`` bbox; product footprint must intersect
- ``platform`` -- exact match against ``ProductItem.platform`` when given
- ``cloud_cover_max`` -- ``ProductItem.cloud_fraction`` must be <= this when given
  (a NaN / unknown cloud fraction is *kept* -- see
  :py:meth:`scrappi.api.eodag.EODAGCallHandler.perform_query`'s -1 handling)

A filter absent from the query is not applied; an empty query matches everything.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Any, List, Optional

from scrappi.product import ProductItem
from scrappi.utils.utils import convert_datetime, convert_geom_shapely

__all__ = ["CompiledQuery", "compile_query", "product_matches_query", "query_collections"]


def query_collections(query: dict) -> List[str]:
    """The collection ids a query filters on -- ``collection`` (one) or
    ``collections`` (one or many). Empty list means "no collection filter"."""
    if query.get("collection") is not None:
        return [query["collection"]]
    cols = query.get("collections")
    if cols is None:
        return []
    return list(cols) if isinstance(cols, (list, tuple, set)) else [cols]


def _as_datetime(value: Any) -> Optional[dt.datetime]:
    if value in (None, ""):
        return None
    try:
        return convert_datetime(value)
    except Exception:
        return None


@dataclass(frozen=True)
class CompiledQuery:
    """A query dict with its geometry / datetimes parsed once. Build with
    :py:func:`compile_query`, then :py:meth:`matches` each product."""

    collections: frozenset
    start_time: Optional[dt.datetime]
    stop_time: Optional[dt.datetime]
    geom: Any  # shapely geometry, or None
    platform: Optional[str]
    cloud_cover_max: Optional[float]

    def matches(self, product: ProductItem) -> bool:
        """Whether *product* satisfies every filter this query carries."""
        if self.collections and getattr(product, "collection", None) not in self.collections:
            return False

        # time: product [start, stop] must overlap [query start, query stop]
        p_start = _as_datetime(getattr(product, "start_time", None))
        p_stop = _as_datetime(getattr(product, "stop_time", None)) or p_start
        if self.stop_time is not None and p_start is not None and p_start > self.stop_time:
            return False
        if self.start_time is not None and p_stop is not None and p_stop < self.start_time:
            return False

        # footprint: product geometry must intersect the query geometry
        if self.geom is not None:
            p_geom = getattr(product, "geometry", None)
            try:
                if p_geom is not None and not self.geom.intersects(p_geom):
                    return False
            except Exception:
                pass  # a geometry we can't compare shouldn't silently drop the product

        if self.platform is not None and getattr(product, "platform", None) != self.platform:
            return False

        if self.cloud_cover_max is not None:
            cf = getattr(product, "cloud_fraction", None)
            known = cf is not None and not (isinstance(cf, float) and math.isnan(cf))
            if known and cf > self.cloud_cover_max:
                return False

        return True


def compile_query(query: dict) -> CompiledQuery:
    """Parse *query* into a :py:class:`CompiledQuery` (geometry and datetimes
    converted once)."""
    geom = None
    if query.get("geom") is not None:
        try:
            geom = convert_geom_shapely(query["geom"])
        except Exception:
            geom = None
    return CompiledQuery(
        collections=frozenset(query_collections(query)),
        start_time=_as_datetime(query.get("start_time")),
        stop_time=_as_datetime(query.get("stop_time")),
        geom=geom,
        platform=query.get("platform"),
        cloud_cover_max=query.get("cloud_cover_max"),
    )


def product_matches_query(product: ProductItem, query: dict) -> bool:
    """One-shot :py:meth:`CompiledQuery.matches` -- use :py:func:`compile_query`
    once and reuse it when filtering many products."""
    return compile_query(query).matches(product)
