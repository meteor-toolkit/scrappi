"""scrappi.utils - util functions for api and file system call handlers"""

from __future__ import annotations
from copy import deepcopy
import tarfile
from typing import Optional, Union, List, Any
import zipfile
from dateutil.parser import parse
import datetime
import shapely
import shapely.wkt
import shapely.errors
import shapely.geometry
from shapely.geometry import Polygon
from pyproj import Transformer
import numpy as np
from pathlib import Path
from processor_tools.utils.formatters import convert_datetime

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]


def add_seconds_to_datetime(dt, seconds):
    """
    add seconds to datetime object

    :param dt: datetime object
    :param seconds: seconds to be added (can be negative)
    :return: adapted datetime
    """
    dt = convert_datetime(dt)
    dt += datetime.timedelta(seconds=seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def generate_bounding_lat_lon(latitude, longitude, distance, crs="EPSG:32630") -> list:
    """
    Return list of coordinates of a square box around a point

    :param latitude: latitude of point
    :param longitude: longitude of point
    :param distance: distance in m of point from each side of the box
    :param crs: Universal Transverse Mercator coordinate reference system of point. Defaults to "EPSG:32630" (standard lat/lon sytem)
    :return: list of coordinates of box
    """
    transformer = Transformer.from_crs(
        "EPSG:4326", str(crs), always_xy=True
    )  # convert from World Geodetic System 1984 to current image crs
    reverse_transformer = Transformer.from_crs(
        str(crs), "EPSG:4326", always_xy=True
    )  # convert from World Geodetic System 1984 to current image crs
    xx, yy = transformer.transform(longitude, latitude)

    minx = xx - distance
    miny = yy - distance
    maxx = xx + distance
    maxy = yy + distance

    minx_wgs84, miny_wgs84 = reverse_transformer.transform(minx, miny)
    maxx_wgs84, maxy_wgs84 = reverse_transformer.transform(maxx, maxy)

    return [miny_wgs84, minx_wgs84, maxy_wgs84, maxx_wgs84]


def convert_geom(geom: Any) -> Any:
    """
    Get the geometry to use to query the api

    :param geom:
    :returns:
    """
    if isinstance(geom, tuple):
        geom = list(geom)

    if isinstance(geom, list):
        if -180 <= geom[1] <= 180 and -180 <= geom[3] <= 180 and -90 <= geom[0] <= 90 and -90 <= geom[2] <= 90:
            return {
                "latitude_minimum": geom[0],
                "longitude_minimum": geom[1],
                "latitude_maximum": geom[2],
                "longitude_maximum": geom[3],
            }
        else:
            raise ValueError("""Incorrect "geom" query format. 
                            Please choose from: 
                                shapely geometry object,
                                Well-Known-Text string (wkt str)
                                dict("latitude_minimum": val,  "longitude_minimum": val, "latitude_maximum": val, "longitude_maximum": val),
                                list(latitude_minimum, longitude_minimum, latitude_maximum, longitude_maximum)
                            """)
    elif isinstance(geom, dict):
        if {
            "longitude_minimum",
            "longitude_maximum",
            "latitude_minimum",
            "latitude_maximum",
        } == set(geom.keys()):
            return geom
        else:
            raise ValueError("""Incorrect "geom" query format. 
                            Please choose from: 
                                shapely geometry object,
                                Well-Known-Text string (wkt str)
                                dict("latitude_minimum": val,  "longitude_minimum": val, "latitude_maximum": val, "longitude_maximum": val),
                                list(latitude_minimum, longitude_minimum, latitude_maximum, longitude_maximum)
                            """)
    elif isinstance(
        geom,
        (
            shapely.geometry.base.BaseGeometry,
            shapely.geometry.base.BaseMultipartGeometry,
        ),
    ):
        if (
            -180 <= geom.bounds[0] <= 180
            and -180 <= geom.bounds[2] <= 180
            and -90 <= geom.bounds[1] <= 90
            and -90 <= geom.bounds[3] <= 90
        ):
            return geom
        else:
            raise ValueError("""Incorrect "geom" query format. 
                            The provided shapely geom has invalid lat or lon. 
                            Remember that shapely polygons are provided with (x,y) coordinates, i.e. (lon, lat).
                            """)
    else:
        try:
            return shapely.wkt.loads(geom)
        except shapely.errors.WKTReadingError:
            raise ValueError("""Incorrect "geom" query format. 
                            Please choose from: 
                                shapely geometry object,
                                Well-Known-Text string (wkt str)
                                dict("latitude_minimum": val,  "longitude_minimum": val, "latitude_maximum": val, "longitude_maximum": val),
                                list(latitude_minimum, longitude_minimum, latitude_maximum, longitude_maximum)
                            """)


def convert_geom_shapely(geom: Any) -> Any:
    """
    Get the geometry converted to shapely

    :param geom:
    :returns:
    """
    geom = convert_geom(
        geom
    )  # this returns shapely or dictionary with "longitude_minimum", "longitude_maximum", "latitude_minimum", "latitude_maximum"
    if isinstance(geom, dict):
        return Polygon(
            (
                (geom["longitude_minimum"], geom["latitude_minimum"]),
                (geom["longitude_maximum"], geom["latitude_minimum"]),
                (geom["longitude_maximum"], geom["latitude_maximum"]),
                (geom["longitude_minimum"], geom["latitude_maximum"]),
                (geom["longitude_minimum"], geom["latitude_minimum"]),
            )
        )
    else:
        return geom


# dictionary tools from eoio
def list_keys(test_dict, new_list=None):
    """
    List all keys in nested dictionary, useful when searching for keys in a Dataset dictionary

    :param test_dict: dictionary to search
    :param new_list: list of keys to append to, default None creates a new empty list to return
    :returns: new_list containing keys in dictionary
    """
    if new_list is None:
        new_list = []
    for k, v in test_dict.items():
        if all(["@" not in k, "#" not in k]):
            new_list.append(k)
        if isinstance(v, dict):
            new_list = list_keys(v, new_list)
    new_list = [*set(new_list)]
    new_list.sort()
    return new_list


def get_nested_value(input_dict: dict, keys: list):
    """
    Return a single value in a nested dictionary at the path loosely defined by the keys.

    Note
    Useful if there are multiple values return by 'get_value' as you can filter the nested
    dictionaries that being searched

    Example dictionary to search through and appropriate keys
    example_dict =
        {"Satellite_1": {"Bands": {"B01": {"Wavelength": 10}, "B02": { "Wavelength": 20}}},
        "Satellite_2": {"Bands": {"B01": {"Wavelength": 30}, "B02": { "Wavelength": 40}}}}
    example_keys =
        ["Satellite_2", "B01", "Wavelength"]

    get_nested_value(example_dict, example_keys) == 30

    :param input_dict: input dictionary through which to search
    :param keys: list of keys ordered from out to in
    """
    value = input_dict
    for k in keys:
        value = get_value(value, k)
    return value


def key_present(test: Union[dict, list], keys: Union[str, list]) -> bool:
    """
    Determine whether a key is present in a nested iterable

    :param test: iterable through which to search
    :param keys: keys to search for in iterable
    :returns: bool
    """
    value = False
    if isinstance(keys, str):
        keys = [keys]
    if isinstance(test, dict):
        for k, v in zip(list(test.keys()), list(test.values())):
            if value is True:
                return value
            elif k in keys:
                value = True
            elif isinstance(v, dict) and v != {}:
                value = key_present(test[k], keys)
            elif isinstance(v, list):
                value = key_present(test[k], keys)
            else:
                pass
    elif isinstance(test, list) and all([isinstance(i, dict) for i in test]):
        for i in range(len(test)):
            value = key_present(test[i], keys)
            if value is True:
                return value
    return value


def get_dict_path(input_dict: dict, value: str, new_list: Optional[list] = None) -> list:
    """
    Return list of keys to get to value in input dictionary. Empty list returned if value isn't present in dictionary

    :param input_dict: input dictionary through which to search for the value given
    :param value: key to look for in the input dictionary
    :param new_list: optional list to append key path to
    :returns: new_list containing the keys required to get to the key defined by value
    """
    if new_list is None:
        new_list = []
    for k, v in input_dict.items():
        if key_present(v, value):
            new_list.append(k)
            new_list = get_dict_path(v, value, new_list)
    return new_list


def get_value(test_dict, key, multiple=False):
    """
    Return dictionary values associated with the specified key

    :param multiple:
    :param test_dict: input dictionary in which to search for the key-value pair/s
    :param key: key to use to search through dictionary
    :returns: list of multiple values or single value associated with key
    """
    value_list = list(get_value_gen(test_dict, key))
    try:
        if len(value_list) == 1 or all([True if i[1] == value_list[0][1] else False for i in value_list]):
            if multiple:
                return value_list
            else:
                return dict(value_list)[key]
    except KeyError:
        return None
    except ValueError:
        pass
    if multiple is True and value_list:
        return value_list
    elif value_list:
        print(
            "Multiple different values found to be associated with '{}'. Consider filtering dictionary further.".format(
                key
            )
        )
        return value_list
    print("No value found associated with '{}'. Check spelling and letter case.".format(key))
    return


def get_value_gen(test_dict: dict, key: str):
    """
    Get generator function of dictionary values associated with the specified key

    :param test_dict: input iterator in which to search for the key-values pair/s
    :param key: key to use to search through dictionary
    :returns: generator function containing key-value pair/s
    """
    if isinstance(test_dict, dict):
        for k, v in zip(list(test_dict.keys()), list(test_dict.values())):
            if k == key:
                t = deepcopy(test_dict.get(k))
                yield k, t
            elif isinstance(v, list) and all([isinstance(i, dict) for i in v]):
                for i, vel in enumerate(v):
                    yield from get_value_gen(test_dict[k][i], key)
            else:
                yield from ([] if not isinstance(v, dict) else get_value_gen(test_dict[k], key))
    elif isinstance(test_dict, list) and all([isinstance(i, dict) for i in test_dict]):
        for i, vel in enumerate(test_dict):
            yield from get_value_gen(test_dict[i], key)


def normalize_product_path(path: Path) -> Path:
    """Normalize a product path by stripping compression suffixes.
    :param path: Path to normalize
    :return: Normalized Path
    """
    archive_suffixes = (".tar", ".gz", ".zip")

    out = path
    while out.suffix in archive_suffixes:
        out = out.with_suffix("")
    return out


def validate_product_download(path: Path) -> bool:
    """Validate that a product has been downloaded by checking the integrity of the archive.

    :param path: Path to validate
    :return: True if the path exists and is a valid archive, False otherwise
    """
    if not path.exists():
        return False

    elif path.suffix == ".zip":
        try:
            with zipfile.ZipFile(path) as z:
                return True
        except Exception:
            return False

    elif path.suffix in (".tar", ".gz"):
        try:
            with tarfile.open(path) as t:
                return True
        except tarfile.TarError:
            return False

    else:
        print(f"File {path} does not have a recognized archive suffix. Cannot validate download.")
        return True
