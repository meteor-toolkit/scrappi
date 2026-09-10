"""Client-side query matching for offline (archive-backed) handlers.

An online handler pushes the query filters (collection, time range, footprint,
platform, cloud cover) to the remote catalogue and trusts what comes back. An
offline handler has to apply the same filters itself, to every
:py:class:`~scrappi.product.ProductItem` it reconstructs from the archive.

:py:func:`product_matches_query` is that filter, in one place, so every offline
handler (and, in time, the post-search filtering the online eodag handler still
does by hand) agrees on what "matches" means.

Query shape -- the same dict the online ``perform_query`` handlers accept:

- ``collection`` (str) or ``collections`` (str | list[str]) -- required to filter on
- ``start_time`` / ``stop_time`` -- product's [start, stop] must overlap this window
- ``geom`` -- WKT / shapely / ``{latitude_minimum, ...}`` bbox; product footprint must intersect
- ``platform`` -- exact match against ``ProductItem.platform`` when given
- ``cloud_cover_max`` -- ``ProductItem.cloud_fraction`` must be <= this when given
  (a NaN / unknown cloud fraction is *kept* -- see
  :py:meth:`scrappi.api.eodag.EODAGCallHandler.perform_query`'s -1 handling)
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any, Optional

from scrappi.product import ProductItem
from scrappi.utils.utils import convert_datetime, convert_geom_shapely

__all__ = ["product_matches_query", "query_collections"]


def query_collections(query: dict) -> list:
    """The collection ids a query filters on -- ``collection`` (one) or
    ``collections`` (one or many). Empty list means "no collection filter"."""
    if query.get("collection") is not None:
        return [query["collection"]]
    cols = query.get("collections")
    if cols is None:
        return []
    return list(cols) if isinstance(cols, (list, tuple, set)) else [cols]


def _query_time_range(query: dict) -> tuple[Optional[dt.datetime], Optional[dt.datetime]]:
    start = convert_datetime(query["start_time"]) if query.get("start_time") is not None else None
    stop = convert_datetime(query["stop_time"]) if query.get("stop_time") is not None else None
    return start, stop


def _as_datetime(value: Any) -> Optional[dt.datetime]:
    if value in (None, ""):
        return None
    try:
        return convert_datetime(value)
    except Exception:
        return None


def product_matches_query(product: ProductItem, query: dict) -> bool:
    """Whether *product* satisfies every filter present in *query* (see module docstring).

    A filter that isn't in the query isn't applied. Returns ``True`` for an empty
    query.
    """
    # ---- collection ----
    wanted_collections = query_collections(query)
    if wanted_collections and product.collection not in wanted_collections:
        return False

    # ---- time range: product [start, stop] must overlap [query start, query stop] ----
    q_start, q_stop = _query_time_range(query)
    p_start = _as_datetime(getattr(product, "start_time", None))
    p_stop = _as_datetime(getattr(product, "stop_time", None)) or p_start
    if q_stop is not None and p_start is not None and p_start > q_stop:
        return False
    if q_start is not None and p_stop is not None and p_stop < q_start:
        return False

    # ---- footprint: product geometry must intersect the query geometry ----
    if query.get("geom") is not None:
        try:
            q_geom = convert_geom_shapely(query["geom"])
            p_geom = product.geometry
            if q_geom is not None and p_geom is not None and not q_geom.intersects(p_geom):
                return False
        except Exception:
            # a geometry we can't compare shouldn't silently drop the product
            pass

    # ---- platform ----
    if query.get("platform") is not None and getattr(product, "platform", None) != query["platform"]:
        return False

    # ---- cloud cover (only when the query asks and the product has a real number) ----
    cloud_max = query.get("cloud_cover_max")
    if cloud_max is not None:
        cf = getattr(product, "cloud_fraction", None)
        if cf is not None and not (isinstance(cf, float) and math.isnan(cf)) and cf > cloud_max:
            return False

    return True
