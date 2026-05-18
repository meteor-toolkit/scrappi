"""EODAG API handler integration for scrappi.

This module provides `EODAGCallHandler`, an implementation of
`BaseAPICallHandler` that uses the EODAG library to search and download
satellite products from supported providers.
"""

import datetime
import os
import shutil
import re
import warnings
import yaml
import requests
import shapely
import shapely.wkt
import shapely.geometry
import time
import numpy as np
import datetime as dt
from packaging.version import Version
from shapely.geometry import Polygon, MultiPolygon, Point
from pathlib import Path
from typing import Optional, Union, List, cast

from processor_tools import Context

from scrappi.api.base import BaseAPICallHandler
from scrappi.product import ProductItem, ProductItemSet
from scrappi.fs.base import BaseFileSystem
from eodag import setup_logging, EODataAccessGateway, SearchResult, EOProduct
from eodag import __version__ as eodag_version
from eodag.plugins.apis.base import Api
from eodag import config as eodagconfig
from scrappi.utils.utils import *
import matplotlib.pyplot as plt
from scrappi import ScrappiContext

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]
__all__ = ["EODAGCallHandler"]


class EODAGCallHandler(BaseAPICallHandler):
    """EODAG API call handler.

    Use this handler to perform catalogue searches and downloads through the
    EODAG ecosystem. Provider credentials and configuration are loaded from
    `self.context["eodag"]` and follow EODAG's configuration schema.

    :param context: scrappi `Context` or equivalent mapping of configuration
    """

    name = "eodag"
    """Name of APICallHandler"""

    def __init__(self, context: Optional[Union[str, List, Context]] = None):
        """
        Extend `BaseAPICallHandler.__init__()` saving provided credentials as environment variables
        for "service" authentication.
        """
        super().__init__(context)

        self.dag = EODataAccessGateway()
        if self.context["eodag"] is not None:
            self.dag.update_providers_config(
                dict_conf=self.filter_eodag_config_priority(self.context["eodag"])
            )

        if self.context["api"]["preferred_provider"] is not None:
            self.dag.set_preferred_provider(self.context["api"]["preferred_provider"])

        self.check_eodag_version()
        self.check_usgs_tmp_file(
            delete_tmp_file=self.context.get("delete_usgs_tmp_file", False)
        )

        # this bit is meant to be used for one time passwords (authenticator apps), but does not seem to work right
        # if "totp" in config_dict.keys():
        #     provider = config_dict["totp_provider"]
        #     totp = config_dict["totp"]
        #     self.dag.providers_config[provider].auth.credentials["totp"] = totp
        #     print(self.dag.providers_config[provider].auth.credentials)
        #     self.dag._plugins_manager.get_auth_plugin(provider).authenticate()

        setup_logging(
            self.context["api"]["eodag_logging_level"]
        )  # 3 for even more information

    def filter_eodag_config_priority(self, eodag_config: dict) -> dict:
        """Return a copy of an EODAG provider configuration filtered by priority.

        Only providers with a `priority` value greater than zero are retained.

        :param eodag_config: mapping of provider keys to provider configuration
        :return: filtered provider configuration dict
        """
        filtered_eodag_config = {}
        for key in eodag_config.keys():
            if eodag_config[key]["priority"] and eodag_config[key]["priority"] > 0:
                filtered_eodag_config[key] = eodag_config[key]
        return filtered_eodag_config

    def update_context(self, context):
        """Update providers configuration with given input.
        Can be used to add a provider to existing configuration or update
        an existing one.

        :param yaml_conf: YAML formated provider configuration
        """
        self.context = context
        self.dag.update_providers_config(dict_conf=context["eodag"])

    def _set_datetime(self, date_time: Union[dt.datetime, str]) -> str:
        """
        Convert input datetime to a datetime object suited to the eodag query format

        :param date_time: input datetime string or object
        :returns: datetime object of the input datetime
        """
        return self._get_datetime(date_time).strftime("%Y-%m-%dT%H:%M:%S")

    def _set_geom(
        self, geom: Union[list, dict, str, shapely.geometry.base.BaseGeometry]
    ) -> Union[dict, shapely.geometry.base.BaseGeometry]:
        """
        Convert input geometries to ones suited to the apis query format
        All accepted geometries work for eodag api

        :param geom: geometry to convert
        :return: geometry in accepted eodag format
        """
        geom = self._get_geom(geom)
        if isinstance(geom, dict):
            return {
                "lonmin": geom["longitude_minimum"],
                "latmin": geom["latitude_minimum"],
                "lonmax": geom["longitude_maximum"],
                "latmax": geom["latitude_maximum"],
            }
        else:
            if not isinstance(
                geom,
                (
                    shapely.geometry.base.BaseGeometry,
                    shapely.geometry.base.BaseMultipartGeometry,
                ),
            ):
                geom = shapely.wkt.loads(geom)
            return geom

    def _set_product_type(self, collection: str) -> str:
        """
        Return appropriate product type for eodag api

        :param collection: product type of interest, e.g. S3_EFR
        """
        return self._get_product_type(collection)

    def get_providers(self, collection: str) -> list:
        """
        Return product catalogue providers available for provided product type/collection through eodag

        :param collection: product type of interest, e.g. S3_EFR
        """
        return self.dag.available_providers(collection)

    def list_collections(
        self, 
    ) -> List:
        """Lists supported collections.

        :returns: The list of the collections that can be accessed using eodag.) -> list:
        """
        return [
            collection.id
            for collection in self.dag.list_collections(fetch_providers=self.context["api"]["fetch_collection_update"]
            )
        ]

    def _perform_query(self, query: dict) -> list:
        """
        Return catalogue product SearchResults that satisfy query

        :param query: catalogue query
        :returns: product urls satisfying query
        """
        # query_geom = query["geom"]

        # reformat query into style suitable for eodag searching
        eodag_query = query.copy()
        eodag_query["collection"] = self._set_product_type(query["collection"])
        eodag_query["geom"] = self._set_geom(query["geom"])
        eodag_query["start"] = self._set_datetime(query["start_time"])
        eodag_query["end"] = self._set_datetime(query["stop_time"])

        for k in ["start_time", "stop_time", "collections"]:
            eodag_query.pop(k, None)

        # search catalogue with query
        try:
            self.dag.update_providers_config(dict_conf=self.context["eodag"])
        except Exception as e:
            print(f"Error updating providers config: {e}")

        products = self.dag.search_all(**eodag_query)

        if "geom" not in eodag_query.keys():
            return products

        elif isinstance(eodag_query["geom"], shapely.geometry.base.BaseGeometry):
            products = [
                i for i in products if eodag_query["geom"].intersects(i.geometry)
            ]
            return products

        for p in products:
            for s in ["geometry", "search_intersection"]:
                if isinstance(p.__dict__[s], MultiPolygon):
                    if len(p.__dict__[s].geoms) > 1:
                        raise NotImplementedError(
                            "The satellite product uses multiple Polygons within a MultiPolygon. This is not yet implemented within scrappi."
                        )
                    p.__dict__[s] = p.__dict__[s].geoms[0]

        return products

    def list_queryables(self, provider):
        return self.dag.list_queryables("cop_cds")

    def perform_query(self, query: dict) -> ProductItemSet:
        """
        Return ProductItemSet containing ProductItems that satisfy query

        :param query: catalogue query
        :returns: ProductItemSet
        """
        catalogue_obj = self._perform_query(query)

        if len(catalogue_obj) == 0:
            return ProductItemSet()

        if isinstance(catalogue_obj[0], SearchResult):
            catalogue_obj = [prod for item in catalogue_obj for prod in item]

        product_list = []
        for prod in catalogue_obj:
            prod_dict = prod.as_dict()
            # check if quicklook is present
            if (
                ("eodag:quicklook" not in prod_dict["properties"].keys())
                or (prod_dict["properties"]["eodag:quicklook"] is None)
                or (len(prod_dict["properties"]["eodag:quicklook"]) > 200)
            ):
                prod_dict["properties"]["eodag:quicklook"] = ""

            if ("eo:cloud_cover" not in prod_dict["properties"].keys()) or (
                prod_dict["properties"]["eo:cloud_cover"] is None
            ):
                prod_dict["properties"]["eo:cloud_cover"] = np.nan

            # check if platform is set
            if ("platform" in query) and self.get_platform(prod_dict) != query[
                "platform"
            ]:
                continue

            # check shape of geometry
            if prod_dict["geometry"]["type"] == "Point":
                prod_geom = Point(prod_dict["geometry"]["coordinates"])
            else:
                prod_geom = Polygon(prod_dict["geometry"]["coordinates"][0])

            if "eodag:download_link" in prod_dict["properties"].keys():
                url = prod_dict["properties"]["eodag:download_link"]
            elif "orderLink" in prod_dict["properties"].keys():
                url = prod_dict["properties"]["orderLink"]
            else:
                url = ""

            if "collection" in prod_dict["properties"].keys():
                collection = prod_dict["properties"]["collection"]
            else:
                collection = query["collection"]

            # store product item
            product_list.append(
                ProductItem(
                    constellation=self.get_constellation(prod_dict),
                    platform=self.get_platform(prod_dict),
                    collection=collection,
                    id=prod_dict["id"],
                    geometry=prod_geom,
                    start_time=self.find_start_time(prod_dict),
                    stop_time=self.find_stop_time(prod_dict),
                    prod_dict=prod_dict,
                    filter_dict=self.extract_filter_attributes(prod_dict),
                    api=self,
                    url=url,
                    quicklook=prod_dict["properties"]["eodag:quicklook"],
                    cloud_fraction=prod_dict["properties"]["eo:cloud_cover"],
                    context=self.context,
                    api_product=prod,
                )
            )

        return ProductItemSet(product_list)

    def get_platform(self, prod_dict: dict) -> str:
        """
        Function to extract to platform identifier

        :param prod_dict: eodag product dictionary
        :return: platform identifier
        """
        try:
            return self.parse_platform_from_name(prod_dict["id"])
        except NotImplementedError:
            if "platformSerialIdentifier" in prod_dict["properties"]:
                return prod_dict["properties"]["platformSerialIdentifier"]
            else:
                raise NotImplementedError("platform name could not be parsed")

    def get_constellation(self, prod_dict: dict) -> str:
        """
        Function to extract constellation identifier

        :param prod_dict: eodag product dictionary
        :return: constellation identifier
        """
        try:
            return self.parse_constellation_from_name(prod_dict["id"])
        except NotImplementedError:
            if "platformSerialIdentifier" in prod_dict["properties"]:
                return prod_dict["properties"]["constellationIdentifier"]
            else:
                raise NotImplementedError("constellation name could not be parsed")

    def get_version(self, prod_dict: dict) -> str:
        """
        Function to extract version/baseline of processor

        :param prod_dict: eodag product dictionary
        :return: version identifier
        """
        if "processingBaseline" in prod_dict["properties"]:
            return prod_dict["properties"]["processingBaseline"]
        else:
            raise NotImplementedError("The platform for this query is not found.")

    def find_start_time(self, prod_dict: dict) -> dt.datetime:
        """
        Function to find the best start time for a scene (depends on information provided by provider).

        :param prod_dict: eodag product dictionary
        :return: datetime of starting time of observation
        """
        if "beginPosition" in prod_dict["properties"]:
            return self._set_datetime(prod_dict["properties"]["beginPosition"])

        elif "start_datetime" in prod_dict["properties"]:
            return self._set_datetime(prod_dict["properties"]["start_datetime"])

        else:
            raise ValueError("start time not found in product dictionary")

    def find_stop_time(self, prod_dict: dict) -> dt.datetime:
        """
        Function to find the best end time for a scene (depends on information provided by provider).

        :param prod_dict: eodag product dictionary
        :return: datetime of end time of observation
        """
        if "endPosition" in prod_dict["properties"]:
            return self._set_datetime(prod_dict["properties"]["endPosition"])

        elif prod_dict["collection"] == "LANDSAT_C2L1":
            return self._set_datetime(
                prod_dict["properties"]["end_datetime"][0:10] + "T23:59:59"
            )

        elif "end_datetime" in prod_dict["properties"]:
            return self._set_datetime(prod_dict["properties"]["end_datetime"])

        elif "start_datetime" in prod_dict["properties"]:
            return self._set_datetime(prod_dict["properties"]["start_datetime"])

        else:
            raise ValueError("stop time not found in product dictionary")

    def extract_filter_attributes(self, prod_dict: dict) -> dict:
        """
        Function to extract information that can later be used for filtering,
        and convert the name from the provider specific attribute, to that expected by matchmaker.

        :param prod_dict: eodag product dictionary
        :return: dictionary with filter attributes
        """
        filter_dict = {}

        if prod_dict["properties"]["providers"][0]["name"] == "usgs":
            filter_dict["cloud_fraction"] = prod_dict["properties"]["eo:cloud_cover"]

        return filter_dict

    def _download_product_EOProduct(
        self, product: EOProduct, path: str
    ) -> Union[list, str]:
        """
        Download catalogue product(s) at defined URL to local path

        :param product: search result from a eodag product query
        :param path: path to write product to
        :return: path to which product has been downloaded
        """

        if isinstance(product, EOProduct):
            product_title = product.properties["id"]
            if os.path.isfile(os.path.join(path, product_title.split(".")[0] + ".zip")):
                print(f"zipped {product_title} exists in {path}")
            elif os.path.exists(os.path.join(path, product_title)):
                print(f"{product_title} exists in {path}")
            else:
                print(f"{product_title} needs downloading to {path}")
                if not os.path.exists(path):
                    os.makedirs(path)

                if hasattr(product.downloader, "config") and hasattr(
                    product.downloader.config, "timeout"
                ):
                    timeout = product.downloader.config.timeout
                else:
                    timeout = 10
                if hasattr(product.downloader, "config") and hasattr(
                    product.downloader.config, "wait"
                ):
                    wait = product.downloader.config.wait
                else:
                    wait = 0.2

                for attempt in range(self.context.get("max_retrys", 3)):
                    try:
                        path_out = product.download(
                            outputs_prefix=path,
                            output_dir=path,
                            extract=False,
                            timeout=timeout,
                            wait=wait,
                        )
                        if validate_product_download(Path(path_out)):
                            break
                        else:
                            try:
                                if path_out and Path(path_out).exists():
                                    if Path(path_out).is_dir():
                                        shutil.rmtree(path_out)
                                    else:
                                        Path(path_out).unlink()
                            except Exception:
                                pass
                            raise ValueError(
                                f"Downloaded file {path_out} is not a valid download."
                            )

                    except Exception as e:
                        print(f"Download attempt {attempt+1} failed with error: {e}")
                        if attempt < self.context.get("max_retrys", 3) - 1:
                            print(
                                f"Retrying download after {self.context.get('retry_wait', 5)} seconds..."
                            )
                            time.sleep(self.context.get("retry_wait", 5))
                        else:
                            print(
                                f"Max download attempts reached. Download failed for product {product_title}."
                            )
                            raise e

                if not (
                    os.path.basename(path_out) == product_title
                    or os.path.basename(path_out.split(".")[0]) == product_title
                ):
                    # Safely check configuration option to allow modifying downloaded filename
                    allow_modify = False
                    try:
                        allow_modify = bool(
                            self.context["eodag"][product.provider].get(
                                "allow_modify_download_filename", False
                            )
                        )
                    except Exception:
                        allow_modify = False

                    if allow_modify:
                        warnings.warn(
                            f"Filename of the downloaded file ({os.path.basename(path_out)}) does not match the product title ({product_title}). Modifying product_title to correct."
                        )
                        product_title = os.path.basename(path_out)
                        product.properties["id"] = product_title
                    else:
                        warnings.warn(
                            f"Filename of the downloaded file ({os.path.basename(path_out)}) does not match the product title ({product_title}). Continuing without modifying product_title."
                        )
                        if path_out.split(".")[-1] == "zip":
                            if not product_title.split(".")[-1] == "zip":
                                warnings.warn(
                                    f"Adding .zip to the product title (returned downloaded file has .zip)"
                                )
                                product_title += ".zip"

                path_out = Path(path_out)
                expected = Path(path) / product_title

                if normalize_product_path(path_out) != expected:
                    warnings.warn(
                        f"Downloaded product to {path_out} instead of expected {os.path.join(path, product_title)}. Moving to expected location."
                    )
                    if os.path.isdir(path_out):
                        shutil.move(path_out, os.path.join(path, product_title))
                    else:
                        os.rename(path_out, os.path.join(path, product_title))
                if os.path.isdir(os.path.join(path, product_title)):
                    # List only files
                    files = [
                        f
                        for f in os.listdir(os.path.join(path, product_title))
                        if os.path.isfile(
                            os.path.join(os.path.join(path, product_title), f)
                        )
                    ]
                    print(files)
                    if len(files) == 1:
                        warnings.warn(
                            f"Downloaded product is a directory containing only one file. Moving this file to the expected location and removing the directory."
                        )
                        shutil.move(
                            os.path.join(path, product_title, files[0]),
                            os.path.join(path, files[0]),
                        )
                        os.rmdir(os.path.join(path, product_title))
                        product_title = files[0]
            return os.path.join(path, product_title)

        else:
            raise ValueError(
                "products are not in the right format for download by scrappi eodag (EOproduct)"
            )

    def _set_provider_output_dir(self, eoprod, path):
        """
        Set the output directory for the provider of the EOProduct.
        This is necessary to ensure that the downloaded files are stored in the correct location.
        """
        provider_config = self.dag.providers.configs[eoprod.provider]
        output_dir = os.path.dirname(path)

        # Try to set api.output_dir
        if hasattr(self.dag.providers.configs[eoprod.provider], "api") and hasattr(
            self.dag.providers.configs[eoprod.provider].api, "output_dir"
        ):
            print(
                f"Setting output directory for provider {eoprod.provider} to {output_dir}"
            )
            self.dag.providers.configs[eoprod.provider].api.output_dir = output_dir
        # Try to set download.output_dir
        elif hasattr(
            self.dag.providers.configs[eoprod.provider], "download"
        ) and hasattr(
            self.dag.providers.configs[eoprod.provider].download, "output_dir"
        ):
            print(
                f"Setting output directory for provider {eoprod.provider} to {output_dir}"
            )
            self.dag.providers.configs[eoprod.provider].download.output_dir = output_dir

        else:
            # provider does not have a known output_dir attribute
            print(
                f"No known option to change download directory for provider {eoprod.provider}. "
            )
            print("data saved in local TEMP dir")

    def download_product(
        self,
        product: Union[ProductItem, ProductItemSet],
    ) -> Union[list, str]:
        """
        Download catalogue product(s) from query results to local path

        :param product: ProductItem or ProductItemSet that contains all the products as returned by a given query. Alternatively, a filename (id field in ProductItem) can be provided.
        :return: path (or list of paths) to downloaded product(s)
        """

        if isinstance(product, ProductItemSet) or isinstance(product, SearchResult):
            return [self.download_product(prod) for prod in product]

        # next perform download based on type of product provided
        if product is None:
            warnings.warn("no product was provided to download")
            return None

        elif isinstance(product, ProductItem):
            path, exists = product.filesystem.return_path(product, check_exists=True)

            if exists:
                print(f"{path} exists")
                valid_download = validate_product_download(Path(path))
                if not valid_download:
                    warnings.warn(
                        f"Existing file {path} is not a valid download. Removing the partial download and redownloading product."
                    )
                    try:
                        if Path(path).is_dir():
                            shutil.rmtree(path)
                        else:
                            Path(path).unlink()
                    except Exception as e:
                        print(f"Error removing invalid download {path}: {e}")
                        raise e
                else:
                    return path

            elif product.api_product is not None and isinstance(
                product.api_product, EOProduct
            ):
                eoprod = product.api_product
                # self._set_provider_output_dir(eoprod, path)

                return self._download_product_EOProduct(eoprod, os.path.dirname(path))

            else:
                if (
                    product.prod_dict is not None
                    and "properties" in product.prod_dict.keys()
                ):
                    try:
                        eoprod = EOProduct.from_geojson(product.prod_dict)
                        # self.dag.providers_config[
                        #     eoprod.provider
                        # ].api.products = self.dag.providers_config[eoprod.provider].products
                        self.dag._setup_downloader(eoprod)
                        self._set_provider_output_dir(eoprod, path)
                        return self._download_product_EOProduct(
                            eoprod, os.path.dirname(path)
                        )
                    except:
                        print(
                            "Could not create EOProduct from prod_dict, trying search method."
                        )
                        pass

                new_query = {
                    "collection": product.collection,
                    "geom": {
                        "latitude_minimum": product.geometry.bounds[1],
                        "longitude_minimum": product.geometry.bounds[0],
                        "latitude_maximum": product.geometry.bounds[3],
                        "longitude_maximum": product.geometry.bounds[2],
                    },
                    "start_time": add_seconds_to_datetime(product.start_time, -10),
                    "stop_time": add_seconds_to_datetime(product.stop_time, 10),
                }
                # search catalogue with query
                searchresult = self._perform_query(new_query)
                search_ids = np.array([prod.as_dict()["id"] for prod in searchresult])
                correct_ids = np.where(search_ids == product.id)[0]
                if len(correct_ids) == 0:
                    warnings.warn("no products found that satisfy download criterea")
                    return None
                elif len(correct_ids) > 1:
                    warnings.warn(
                        "multiple products found that satisfy download criterea (%s), only first will be downloaded."
                        % searchresult
                    )

                return self._download_product_EOProduct(
                    searchresult[correct_ids[0]], os.path.dirname(path)
                )

        else:
            raise ValueError(
                "products are not in the right format for download by scrappi eodag (ProductItem, ProductItemSet)"
            )

    def download_product_filename(
        self,
        product: Union[str, List],
        fs: Optional[BaseFileSystem] = None,
    ) -> Union[list, str]:
        """
        Download catalogue product(s) from query results to local path

        :param product: filename (id field in ProductItem)
        :param fs: file system to use when writing the data. Alternatively, an existing product path can be provided as a string. If nothing is provided, it defaults to the path of scrappi/examples/downloaded_data
        :param organise_data: When a path is provided as a string (or when using default) instead of a filesystem, the organise_data boolean decides whether the data is organised by collection/year/month/day or not. Defaults to True.
        :param provider: When providing the product as a flename string, the provider is used to determine how the file should be downloaded. Not relevant when ProductItem or ProductItemSet is used.
        :return: path (or list of paths) to downloaded product(s)
        """

        if isinstance(product, List):
            return [self.download_product_filename(prod, provider) for prod in product]

        from scrappi import make_fs

        if fs:
            fs = make_fs(fs)
        else:
            fs = make_fs(context=self.context)

        # next perform download based on type of product provided
        if product is None:
            warnings.warn("no product was provided to download")
            return None

        elif isinstance(product, str):
            provider = self.context["api"]["preferred_provider"]
            if provider is None:
                provider = ["peps", "usgs"]

            if not isinstance(provider, list):
                provider = [provider]

            found = False
            for prov in provider:
                product_prov = self.dag.search(id=product, provider=prov)
                if len(product_prov) > 0:
                    found = True
                    product = product_prov[0]

            if not found:
                warnings.warn(
                    "No product was found for %s for these providers (%s)"
                    % (product, provider)
                )
                return None

            path = fs.directory

            return self._download_product_EOProduct(product, path)

        else:
            raise ValueError(
                "products are not in the right format for filename download by scrappi eodag (str)"
            )

    def check_eodag_version(self):
        """
        Check the version of eodag being used and warn if it differs from the latest version on PyPI.
        """

        url = f"https://pypi.org/pypi/eodag/json"

        try:
            resp = requests.get(url, timeout=2)
            resp.raise_for_status()
            data = resp.json()
            latest_version = data["info"]["version"]
        except Exception:
            latest_version = None
            print(
                "Could not check for latest version of EODAG on PyPI. Continuing without version check."
            )

        if eodag_version != latest_version and latest_version is not None:
            warnings.warn(
                f"The version of EODAG you are using ({eodag_version}) is not the latest version available on PyPI ({latest_version}). Scrappi may not perform as expected if you continue using this version."
            )

    def check_usgs_tmp_file(self, delete_tmp_file: bool = True):
        """
        Check for the presence of a temporary file created by the USGS provider during download, and remove it if it exists.
        """

        TMPFILE = os.path.join(os.path.expanduser("~"), ".usgs")

        if os.path.exists(TMPFILE):
            print(
                f"Found temporary file created by USGS provider during download at {TMPFILE}. Removing this file to prevent issues with download validation."
            )
            if delete_tmp_file:
                try:
                    os.remove(TMPFILE)
                except Exception as e:
                    print(
                        f"Error removing temporary USGS credential file {TMPFILE}: {e}"
                    )


if __name__ == "__main__":
    pass
