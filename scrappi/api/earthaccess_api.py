"""scrappi.api.earthaccess - earthaccess class for API call handler implementations"""

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

import earthaccess
from earthaccess import DataGranule

from scrappi.api.base import BaseAPICallHandler
from scrappi.product import ProductItem, ProductItemSet
from scrappi.fs.base import BaseFileSystem
from scrappi.utils.utils import *
from scrappi import ScrappiContext

__all__ = ["EarthaccessCallHandler"]


class EarthaccessCallHandler(BaseAPICallHandler):
    """
    Class for earthaccess call handler implementations. Extend `BaseAPICallHandler`.
    """
    name = "earthaccess"
    def __init__(self, 
                 context: Optional[Union[str, List, Context]] = None):
        
        super().__init__(context)
        
        try:
            os.environ["EARTHDATA_USERNAME"] = self.context["earthaccess"]["credentials"]["username"]
            os.environ["EARTHDATA_REMOVED_PASSWORD"] = self.context["earthaccess"]["credentials"]["password"]
        except:
            warnings.warn("No credentials found for earthaccess. Please set these in the config file to enable downloading of products.")
                    
    def _set_product_type(self, collection: str) -> str:
        """
        Return appropriate product type for earthaccess api

        :param collection: product type of interest, e.g. MOD09, MOD02HKM
        """
        return self._get_product_type(collection)
    
    def _set_datetime(self, date_time: Union[dt.datetime, str]) -> str:
        """
        Convert input datetime to a datetime object suited to the earthaccess query format

        :param date_time: input datetime string or object
        :returns: datetime object of the input datetime
        """
        return self._get_datetime(date_time).strftime("%Y-%m-%dT%H:%M:%S")
    
    def _set_geom(
        self, geom: Union[list, dict, str, shapely.geometry.base.BaseGeometry]
    ) -> Union[dict, shapely.geometry.base.BaseGeometry]:
        """
        Convert input geometries to ones suited to the apis query format
        All accepted geometries work for earthaccess api

        :param geom: geometry to convert
        :return: geometry in accepted earthaccess format
        """
        geom = self._get_geom(geom)
        if isinstance(geom, dict):
            return (
                geom["longitude_minimum"],
                geom["latitude_minimum"],
                geom["longitude_maximum"],
                geom["latitude_maximum"],
            )
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
              
    def _format_query(self, query: dict) -> dict:
        """
        Format input query to be earthaccess compatible

        :param query: dict of query parameters (e.g. collection, start_time, stop_time, geom)
        :return: formatted query dict
        """
        earthaccess_query = query.copy()
        earthaccess_query["short_name"] = self._set_product_type(query["collection"])
        earthaccess_query["temporal"] = (self._set_datetime(query["start_time"]),
                                         self._set_datetime(query["stop_time"]))
        earthaccess_query["bounding_box"] = self._set_geom(query["geom"])
        

        for k in ["start_time", "stop_time", "collections", "collection", "geom"]:
            earthaccess_query.pop(k, None)
            
        return earthaccess_query
            
    def list_collections(self) -> List:
        
        if self.context['update_collections_list']:
            results = earthaccess.search_datasets(downloadable = True)
            collections = []
            for x in results:
                try:
                    collections.append(x.summary()['short-name'])
                except:
                    continue
            np.save(os.path.join(os.path.dirname(__file__), "utils", "earthaccess_collections_list.npy"), collections)
        else:
            collections = np.load(os.path.join(os.path.dirname(__file__), "utils", "earthaccess_collections_list.npy"), allow_pickle=True)
        return collections
    
    def _perform_query(self, query: dict) -> list:
        """
        Return catalogue product DataGranules that satisfy query

        :param query: catalogue query
        :returns: product urls satisfying query
        """

        # reformat query into style suitable for earthaccess searching
        earthaccess_query = self._format_query(query)
        
        # search catalogue with query
        products = earthaccess.search_data(**earthaccess_query)

        if "geom" not in earthaccess_query.keys():
            return products

        elif isinstance(earthaccess_query["geom"], shapely.geometry.base.BaseGeometry):
            products = [
                i for i in products if earthaccess_query["geom"].intersects(i.geometry)
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
    
    def perform_query(self, query: dict) -> ProductItemSet:
        """
        Return ProductItemSet containing ProductItems that satisfy query

        :param query: catalogue query
        :returns: ProductItemSet
        """
        if "collections" in query.keys():
            if isinstance(query["collections"], str):
                query["collection"] = query["collections"]
            elif len(query["collections"]) == 1:
                query["collection"] = query["collections"][0]
            else:
                collections = query.pop("collections")
                query["collection"] = collections[0]
                products = self.perform_query(query)
                for icol in range(1, len(collections)):
                    query["collection"] = collections[icol]
                    products.append_ProductItemSet(self.perform_query(query))
                return products

        granule_list = self._perform_query(query)

        if len(granule_list) == 0:
            return ProductItemSet()

        if isinstance(granule_list[0], DataGranule):
            catalogue_obj = [item['umm'] for item in granule_list]

        product_list = []
        for i, prod in enumerate(catalogue_obj):
            prod_dict = prod

            # check if platform is set
            if ("platform" in query) and self.get_platform(prod_dict) != query[
                "platform"
            ]:
                continue

            # check shape of geometry
            if "SpatialExtent" in prod_dict.keys():
                prod_geom = Polygon([(x['Longitude'], x['Latitude'],) for x in prod['SpatialExtent']['HorizontalSpatialDomain']['Geometry']['GPolygons'][0]['Boundary']['Points']])
                
            if "RelatedUrls" in prod_dict.keys():
                url = prod['RelatedUrls'][[x['Type'] for x in prod['RelatedUrls']].index('GET DATA')]['URL']
            else:
                url = ""

            if "CollectionReference" in prod_dict.keys():
                collection = prod_dict["CollectionReference"]['ShortName']
            else:
                collection = query["collection"]

            # store product item
            product_list.append(
                ProductItem(
                    constellation=self.get_constellation(prod_dict),
                    platform=self.get_platform(prod_dict),
                    collection=collection,
                    id=prod_dict['DataGranule']['Identifiers'][0]['Identifier'],
                    geometry=prod_geom,
                    start_time=self.find_start_time(prod_dict),
                    stop_time=self.find_stop_time(prod_dict),
                    prod_dict=prod_dict,
                    filter_dict=self.extract_filter_attributes(prod_dict),
                    api=self,
                    url=url,
                    context=self.context,
                    api_product=granule_list[i],
                    version=self.find_version(prod_dict),
                )
            )

        return ProductItemSet(product_list)
    
    def get_platform(self, prod_dict: dict) -> str:
        """
        Function to extract to platform identifier

        :param prod_dict: earthaccess product dictionary
        :return: platform identifier
        """
        try:
            return self.parse_platform_from_name(prod_dict["CollectionReference"]["ShortName"])
        except NotImplementedError:
            if "Platforms" in prod_dict.keys():
                return [x['ShortName'] for x in prod_dict["Platforms"]][0]
            else:
                raise NotImplementedError("platform name could not be parsed")
            
    def get_constellation(self, prod_dict: dict) -> str:
        """
        Function to extract constellation identifier

        :param prod_dict: earthaccess product dictionary
        :return: constellation identifier
        """
        try:
           return self.parse_constellation_from_name(prod_dict["CollectionReference"]["ShortName"])
        except NotImplementedError:
            if "Platforms" in prod_dict.keys():
                return [x['Instruments'][0]['ShortName'] for x in prod_dict["Platforms"]][0]
            else:
                raise NotImplementedError("platform name could not be parsed")

    def find_version(self, prod_dict: dict) -> str:
        """
        Function to find the version of a product.

        :param prod_dict: earthaccess product dictionary
        :return: version of product
        """
        if "CollectionReference" in prod_dict.keys():
            return prod_dict['CollectionReference']['Version']
        else:
            raise ValueError("version not found in product dictionary")
        
    def find_start_time(self, prod_dict: dict) -> dt.datetime:
        """
        Function to find the best start time for a scene (depends on information provided by provider).

        :param prod_dict: earthaccess product dictionary
        :return: datetime of starting time of observation
        """
        if "TemporalExtent" in prod_dict.keys():
            return self._set_datetime(prod_dict['TemporalExtent']["RangeDateTime"]['BeginningDateTime'])
        else:
            raise ValueError("start time not found in product dictionary")

    def find_stop_time(self, prod_dict: dict) -> dt.datetime:
        """
        Function to find the best end time for a scene (depends on information provided by provider).

        :param prod_dict: earthaccess product dictionary
        :return: datetime of end time of observation
        """
        if "TemporalExtent" in prod_dict.keys():
            return self._set_datetime(prod_dict['TemporalExtent']["RangeDateTime"]['EndingDateTime'])
        else:
            raise ValueError("stop time not found in product dictionary")

    def extract_filter_attributes(self, prod_dict: dict) -> dict:
        """
        Function to extract information that can later be used for filtering,
        and convert the name from the provider specific attribute, to that expected by matchmaker.

        :param prod_dict: earthaccess product dictionary
        :return: dictionary with filter attributes
        """
        filter_dict = {}

        if "DataGranule" in prod_dict.keys():
            filter_dict["day_night_flag"] = prod_dict['DataGranule']['DayNightFlag']

        return filter_dict

    def _download_product_DataGranule(
        self, product: Union[DataGranule, str], path: str, product_id: str,
    ) -> Union[list, str]:
        """
        Download catalogue product(s) at defined URL to local path

        :param product: search result from a earthaccess product query
        :param path: path to write product to
        :param product_id: product id (used for naming downloaded file)
        :return: path to which product has been downloaded
        """
        if isinstance(product, DataGranule) or isinstance(product, str):
            product_title = product_id
            if os.path.exists(os.path.join(path, product_title)):
                print(f"{product_title} exists in {path}")
            else:
                print(f"{product_title} needs downloading to {path}")
                if not os.path.exists(path):
                    os.makedirs(path)

                for attempt in range(self.context.get("max_retrys", 3)):
                    try:
                        path_out = earthaccess.download(product, local_path=path)[0]
                        path_out = str(path_out)
                        if os.path.exists(path_out):
                            break
                        else:
                            raise ValueError(
                                f"{path_out} not downloaded."
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

            return os.path.join(path, product_title)

        else:
            raise ValueError(
                "products are not in the right format for download by scrappi earthaccess (DataGranule or URL)"
            )
             
    def download_product(
        self,
        product: Union[ProductItem, ProductItemSet],
    ) -> Union[list, str]:
        """
        Download catalogue product(s) from query results to local path

        :param product: ProductItem or ProductItemSet that contains all the products as returned by a given query. Alternatively, a filename (id field in ProductItem) can be provided.
        :return: path (or list of paths) to downloaded product(s)
        """

        if isinstance(product, ProductItemSet):
            return [self.download_product(prod) for prod in product]

        earthaccess.login()

        # next perform download based on type of product provided
        if product is None:
            warnings.warn("no product was provided to download")
            return None

        elif isinstance(product, ProductItem):
            path, exists = product.filesystem.return_path(product, check_exists=True)

            if exists:
                print(f"{path} exists")
                return path

            elif product.api_product is not None and isinstance(
                product.api_product, DataGranule
            ):
                eoprod = product.api_product

                return self._download_product_DataGranule(eoprod, os.path.dirname(path), product.id)

            else:
                if (
                    product.prod_dict is not None
                    and "RelatedUrls" in product.prod_dict.keys()
                ):
                    url = product.prod_dict['RelatedUrls'][[x['Type'] for x in product.prod_dict['RelatedUrls']].index('GET DATA')]['URL']
                    
                    return self._download_product_DataGranule(
                        url, os.path.dirname(path), product.id
                    )

        else:
            raise ValueError(
                "products are not in the right format for download by scrappi earthaccess (ProductItem, ProductItemSet)"
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
        :return: path (or list of paths) to downloaded product(s)
        """

        if isinstance(product, List):
            return [self.download_product_filename(prod, fs) for prod in product]

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
            found = False
            product_prov = earthaccess.search_data(granule_name=product)
            if len(product_prov) > 0:
                found = True
                product = product_prov[0]

            if not found:
                warnings.warn(
                    "No product was found for %s. Please check the filename and ensure it is in the right format for scrappi earthaccess download by filename (str). Do not include file extensions."
                    % (product,)
                )
                return None

            path = fs.directory

            return self._download_product_DataGranule(product, path, product['DataGranule']['Identifiers'][0]['Identifier'])

        else:
            raise ValueError(
                "products are not in the right format for filename download by scrappi earthaccess (str)"
            )