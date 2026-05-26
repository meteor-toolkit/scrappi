"""High-level scrappi interface helpers.

This module provides the user-facing convenience functions used throughout
scrappi to create API and filesystem handler instances, run queries and to
download products. The helpers bridge the `ScrappiContext` to concrete
adapter implementations.
"""

import os
import datetime as dt
import numpy as np
import warnings

import shapely
import shapely.geometry
from dateutil.parser import parse
from pyproj import Transformer
from typing import Optional, Union, List, Dict, Any
import xarray as xr
from processor_tools import Context
from processor_tools.utils.formatters import convert_datetime

from scrappi.api.factory import APICallHandlerFactory
from scrappi.fs.factory import FSCallHandlerFactory
from scrappi.fs.base import BaseFileSystem
from scrappi.utils.utils import generate_bounding_lat_lon
from scrappi.product import ProductItem, ProductItemSet
from scrappi.api.base import BaseAPICallHandler
from scrappi.api.insitubase import InSituCallHandler
from scrappi import ScrappiContext

__author__ = "Pieter De Vis <pieter.de.vis@npl.co.uk>"
__all__ = [
    "parse_queries_orbitx",
    "get_api_name",
    "make_api",
    "make_fs",
    "perform_query",
    "download_product",
    "download_product_filename",
    "download_product_scene",
    # "download_metadata",
    "make_query_with_tolerance",
    "make_query_start_stop",
    "generate_bounding_box",
    "is_insitu_collection",
    "list_collections",
    "set_credentials",
    "update_context_file",
]

platforms = {
    "S2_MSI_L1C": "Sentinel-2",
    "LANDSAT_C2L1": "Landsat-8/9",
}

Factory = APICallHandlerFactory()
FSFactory = FSCallHandlerFactory()


def parse_queries_orbitx(ds_orbitx: xr.Dataset) -> List[dict]:
    """
    Function to parse individual queries that scrappi should run from the output of orbitx

    :param ds_orbitx: orbitx dataset
    :return: list of queries
    """
    queries1 = []
    queries2 = []
    times = ds_orbitx.time.values
    lat1 = ds_orbitx.lat1.values
    lon1 = ds_orbitx.lon1.values
    lat2 = ds_orbitx.lat2.values
    lon2 = ds_orbitx.lon2.values
    i_start = 0
    indices = [0]
    for i in range(i_start, len(times)):
        if (i == len(times) - 1) or (times[i + 1] - times[i] > np.timedelta64(1, "m")):
            if i_start == i:
                query = {
                    "collection": "LANDSAT_C2L1",  # ["S2_MSI_L1C","S3_EFR","LANDSAT_C2L1"]
                    "platform": "LC08",
                    "geom": {
                        "latitude_minimum": lat1[i_start],
                        "longitude_minimum": lon1[i_start],
                        "latitude_maximum": lat1[i_start],
                        "longitude_maximum": lon1[i_start],
                    },
                    "start_time": times[i_start] - np.timedelta64(900, "s"),
                    "stop_time": times[i] + np.timedelta64(900, "s"),
                }
                queries1.append(query)
                query = {
                    "collection": "S2_MSI_L1C",  # ["S2_MSI_L1C","S3_EFR","LANDSAT_C2L1"]
                    "platform": "S2A",
                    "geom": {
                        "latitude_minimum": lat2[i_start],
                        "longitude_minimum": lon2[i_start],
                        "latitude_maximum": lat2[i_start],
                        "longitude_maximum": lon2[i_start],
                    },
                    "start_time": times[i_start] - np.timedelta64(900, "s"),
                    "stop_time": times[i] + np.timedelta64(900, "s"),
                }
                queries2.append(query)
                i_start = i + 1
                indices.append(i + 1)
            else:
                query = {
                    "collection": "LANDSAT_C2L1",  # ["S2_MSI_L1C","S3_EFR","LANDSAT_C2L1"]
                    "platform": "LC08",
                    "geom": {
                        "latitude_minimum": np.min(lat1[i_start:i]),
                        "longitude_minimum": np.min(lon1[i_start:i]),
                        "latitude_maximum": np.max(lat1[i_start:i]),
                        "longitude_maximum": np.max(lon1[i_start:i]),
                    },
                    "start_time": times[i_start] - np.timedelta64(900, "s"),
                    "stop_time": times[i] + np.timedelta64(900, "s"),
                }
                queries1.append(query)
                query = {
                    "collection": "S2_MSI_L1C",  # ["S2_MSI_L1C","S3_EFR","LANDSAT_C2L1"]
                    "platform": "S2A",
                    "geom": {
                        "latitude_minimum": np.min(lat2[i_start:i]),
                        "longitude_minimum": np.min(lon2[i_start:i]),
                        "latitude_maximum": np.max(lat2[i_start:i]),
                        "longitude_maximum": np.max(lon2[i_start:i]),
                    },
                    "start_time": times[i_start] - np.timedelta64(900, "s"),
                    "stop_time": times[i] + np.timedelta64(900, "s"),
                }
                queries2.append(query)
                i_start = i + 1
                indices.append(i + 1)

    return queries1, queries2, indices


def get_api_name(collection: str, all_apis: bool = False, context: ScrappiContext = None) -> Optional[Union[str, list]]:
    """
    Return name of API call handler capable of reading in desired satellite collection.
    If preferred_api is set in context, this is returned.
    Returns None if no suitable API found.

    :param collection: name of the satellite collection to download
    :param all_apis: whether to return all suitable APIs
    :return: name/s of API to use
    """

    if not context:
        context = ScrappiContext()

    preferred_api = ""
    if context["api"]["preferred_api"]:
        preferred_api = context["api"]["preferred_api"]

    if all_apis:
        apis = []
        for k, v in Factory.api_call_handlers.items():
            try:
                if collection in v(context=context).list_collections():
                    if all_apis is True:
                        apis.append(k)
                    else:
                        return k
            except:
                pass

        if preferred_api != "" and preferred_api in apis:
            apis.remove(preferred_api)
            apis.insert(0, preferred_api)

        return apis

    else:
        # select api based on collection if not already specified in context
        if context and context["api"]["preferred_api"]:
            if (
                collection
                in Factory.api_call_handlers[context["api"]["preferred_api"]](context=context).list_collections()
            ):
                return context["api"]["preferred_api"]

        for k, v in Factory.api_call_handlers.items():
            try:
                if collection in v(context=context).list_collections():
                    return k
            except:
                pass

        warnings.warn("No api was found for the specified collection. Returning context['api']['preferred_api'].")
        return context["api"]["preferred_api"]


def list_collections(guess: Optional[str] = None, context: ScrappiContext = None):
    """
    Return a list of accepted collection strings
    which can be used to query products

    :param context: Context object (user provided configuration values or scrappi default)

    :return: list of product types/collections
    """
    products = []
    for k, v in Factory.api_call_handlers.items():
        try:
            products.extend(list(v(context=context).list_collections()))
        except:
            warnings.warn(f"No collections identified for {k} api")

    if guess:
        return sorted([i for i in list(set(products)) if any([guess in i, guess.lower() in i, guess.upper() in i])])

    return sorted(list(set(products)))


def make_api(api: str = None, context: ScrappiContext = None):
    """
    Return specified API call handler

    :param api: name of API to use (e.g. ``"eodag"``)
    :param context: Context object (user provided configuration values or scrappi default)
    :return : reader object
    """
    if not context:
        context = ScrappiContext()
    if isinstance(api, BaseAPICallHandler):
        return api
    elif not api:
        api = context["api"]["preferred_api"]
    return Factory.get_api_call_handler(api, context)


def make_fs(fs: str = None, context: ScrappiContext = None):
    """
    Return specified file system call handler.

    If no directory specified current working directory is used.

    :param fs: name of file system to use (e.g. CEDA archive, eoserver)
    :param context: Context object (user provided configuration values or scrappi default)

    """
    if not context:
        context = ScrappiContext()
    if not fs:
        fs = context["fs"]["path"]
    return FSFactory.get_fs_call_handler(fs, context)


def perform_query(query: dict, context: ScrappiContext = None) -> ProductItemSet:
    """
    Return catalogue product url(s) that satisfy query

    :param query: catalogue query
    :param context: Context object (user provided configuration values or scrappi default)
    :return: ProductItemSet satisfying query
    """
    if not isinstance(context, ScrappiContext):
        context = ScrappiContext(context)

    # if multiple collections are provided, run query for each and combine results
    if "collections" in query.keys():
        if isinstance(query["collections"], str):
            query["collection"] = query["collections"]
        elif len(query["collections"]) == 1:
            query["collection"] = query["collections"][0]
        else:
            collections = query.pop("collections")
            query["collection"] = collections[0]
            products = perform_query(query, context)
            for icol in range(1, len(collections)):
                query["collection"] = collections[icol]
                products.append_ProductItemSet(perform_query(query, context))
            return products

    apis = get_api_name(query["collection"], context=context, all_apis=True)

    # run query for different apis until results found
    for api in apis:
        api = make_api(api, context)
        products = api.perform_query(query)
        if len(products) > 0:
            return products


def is_insitu_collection(collection: str) -> bool:
    """
    Return whether collection is an in situ collection

    :param collection: name of the satellite collection to search through
    :return: bool indicating whether collection is in situ
    """
    for k, v in Factory.api_call_handlers.items():
        try:
            api = v()
            if collection in api.list_collections():
                return isinstance(api, InSituCallHandler)
        except:
            pass
    else:
        warnings.warn(
            f"Collection {collection} not found in listed collections for any API (some are missing from list for eodag)."
        )

        return False


def set_credentials(api: str, credentials: dict, context: ScrappiContext = None):
    """
    Set credentials for a given API

    :param api: name of API to set credentials for (e.g. ``"eodag"``)
    :param credentials: dictionary of credentials to set for API
    :param context: Context object (user provided configuration values or scrappi default)
    """
    context_update = {api: {"credentials": credentials}}
    if context:
        context.update(context_update)
    else:
        context = self.update_context_file(context_update)
    return context


def update_context_file(context_update: dict):
    """
    Update context file with provided dictionary

    :param context_update: dictionary of values to update in context file
    :param context: Context object (user provided configuration values or scrappi default)
    """
    from scrappi.config import config_init

    path = os.path.join(config_init.get_config_directory(), config_init.list_config()[0])
    context = Context(config=context_update, config_init=config_init)
    context.write_config(path)
    return context


def download_product(product: Union[ProductItem, ProductItemSet], context: ScrappiContext = None):
    """
    Download catalogue product(s), provided as ProductItem or ProductItemSet, to file system path

    :param product: ProductItem or ProductItemSet to download
    :param context: Context object (user provided configuration values or scrappi default)
    :return product paths of downloaded products
    """
    if product is None:
        warnings.warn("no product was provided to download")
        return None

    if not isinstance(context, ScrappiContext):
        context = product.context

    if isinstance(product, ProductItemSet):
        return [p.download_product(context=context) for p in product]

    if isinstance(product, ProductItem):
        path, exists = product.filesystem.return_path(product, check_exists=True)

        if exists:
            print(f"{path} exists")
            return path

    apis = get_api_name(product.collection, context=context, all_apis=True)

    for api in apis:
        api = make_api(api, context=context)
        download_path = api.download_product(product)
        if download_path is not None:
            # After successful download, attempt to register the product in filesystem STAC catalogs
            try:
                # Check context setting to decide whether to auto-register
                register_flag = False
                try:
                    register_flag = bool(context["fs"]["register_stac_items"])
                except Exception:
                    register_flag = False

                if register_flag and isinstance(product, ProductItem):
                    # prefer product.filesystem; make_fs will handle strings
                    try:
                        product.register_in_filesystem_catalog(overwrite=context["fs"]["overwrite_stac_items"])
                    except Exception:
                        # fallback: try using make_fs with product.filesystem attribute
                        try:
                            fs = make_fs(product.filesystem)
                            product.register_in_filesystem_catalog(
                                filesystem=fs,
                                overwrite=context["fs"]["overwrite_stac_items"],
                            )
                        except Exception as e:
                            warnings.warn(f"Failed to register product in STAC catalog: {e}")
                # for ProductItemSet we assume individual downloads will have registered themselves
            except Exception:
                # Do not let registration errors prevent returning the download path
                pass

            return download_path


def download_product_filename(
    product: Union[str, List],
    context: ScrappiContext = None,
):
    """
    Download catalogue product(s), provided as filename string, to file system path

    :param product: filename (id field in ProductItem)
    :param context: Context object (user provided configuration values or scrappi default)

    :return product paths of downloaded products
    """
    api = context["api"]["preferred_api"]
    api = make_api(api, context=context)
    func = getattr(api, "download_product_filename", None)
    if callable(func):
        return api.download_product_filename(product, context=context)
    else:
        raise NotImplementedError("download_product_filename is not implemented for this api (%s)" % api)


def download_product_scene(
    product: Union[str, List],
    context: ScrappiContext = None,
):
    """
    Download catalogue product(s), provided as scene_id (url field in ProductItem) string, to file system path

    :param product: scene_id (url field in ProductItem)
    :param context: Context object (user provided configuration values or scrappi default)
    :return product paths of downloaded products
    """
    api = context["api"]["preferred_api"]
    api = make_api(api, context=context)
    func = getattr(api, "download_product_scene", None)
    if callable(func):
        return api.download_product_scene(product, context=context)
    else:
        raise NotImplementedError("download_product_filename is not implemented for this api (%s)" % api)


# def download_metadata(
#     products, path
# ):
#     """
#     Download catalogue product(s) metadata at defined URL to local path
#
#     :param api: name of API to use (e.g. ``"eodag"``)
#     :param products: search result from a product query
#     :param path: local path to write metadata to
#     """
#     collection = str(products.collection)
#     api = context[collection]['preferred_apis'][0]
#     api = make_api(api)
#     return api.download_metadata(products, path)


def make_query_with_tolerance(
    collection: Union[str, List],
    latitude: Union[float, int],
    longitude: Union[float, int],
    date_time: Union[dt.datetime, str],
    spatial_tolerance_deg: Optional[Union[float, int]] = None,
    spatial_tolerance_m: Optional[Union[float, int]] = None,
    temporal_tolerance_min: Optional[float] = None,
    temporal_tolerance_hours: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Make a query with a given spatial and temporal tolerance

    NB
    Only one parameter can be used for either the spatial or temporal tolerances (as
    in you cannot specify both a spatial tolerance in degrees and in meters)

    :param collection: name of the satellite collection to search through
    :param latitude: longitude of the point to search for
    :param longitude: latitude of the point to search for
    :param date_time: datetime around which to search for
    :param spatial_tolerance_deg: spatial tolerance about point in degrees
    :param spatial_tolerance_m: spatial tolerance about point in meters
    :param temporal_tolerance_min: temporal tolerance about datetime in minutes
    :param temporal_tolerance_hours: temporal tolerance about datetime in hours
    :return:
    """
    # initialise query dictionary
    if isinstance(collection, str):
        query: Dict[str, Any] = {
            "collections": [collection],
        }
    else:
        query: Dict[str, Any] = {
            "collections": collection,
        }
    # convert datetime format
    datetime = convert_datetime(date_time)

    # create datetime query value

    if temporal_tolerance_min is not None and temporal_tolerance_hours is not None:
        raise ValueError("Either temporal_tolerance_min or temporal_tolerance_hours is required, but not both.")

    else:
        if temporal_tolerance_min is not None:
            datetime_start: dt.datetime = datetime - dt.timedelta(minutes=temporal_tolerance_min)
            datetime_stop: dt.datetime = datetime + dt.timedelta(minutes=temporal_tolerance_min)

        elif temporal_tolerance_hours is not None:
            datetime_start = datetime - dt.timedelta(hours=temporal_tolerance_hours)
            datetime_stop = datetime + dt.timedelta(hours=temporal_tolerance_hours)
        else:
            raise ValueError("A temporal tolerance is required to query between two datetimes.")
        query.update(
            {
                "start_time": "%s" % datetime_start.isoformat(),
                "stop_time": "%s" % datetime_stop.isoformat(),
            }
        )

    # create geometry query value
    if spatial_tolerance_deg is not None and spatial_tolerance_m is not None:
        raise ValueError("Either a spatial_tolerance_deg or spatial_tolerance_m is required, but not both")
    else:
        if spatial_tolerance_deg is None and spatial_tolerance_m is None:
            query.update({"geom": shapely.geometry.Point(latitude, longitude)})
        else:
            if spatial_tolerance_deg is not None:
                lon_start = longitude - spatial_tolerance_deg
                lat_start = latitude - spatial_tolerance_deg
                lon_stop = longitude + spatial_tolerance_deg
                lat_stop = latitude + spatial_tolerance_deg

            else:
                lat_start, lon_start, lat_stop, lon_stop = generate_bounding_lat_lon(
                    latitude, longitude, spatial_tolerance_m
                )
            query.update({"geom": [lat_start, lon_start, lat_stop, lon_stop]})
    return query


def make_query_start_stop(
    collection: str,
    latitude_start: Union[float, int],
    longitude_start: Union[float, int],
    latitude_stop: Union[float, int],
    longitude_stop: Union[float, int],
    date_time_start: Union[dt.datetime, str],
    date_time_stop: Union[dt.datetime, str],
) -> Dict[str, Any]:
    """
    Make a query with a given region and start and end time

    :param collection: name of the satellite collection to search through
    :param latitude_start: start longitude of the region to search for
    :param longitude_start: start latitude of the region to search for
    :param latitude_stop: end longitude of the region to search for
    :param longitude_stop: end latitude of the region to search for
    :param date_time_start: start datetime of period in which to search for
    :param date_time_stop: end datetime of period in which to search for
    :return:
    """

    if isinstance(collection, str):
        collection = [collection]

    datetime_start = convert_datetime(date_time_start)
    datetime_stop = convert_datetime(date_time_stop)

    # initialise query dictionary
    query: Dict[str, Any] = {
        "collections": collection,
        "start_time": "%s" % datetime_start.isoformat(),
        "stop_time": "%s" % datetime_stop.isoformat(),
    }

    if latitude_start == latitude_stop and longitude_start == longitude_stop:
        query.update({"geom": shapely.geometry.Point(latitude_start, longitude_start)})
    else:
        query.update({"geom": [latitude_start, longitude_start, latitude_stop, longitude_stop]})

    return query


def generate_bounding_box(latitude, longitude, distance, crs="EPSG:32630") -> list:
    """
    Return list of coordinates of a square box around a point

    :param crs: Universal Transverse Mercator coordinate reference system of point
    :param latitude: latitude of point
    :param longitude: longitude of point
    :param distance: distance of point from each side of the box
    :return: list of coordinates of box
    """
    miny_wgs84, minx_wgs84, maxy_wgs84, maxx_wgs84 = generate_bounding_lat_lon(latitude, longitude, distance, crs=crs)

    bounding_box = [
        [minx_wgs84, maxy_wgs84],
        [maxx_wgs84, maxy_wgs84],
        [maxx_wgs84, miny_wgs84],
        [minx_wgs84, miny_wgs84],
        [minx_wgs84, maxy_wgs84],
    ]

    return bounding_box


if __name__ == "__main__":
    pass
