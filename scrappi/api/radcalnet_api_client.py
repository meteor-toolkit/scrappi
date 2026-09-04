#!/usr/bin/env python3
# -------------------------------------------------------------------
# RadCalNet api client
# -------------------------------------------------------------------

"""RadCalNet API client handlers for scrappi.

Provides `RadcalnetCallHandler` and `RadcalnetOfflineCallHandler` to search
and retrieve in-situ RadCalNet products. The online handler uses RadCalNet's
JSON API with basic auth, while the offline handler resolves files from a
local archive.
"""

import os
import platform
import datetime as dt
import requests
from shapely.geometry import Polygon
from typing import Dict, Optional, Any, Tuple, Union, List
import warnings
import numpy as np
import socket
from processor_tools import Context

from scrappi import ScrappiContext
from scrappi.api.insitubase import InSituCallHandler, InSituOfflineCallHandler
from scrappi.fs.stacfilesystem import STACFileSystem
from scrappi.product import ProductItemSet, ProductItem
from scrappi.utils.utils import generate_bounding_lat_lon, convert_geom_shapely

__author__ = [
    "Ashley James Ramsay <ashley.ramsay@npl.co.uk",
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
]
__all__ = ["RadcalnetCallHandler", "RadcalnetOfflineCallHandler"]

# RadCalNet collection IDs, shared by both the online and offline handlers (identical
# set -- the offline archive is a local mirror of the same two product types).
RCN_COLLECTIONS = ["RCN_TOA", "RCN_BOA"]

# Default per-request timeout (seconds) for calls to the online RadCalNet API -- a
# scalar applies to both the connect and each read. Without it a request to an
# unresponsive server (e.g. for a site the portal doesn't host but which a user has
# added via context["RadCalNet"]["site_definitions"]) hangs the whole run forever with
# no way to Ctrl-C out. Override per run with context["request_timeout"].
DEFAULT_REQUEST_TIMEOUT_S = 60

# Built-in RadCalNet site coordinates/ROI, module-level so both RadcalnetCallHandler and
# RadcalnetOfflineCallHandler resolve the same starting point (see
# _resolve_site_definitions) -- kept as RadcalnetCallHandler.DEFAULT_SITE_DEFINITIONS
# below too, unchanged, since external code (e.g. eomatch's own report scripts) reads
# that class attribute directly.
_RCN_BUILTIN_SITE_DEFINITIONS: Dict[str, Dict[str, float]] = {
    "GONA": {
        "latitude": -23.600201,
        "longitude": 15.119556,
        "default_roi": 250,
    },
    "BTCN": {"latitude": 40.851307, "longitude": 109.62922, "default_roi": 5},
    "BSCN": {"latitude": 40.8658, "longitude": 109.6155, "default_roi": 150},
    "LCFR": {"latitude": 43.558889, "longitude": 4.864167, "default_roi": 30},
    "RVUS": {
        "latitude": 38.497,
        "longitude": -115.690,
        "default_roi": 500,
    },  # default_roi values are 1/2 side len
}


def _resolve_site_definitions(context: ScrappiContext) -> Dict[str, Dict[str, float]]:
    """Merge :py:data:`_RCN_BUILTIN_SITE_DEFINITIONS` with any user-supplied entries
    under ``context["RadCalNet"]["site_definitions"]``.

    Lets a site whose data isn't (yet, or ever) available through RadCalNet's own
    online portal -- e.g. a newer site whose files a user only has saved locally --
    be registered (latitude/longitude/default_roi) without a scrappi code change.
    Both :py:class:`RadcalnetCallHandler` and :py:class:`RadcalnetOfflineCallHandler`
    call this at construction time, so they agree on where a site is regardless of
    which one actually ends up serving a query for it (see
    :py:meth:`~scrappi.api.insitubase.InSituCallHandler.get_roi_shapely`, which is
    resolved from whichever handler happens to be asked first).

    A user-supplied entry overrides the built-in one for the same site code entirely
    (not merged field-by-field) -- same convention as
    :py:meth:`RadcalnetCallHandler.set_default_site_definitions`.

    :param context: :py:class:`~scrappi.ScrappiContext` to read overrides from.
    :return: site code -> ``{"latitude", "longitude", "default_roi"}`` dict -- a
        fresh copy per call, safe for the caller to further mutate without affecting
        :py:data:`_RCN_BUILTIN_SITE_DEFINITIONS` or any other instance.
    """
    definitions = {site: dict(defn) for site, defn in _RCN_BUILTIN_SITE_DEFINITIONS.items()}
    radcalnet_config = context["RadCalNet"] if context and context.get("RadCalNet") else {}
    user_definitions = radcalnet_config.get("site_definitions") if radcalnet_config else None
    if user_definitions:
        for site, definition in user_definitions.items():
            definitions[site] = dict(definition)
    return definitions


def _build_default_geometries(site_definitions: Dict[str, Dict[str, float]]) -> Dict[str, Polygon]:
    """Convert *site_definitions* (lat/lon/default_roi per site) into ROI polygons.

    Shared by :py:meth:`RadcalnetCallHandler._set_Polygons` and
    :py:class:`RadcalnetOfflineCallHandler`'s own construction.

    :param site_definitions: site code -> ``{"latitude", "longitude", "default_roi"}``.
    :return: site code -> ROI :py:class:`~shapely.geometry.Polygon`.
    """
    return {
        site: convert_geom_shapely(
            generate_bounding_lat_lon(definition["latitude"], definition["longitude"], definition["default_roi"])
        )
        for site, definition in site_definitions.items()
    }


def _parse_rcn_filename(filename: str) -> Tuple[str, int, int, str]:
    """Split an RCN filename into site+instrument, year, day of year, and version.

    Shared by :py:meth:`RadcalnetCallHandler.parse_name` and
    :py:meth:`RadcalnetOfflineCallHandler.perform_query`.

    :param filename: name of RCN file, e.g. ``"GONA01_2022_291_v04.09.output"``.
    :return: ``(site_instrument, year, doy, version)``.
    """
    site_instrument, year, doy, version = filename.split("_")
    return site_instrument, int(year), int(doy), version


def _file_matches_collection(filename: str, collection: str) -> bool:
    """Whether *filename*'s TOA/BOA suffix matches the requested *collection*.

    RadCalNet delivers two files per site and day: ``*.input`` carries the measured
    **surface (bottom-of-atmosphere)** reflectance and atmospheric state, and
    ``*.output`` the **top-of-atmosphere** reflectance modelled by propagating that
    state upward. So an ``RCN_TOA`` query wants the ``.output`` files and ``RCN_BOA``
    wants the ``.input`` files (matching :py:mod:`eoio`'s own RadCalNet reader, which
    labels ``.input`` "Bottom of Atmosphere" and ``.output`` "Top of Atmosphere"). A
    *collection* naming neither -- the bare site id -- matches both.

    Shared by the online :py:meth:`RadcalnetCallHandler.get_files_list` and the offline
    :py:meth:`RadcalnetOfflineCallHandler.perform_query` so the two can never disagree
    on the mapping.

    :param filename: an RCN filename, e.g. ``"GONA01_2022_291_v04.09.output"``.
    :param collection: the queried collection id, e.g. ``"RCN_TOA"``/``"RCN_BOA"``.
    :return: ``True`` if *filename* belongs in *collection*.
    """
    if "TOA" in collection:
        return filename.endswith(".output")
    if "BOA" in collection:
        return filename.endswith(".input")
    return True


def _check_date_in_range(year: int, doy: int, date1: dt.date, date2: dt.date) -> bool:
    """
    Function to check whether date of file is between the query dates.

    Shared by :py:meth:`RadcalnetCallHandler.check_date_in_range` and
    :py:meth:`RadcalnetOfflineCallHandler.perform_query`.

    :param year: year of RCN file
    :param doy: day of year of RCN file (1-indexed, i.e. 1 Jan = 1 -- matches
        the convention RadCalNet's own filenames use, and how ``perform_query``
        reconstructs a file's date via ``datetime(year, 1, 1) + timedelta(days=doy - 1)``)
    :param date1: start datetime in query
    :param date2: stop datetime in query
    :return: boolean indicated whether date is in query range or not
    """
    # Handle offset-aware datetimes by creating baselines with matching tzinfo
    tz1 = getattr(date1, "tzinfo", None)
    tz2 = getattr(date2, "tzinfo", None)
    baseline1 = dt.datetime(date1.year, 1, 1, 0, 0, tzinfo=tz1)
    baseline2 = dt.datetime(date2.year, 1, 1, 0, 0, tzinfo=tz2)
    # +1: (date - baseline).days counts full days elapsed since 1 Jan 00:00, which is
    # 0-indexed (1 Jan itself = 0) -- doy above is 1-indexed, so without this offset
    # every comparison below is silently shifted a day early, matching a file from the
    # day before the query window against a same-day (or any) query.
    doy1: int = (date1 - baseline1).days + 1
    doy2: int = (date2 - baseline2).days + 1

    if date1.year == date2.year:
        if year == date1.year and doy1 <= doy <= doy2:
            return True
        return False

    elif date1.year == year and doy1 <= doy:
        return True

    elif date2.year == year and doy <= doy2:
        return True

    elif date1.year < year < date2.year:
        return True

    else:
        return False


def _daylight_window_hours_for_site(site_definitions: Dict[str, Dict[str, float]], site: str) -> Tuple[float, float]:
    """Return *site*'s approximate daylight recording window as ``(start_hour, stop_hour)``.

    Shared by :py:meth:`RadcalnetCallHandler._daylight_window_hours` and
    :py:meth:`RadcalnetOfflineCallHandler.perform_query`; see the former's own
    docstring for the full rationale (approximated as local solar noon +/- 3 hours).

    :param site_definitions: site code -> ``{"latitude", "longitude", "default_roi"}``,
        e.g. an instance's own ``self.DEFAULT_SITE_DEFINITIONS``.
    :param site: RadCalNet site identifier, e.g. ``"GONA"``.
    :return: ``(start_hour, stop_hour)`` as floats, relative to local midnight on the
        file's own date -- may be negative or exceed 24, see the caller's own docstring.
    """
    longitude = site_definitions[site]["longitude"]
    solar_noon_utc = 12.0 - longitude / 15.0
    return solar_noon_utc - 3.0, solar_noon_utc + 3.0


class RadcalnetCallHandler(InSituCallHandler):
    """Handler for RadCalNet online API.

    Credentials may be provided via the scrappi context under the
    ``RadCalNet.credentials`` mapping or read from the environment variables
    ``RADCALNET_USERNAME`` and ``RADCALNET_REMOVED_PASSWORD``.
    """

    url_base: str = "https://www.radcalnet.org/api/json/"
    # Unchanged, same dict object as _RCN_BUILTIN_SITE_DEFINITIONS -- kept as a class
    # attribute since external code (e.g. eomatch's own report scripts) reads it
    # directly off the class, not an instance. A given instance's own site registry
    # (self.DEFAULT_SITE_DEFINITIONS, set in __init__) may additionally include
    # config-supplied sites -- see _resolve_site_definitions -- without affecting this.
    DEFAULT_SITE_DEFINITIONS: Dict[str, Dict[str, float]] = _RCN_BUILTIN_SITE_DEFINITIONS

    COLLECTIONS = RCN_COLLECTIONS

    name = "radcalnet"

    def __init__(
        self,
        context: Optional[Union[str, List, Context]] = None,
    ):
        if not isinstance(context, ScrappiContext):
            # The declared param type (str | List | Context) is a codebase-wide
            # convention (see e.g. InSituCallHandler.__init__, HYPERNETSCallHandler)
            # that ScrappiContext.__init__ itself doesn't accept (dict | str | None
            # only) -- unlike those other call sites, this class needs a real
            # ScrappiContext constructed *before* super().__init__() so
            # _resolve_site_definitions can index into it below.
            context = ScrappiContext(context)  # type: ignore[arg-type]

        # Instance-level site registry (built-ins + any config-supplied additions, e.g.
        # a newer site not yet on RadCalNet's own online portal -- see
        # _resolve_site_definitions) -- shadows the class attribute above for this
        # instance only, so RadcalnetCallHandler.DEFAULT_SITE_DEFINITIONS (accessed on
        # the class itself) is unaffected.
        self.DEFAULT_SITE_DEFINITIONS = _resolve_site_definitions(context)
        self._default_geometries = _build_default_geometries(self.DEFAULT_SITE_DEFINITIONS)
        super(RadcalnetCallHandler, self).__init__(
            context, self._default_geometries
        )  # Runs the init that is in the base class

        credentials = self.context["RadCalNet"]["credentials"]
        if credentials:
            try:
                # set environment variables (when credentials provided)
                os.environ["RADCALNET_USERNAME"] = credentials["username"]
                os.environ["RADCALNET_REMOVED_PASSWORD"] = credentials["password"]
            except Exception:
                warnings.warn("Provided RADCALNET credentials could not be set in environment variables.")
            self.session = requests.session()
            self.session.auth = (credentials["username"], credentials["password"])

        else:
            try:
                # retrieve credentials from environment variables (if no credentials provided)
                username = os.environ["RADCALNET_USERNAME"]
                password = os.environ["RADCALNET_REMOVED_PASSWORD"]
            except KeyError:
                raise ValueError("No credentials found to initialise api.")
            else:
                # initialise api for search and download
                self.session = requests.session()
                self.session.auth = (username, password)

    def list_collections(self, fetch_update: Optional[bool] = False) -> List[str]:
        """
        Function to extract collection identifiers

        :param fetch_update: unused; included for API compatibility
        :return: list of collection identifiers
        """
        return self.COLLECTIONS

    def list_sites(self) -> List[str]:
        """Return the known RadCalNet site identifiers.

        :return: iterable of site identifiers (e.g. 'GONA', 'BTCN')
        """
        return list(self.DEFAULT_SITE_DEFINITIONS.keys())

    def perform_query(
        self,
        query: dict,
    ) -> ProductItemSet:
        """
        Return ProductItemSet containing ProductItems that satisfy query

        :param query: catalogue query
        :returns: ProductItemSet
        """
        if "platform" in query.keys() and "site" not in query.keys():
            query["site"] = query.pop("platform")

        date1 = self._get_datetime(query["start_time"])
        date2 = self._get_datetime(query["stop_time"])

        if date1 > date2:
            warnings.warn("the query stop_time was after the start_time")
            return ProductItemSet()

        filelist = self.get_files_list(query["site"], query["collection"], date1, date2)

        product_list = []

        for filename in filelist:
            site_instrument, year, doy, version = self.parse_name(filename)
            site = site_instrument[0:4]
            geom = self._default_geometries[site]  # get default geometry for site as Polygon
            start_hour, stop_hour = self._daylight_window_hours(site)
            product_list.append(
                ProductItem(
                    constellation="RadCalNet",
                    platform=site,
                    collection=query["collection"],
                    id=filename,
                    geometry=geom,
                    start_time=dt.datetime(year, 1, 1) + dt.timedelta(days=doy - 1, hours=start_hour),
                    stop_time=dt.datetime(year, 1, 1) + dt.timedelta(days=doy - 1, hours=stop_hour),
                    url="",
                    quicklook="",
                    api="radcalnet",
                    context=self.context,
                )
            )

        return ProductItemSet(product_list)

    def _daylight_window_hours(self, site: str) -> tuple:
        """Return this site's approximate daylight recording window as (start_hour, stop_hour).

        RadCalNet only records meaningful reflectance data during daylight,
        so each site's file only covers a window around its own local solar
        noon -- not a fixed UTC clock window, since that shifts with
        longitude (e.g. RVUS, at 115.69 degW, has its daylight window many
        hours later in UTC than GONA, at 15.12 degE). Approximated as local
        solar noon +/- 3 hours (local solar time offset from UTC =
        longitude / 15 deg-per-hour) -- this matches the site whose window
        this was originally hardcoded from (GONA: solar noon ~10:59 UTC,
        window ~08:00-14:00 UTC) almost exactly.

        Returned hours are relative to local midnight on the file's own date
        and may be negative or exceed 24 for sites whose window straddles a
        UTC day boundary -- ``timedelta(hours=...)`` normalises this
        correctly when added to a ``datetime``, so callers don't need to
        handle the wraparound themselves.

        :param site: RadCalNet site identifier, e.g. ``"GONA"``.
        :return: ``(start_hour, stop_hour)`` as floats.
        """
        return _daylight_window_hours_for_site(self.DEFAULT_SITE_DEFINITIONS, site)

    def check_date_in_range(self, year: int, doy: int, date1: dt.date, date2: dt.date) -> bool:
        """
        Function to check whether date of file is between the query dates.

        :param year: year of RCN file
        :param doy: day of year of RCN file (1-indexed, i.e. 1 Jan = 1 -- matches
            the convention RadCalNet's own filenames use, and how ``perform_query``
            reconstructs a file's date via ``datetime(year, 1, 1) + timedelta(days=doy - 1)``)
        :param date1: start datetime in query
        :param date2: stop datetime in query
        :return: boolean indicated whether date is in query range or not
        """
        return _check_date_in_range(year, doy, date1, date2)

    def return_info(self, products) -> Optional[list]:
        """
        Return product info in common format for catalogue product(s)

        :param products: catalogue query
        :returns: list of product info as dictionary
        """
        raise NotImplementedError("not currently available for rcn files")

    def download_metadata(self, product, path: Optional[Union[str, Any]] = None) -> None:
        """
        Download catalogue product(s) metadata at defined URL to local path

        :param product: search result from a product query
        :param path: local path to write metadata to
        """
        # No metadata can be downloaded for rcn products via available api
        # metadata is included in the rcn file instead
        raise NotImplementedError("not currently available for rcn files")

    def download_file(
        self, prod: Union[str, ProductItem], dest: Optional[Union[str, Any]] = None
    ) -> Optional[Union[list, str]]:
        """
        Download the file at URL into dest using class credentials for basic auth
        :param prod: rcn ProductItem
        :param dest: destination folder for downloaded file
        """
        if not isinstance(prod, ProductItem):
            raise TypeError("prod must be a ProductItem for RadcalnetCallHandler.download_file")
        if dest is None:
            raise ValueError("dest must be provided")
        dest_str = str(dest)
        filename = prod.id
        site = prod.platform
        url = self.url_base + site + "/data/" + filename
        if not os.path.exists(os.path.dirname(dest_str)):
            os.makedirs(os.path.dirname(dest_str))
        timeout = self.context.get("request_timeout", DEFAULT_REQUEST_TIMEOUT_S)
        with self.session.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            with open(dest_str, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return os.path.join(dest_str, os.path.basename(url))

    def get_files_list(self, site: str, collection: str, start_date: dt.date, end_date: dt.date) -> list:
        """
        generates a list of files between two dates
         :param site: name of rcn site: [BTCN, BSCN, GHNA, GONA, RVUS, LCFR]
         :param collection: name of collection (<site>, <site>_BOA or <site>_TOA)
         :param start_date: start date of acquisitions
         :param end_date: end date of acquisitions
        """

        if site not in self.sites:
            raise ValueError("site {} unknown. Valid sites are {}".format(site, ", ".join(self.sites)))
        if start_date > end_date:
            return []
        url = self.url_base + site + "/data/"
        # get the list of all files for the site
        r = self.session.get(url, timeout=self.context.get("request_timeout", DEFAULT_REQUEST_TIMEOUT_S))
        r.raise_for_status()
        filelist = [file["name"] for file in r.json()]

        mask = np.zeros(len(filelist))
        for ifile, filename in enumerate(filelist):
            if not _file_matches_collection(filename, collection):
                mask[ifile] = 1

            site_instrument, year, doy, version = self.parse_name(filename)
            if not self.check_date_in_range(year, doy, start_date, end_date):
                mask[ifile] = 1

        return [filelist[i] for i in range(len(filelist)) if mask[i] == 0]

    @staticmethod
    def parse_name(filename: str) -> tuple[str, int, int, str]:
        """
        split rcn filename into site, year, day of year and version number
        :param filename: name of rcn file
        """
        return _parse_rcn_filename(filename)

    def set_default_site_definitions(self, ROI: Dict[str, Union[int, float]]) -> None:
        """
        :param ROI: dictionary ROIs per site
        """
        for site in self.DEFAULT_SITE_DEFINITIONS:
            if site in ROI:
                self.DEFAULT_SITE_DEFINITIONS[site]["default_roi"] = ROI[site]

        self._set_Polygons()

    def _set_Polygons(self) -> None:
        """
        convert site lat/lon and ROI into Polygons

        Updates ``self._default_geometries`` in place (rather than reassigning it)
        so it stays the same object ``self.roi_dict`` was set to in ``__init__`` --
        a caller updating an ROI post-construction via
        :py:meth:`set_default_site_definitions` (which calls this) needs
        :py:meth:`~scrappi.api.insitubase.InSituCallHandler.get_roi_shapely` (reading
        ``self.roi_dict``) to see the change too, not just ``self._default_geometries``
        directly.
        """
        if not hasattr(self, "_default_geometries"):
            self._default_geometries = {}
        self._default_geometries.clear()
        self._default_geometries.update(_build_default_geometries(self.DEFAULT_SITE_DEFINITIONS))


def _default_offline_archive_path() -> str:
    """Hardcoded fallback RadCalNet offline archive location, used when neither
    :py:class:`RadcalnetOfflineCallHandler`'s own *archive_path* constructor argument
    nor ``context["RadCalNet"]["offline_archive_path"]`` is set.

    :return: absolute path to the default archive location for the current platform/host.
    """
    if platform.system() == "Linux":
        if socket.gethostname() == "eoserver.npl.co.uk":
            return os.path.abspath(os.path.join(r"/home", "data", "insitu", "radcalnet", "archive"))
        return os.path.abspath(os.path.join(r"/mnt", "t", "data", "insitu", "radcalnet", "archive"))
    return os.path.abspath(
        os.path.join(r"T:\ECO", "EOServer", "data", "insitu", "radcalnet", "archive")
    )  # r"\\eoserver", "home", "data", "insitu", "radcalnet", "archive"


def _archive_filesystem(dirpath: str, context: ScrappiContext) -> STACFileSystem:
    """A flat-layout :py:class:`~scrappi.fs.stacfilesystem.STACFileSystem` pinned to
    *dirpath* -- the directory a RadCalNet archive file actually sits in.

    Used as the per-product filesystem in
    :py:meth:`RadcalnetOfflineCallHandler.perform_query`. STACFileSystem (rather than a
    plain LocalFileSystem) so :py:meth:`~scrappi.product.ProductItem.to_stac_item` --
    called when the matchup is added to a catalogue -- has ``return_stac_item_path``.
    ``flat=True`` disables both the ``<root>/data`` + ``<root>/stac`` subdivision and
    the organised constellation/platform/date tree, so the file resolves at
    ``<dirpath>/<id>`` regardless of how the archive itself is laid out.
    """
    return STACFileSystem(path=dirpath, context=context, flat=True)


class RadcalnetOfflineCallHandler(InSituOfflineCallHandler):
    """
    Offline API handler for RadCalNet data.

    Resolves RadCalNet in-situ products from a local archive of the same kind of files
    the online API (:py:class:`RadcalnetCallHandler`) serves, rather than the RadCalNet
    web API -- for a site whose data isn't (yet, or ever) published on RadCalNet's own
    online portal but that a user has saved locally, or simply as an offline fallback.
    Exposes the same :py:meth:`perform_query` interface (same query shape, same
    :py:class:`~scrappi.product.ProductItemSet` return type) as the online handler, so
    it's a drop-in addition to the same collection's candidate-API list -- see
    :py:func:`scrappi.get_api_name`, whose ``all_apis=True`` list every caller that
    fans a query out across candidate APIs (e.g.
    ``eomatch._scrappi_cache.call_with_api_fallback``) already tries in turn, stopping
    at the first to return a non-empty result. Registered under ``"radcalnet_offline"``
    (see :py:mod:`scrappi.api.factory`), listed after ``"radcalnet"`` so the online
    portal is always preferred when it actually has the data.

    Archive layout: any directory tree under ``archive_path``, searched recursively --
    file *location* doesn't matter, only the filename itself (the same
    ``<site><instrument>_<year>_<doy>_<version>`` convention
    :py:meth:`RadcalnetCallHandler.parse_name`/``get_files_list`` parse, e.g.
    ``GONA01_2022_291_v04.09.output``) -- so an archive mirroring the online API's own
    ``{site}/data/{filename}`` layout, a flat directory, or anything in between all
    work unchanged. A file that doesn't match this convention is silently skipped (not
    every file under *archive_path* is necessarily a RadCalNet product -- e.g.
    checksums, readme files).

    :param context: :py:class:`~scrappi.ScrappiContext`; ``context["RadCalNet"]``
        supplies ``site_definitions`` (see :py:func:`_resolve_site_definitions`) and
        ``offline_archive_path`` (see *archive_path* below).
    :param archive_path: root directory to search for RadCalNet files. Falls back to
        ``context["RadCalNet"]["offline_archive_path"]`` if not given, then to
        :py:func:`_default_offline_archive_path` (a hardcoded NPL-infrastructure
        default) if that's unset too.
    """

    name = "radcalnet_offline"
    COLLECTIONS = RCN_COLLECTIONS
    #: OfflineArchiveHandler reads the archive root from here when it isn't passed
    #: to __init__: context["RadCalNet"]["offline_archive_path"].
    ARCHIVE_PATH_CONTEXT_KEYS = ("RadCalNet", "offline_archive_path")

    def __init__(
        self,
        context: Optional[Union[str, List, Context]] = None,
        archive_path: Optional[str] = None,
    ):
        if not isinstance(context, ScrappiContext):
            # See RadcalnetCallHandler.__init__'s own comment on this same pattern.
            context = ScrappiContext(context)  # type: ignore[arg-type]

        # Same instance-level, config-mergeable site registry as RadcalnetCallHandler
        # (see _resolve_site_definitions) -- a site only ever available offline still
        # needs a registered ROI for get_roi_shapely() to resolve it.
        self.DEFAULT_SITE_DEFINITIONS = _resolve_site_definitions(context)
        self._default_geometries = _build_default_geometries(self.DEFAULT_SITE_DEFINITIONS)
        # OfflineArchiveHandler resolves self.archive_path (arg -> context ->
        # _default_archive_path) and provides download_product / _archive_path_for;
        # InSituCallHandler takes the roi_dict. No context mutation for organise_data
        # -- each per-product filesystem is built flat in perform_query.
        super().__init__(context, roi_dict=self._default_geometries, archive_path=archive_path)

    @staticmethod
    def _default_archive_path() -> str:
        return _default_offline_archive_path()

    def list_collections(self, fetch_update: Optional[bool] = False) -> List[str]:
        """
        Function to extract collection identifiers

        :param fetch_update: unused; included for API compatibility
        :return: list of collection identifiers
        """
        return list(self.COLLECTIONS)

    def perform_query(self, query: dict) -> ProductItemSet:
        """
        Return ProductItemSet of local-archive products that satisfy *query*.

        Recursively scans :py:attr:`archive_path` for RadCalNet-named files (see
        :py:func:`_parse_rcn_filename`), keeping only those for the requested site,
        matching TOA/BOA suffix, and within the requested date range -- the same three
        filters :py:meth:`RadcalnetCallHandler.get_files_list` applies to the online
        API's own file listing. Each match becomes a
        :py:class:`~scrappi.product.ProductItem` whose own
        :py:class:`~scrappi.fs.stacfilesystem.STACFileSystem` points directly at the
        file's containing directory (flat layout -- its ``data_root`` is that directory
        itself, not a ``data/`` subdir), so :py:meth:`download_product`
        (:py:meth:`~scrappi.api.insitubase.InSituOfflineCallHandler.download_file`)
        resolves it without ever attempting a network fetch, and
        :py:meth:`~scrappi.product.ProductItem.to_stac_item` (called when the matchup is
        added to a catalogue) can resolve the STAC item path.

        :param query: catalogue query -- same shape as
            :py:meth:`RadcalnetCallHandler.perform_query` accepts (``"site"`` or
            ``"platform"``, ``"collection"``, ``"start_time"``, ``"stop_time"``).
        :returns: ProductItemSet of matching local products (empty if *archive_path*
            doesn't exist, the site has no registered ROI, or nothing matches).
        """
        query = dict(query)
        if "platform" in query.keys() and "site" not in query.keys():
            query["site"] = query.pop("platform")

        site = query["site"]
        collection = query["collection"]
        date1 = self._get_datetime(query["start_time"])
        date2 = self._get_datetime(query["stop_time"])

        if date1 > date2:
            warnings.warn("the query stop_time was after the start_time")
            return ProductItemSet()

        if not os.path.isdir(self.archive_path):
            warnings.warn(f"RadCalNet offline archive path does not exist: {self.archive_path!r}")
            return ProductItemSet()

        geom = self._default_geometries.get(site)
        if geom is None:
            warnings.warn(
                f"site {site!r} has no registered ROI (see context['RadCalNet']['site_definitions']) "
                "-- skipping offline archive search for it"
            )
            return ProductItemSet()

        product_list = []
        for dirpath, _dirnames, filenames in os.walk(self.archive_path):
            for filename in filenames:
                try:
                    site_instrument, year, doy, _version = _parse_rcn_filename(filename)
                except ValueError:
                    continue  # not an RCN-named file (e.g. a checksum/readme) -- skip

                if site_instrument[0:4] != site:
                    continue
                if not _file_matches_collection(filename, collection):
                    continue
                if not _check_date_in_range(year, doy, date1, date2):
                    continue

                start_hour, stop_hour = _daylight_window_hours_for_site(self.DEFAULT_SITE_DEFINITIONS, site)
                product_list.append(
                    ProductItem(
                        constellation="RadCalNet",
                        platform=site,
                        collection=collection,
                        id=filename,
                        geometry=geom,
                        start_time=dt.datetime(year, 1, 1) + dt.timedelta(days=doy - 1, hours=start_hour),
                        stop_time=dt.datetime(year, 1, 1) + dt.timedelta(days=doy - 1, hours=stop_hour),
                        url="",
                        quicklook="",
                        api=self,
                        context=self.context,
                        filesystem=_archive_filesystem(dirpath, self.context),
                    )
                )

        return ProductItemSet(product_list)

    # download_product / _archive_path_for come from OfflineArchiveHandler: locate the
    # file by id under archive_path, repin product.filesystem, return the path. RCN
    # ids are exactly the filenames, so the base _archive_path_for needs no override.
