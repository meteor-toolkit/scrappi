"""scrappi.api.eumdac - EUMDAC class for API call handler implementations"""

import os
import shutil
import warnings
import shapely
import shapely.wkt
import shapely.geometry
import time
import numpy as np
import datetime as dt
from shapely.geometry import Polygon, MultiPolygon, shape
from typing import Any, Optional, Union, List

import eumdac

from scrappi.api.base import BaseAPICallHandler
from scrappi.product import ProductItem, ProductItemSet
from scrappi.fs.base import BaseFileSystem
from scrappi import ScrappiContext

__all__ = ["EUMDACCallHandler"]


class EUMDACCallHandler(BaseAPICallHandler):
    """
    Class for eumdac call handler implementations. Extend `BaseAPICallHandler`.
    """

    name = "eumdac"

    def __init__(self, context: Optional[Union[str, List, ScrappiContext]] = None):

        super().__init__(context)

        try:
            eumdac_key = self.context["eumdac"]["credentials"]["key"]
            eumdac_secret = self.context["eumdac"]["credentials"]["secret"]
            
        except Exception:
            warnings.warn(
                "No credentials found for eumdac. Please set these in the config file to enable downloading of products."
            )

        self.eumdac_token = eumdac.AccessToken([eumdac_key, eumdac_secret])
        self.api = eumdac.DataStore(self.eumdac_token)

    def _set_product_type(self, collection: str) -> str:
        """
        Return appropriate product type for eumdac api

        :param collection: product type of interest, e.g. EO:EUM:DAT:METOP:IASIL1C-ALL
        """
        return self._get_product_type(collection)

    def _set_datetime(self, date_time: Union[dt.datetime, str]) -> str:
        """
        Convert input datetime to a datetime object suited to the eumdac query format

        :param date_time: input datetime string or object
        :returns: datetime object of the input datetime
        """
        return self._get_datetime(date_time)

    def _set_geom(
        self, geom: Union[list, dict, str, shapely.geometry.base.BaseGeometry]
    ) -> Union[dict, shapely.geometry.base.BaseGeometry]:
        """
        Convert input geometries to ones suited to the apis query format
        EUMDAC accepts either a bbox or Polygon, but these are different arguments in the query.
        For simplicity, this function will return a bbox (str) if a dict is provided, and a Polygon if a shapely geometry is provided.

        :param geom: geometry to convert
        :return: geometry in accepted eumdac format
        """
        geom = self._get_geom(geom)
        if isinstance(geom, dict):
            return "{lon_min}, {lat_min}, {lon_max}, {lat_max}".format(
                lon_min=geom["longitude_minimum"],
                lat_min=geom["latitude_minimum"],
                lon_max=geom["longitude_maximum"],
                lat_max=geom["latitude_maximum"],
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
        Format input query to be eumdac compatible

        :param query: dict of query parameters (e.g. collection, start_time, stop_time, geom)
        :return: formatted query dict
        """
        eumdac_query = query.copy()
        eumdac_query["selected_collection"] = self._set_product_type(query["collection"])
        eumdac_query["dtstart"] = self._set_datetime(query["start_time"])
        eumdac_query["dtend"] = self._set_datetime(query["stop_time"])
        if self._set_geom(query["geom"]) is not None:
            if isinstance(self._set_geom(query["geom"]), str):
                eumdac_query["bbox"] = self._set_geom(query["geom"])
            else:
                eumdac_query["geo"] = self._set_geom(query["geom"])

        for k in ["start_time", "stop_time", "collections", "collection", "geom"]:
            eumdac_query.pop(k, None)

        return eumdac_query

    def list_collections(self) -> List:

        collections = [collection._id for collection in self.api.collections]
        return collections

    def _perform_query(self, query: dict) -> list:
        """
        Return EUMETSAT DataStore products that satisfy query

        :param query: catalogue query
        :returns: product urls satisfying query
        """

        # reformat query into style suitable for eumdac searching
        eumdac_query = self._format_query(query)

        # set collection object to be used for searching
        collection = self.api.get_collection(eumdac_query["selected_collection"])
        eumdac_query.pop("selected_collection", None)

        # search catalogue with query
        products = collection.search(**eumdac_query)

        if not any(key in eumdac_query.keys() for key in ["geo", "bbox"]):
            return products

        elif "geo" in eumdac_query.keys() and isinstance(eumdac_query["geo"], shapely.geometry.base.BaseGeometry):
            products = [i for i in products if eumdac_query["geo"].intersects(i._geometry)]  # type: ignore
            return products

        for p in products:
            for s in ["_geometry"]:
                geometry = p.__dict__.get(s)
                if geometry is None:
                    continue
                if isinstance(geometry, MultiPolygon):
                    if len(geometry.geoms) > 1:
                        raise NotImplementedError(
                            "The satellite product uses multiple Polygons within a MultiPolygon. This is not yet implemented within scrappi."
                        )
                    p.__dict__[s] = geometry.geoms[0]

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

        product_list = self._perform_query(query)

        if len(product_list) == 0:
            return ProductItemSet()

        product_item_list = []
        for i, prod in enumerate(product_list):
            prod_dict = prod._browse_properties
            prod_geom = self.convert_geom(prod._geometry)

            # check if platform is set
            if ("platform" in query) and self.get_platform(prod_dict) != query["platform"]:
                continue

            if "links" in prod_dict.keys():
                url = prod_dict["links"]["data"][0]["href"]
            else:
                url = ""

            try:
                collection = str(prod.collection)
            except KeyError:
                collection = query["collection"]

            # store product item
            product_item_list.append(
                ProductItem(
                    constellation=self.get_constellation(prod_dict),
                    platform=self.get_platform(prod_dict),
                    collection=collection,
                    id=prod_dict["identifier"],
                    geometry=prod_geom,
                    start_time=self.find_start_time(prod_dict),
                    stop_time=self.find_stop_time(prod_dict),
                    prod_dict=prod_dict,
                    filter_dict=self.extract_filter_attributes(prod_dict),
                    api=self,
                    url=url,
                    context=self.context,
                    api_product=prod,
                    version=self.find_version(prod_dict),
                )
            )

        return ProductItemSet(product_item_list)
    
    def convert_geom(self, geom: Union[dict, shapely.geometry.base.BaseGeometry]) -> Union[dict, shapely.geometry.base.BaseGeometry]:
        """
        Convert product metadata geometry to a format suitable for filtering and downloading
        :param geom: geometry to convert
        :return: geometry in shapely format
        """


        geometry = shape(geom) if isinstance(geom, dict) else geom

        if geometry.geom_type == "Polygon":
            return geometry

        if geometry.geom_type == "MultiPolygon":
            if len(geometry.geoms) == 1:
                return geometry.geoms[0]
            raise ValueError("MultiPolygon contains more than one polygon")

        raise ValueError(f"Unsupported geometry type: {geometry.geom_type}")


    def get_platform(self, prod_dict: dict) -> str:
        """
        Function to extract to platform identifier

        :param prod_dict: eumdac product dictionary
        :return: platform identifier
        """
        try:
            return prod_dict["acquisitionInformation"][0]["platform"]["platformShortName"]
        except NotImplementedError:
            raise NotImplementedError("platform name could not be parsed")

    def get_constellation(self, prod_dict: dict) -> str:
        """
        Function to extract constellation identifier

        :param prod_dict: eumdac product dictionary
        :return: constellation identifier
        """
        try:
            return self.parse_constellation_from_name(prod_dict["acquisitionInformation"][0]["platform"]["platformShortName"])
        except NotImplementedError:
            raise NotImplementedError("platform name could not be parsed")

    def find_version(self, prod_dict: dict) -> str:
        """
        Function to find the version of a product.

        :param prod_dict: eumdac product dictionary
        :return: version of product
        """
        if "productVersion" in prod_dict["productInformation"].keys():
            return prod_dict["productInformation"]["productVersion"]
        else:
            return ""

    def find_start_time(self, prod_dict: dict) -> Union[dt.datetime, str]:
        """
        Function to find the best start time for a scene (depends on information provided by provider).

        :param prod_dict: eumdac product dictionary
        :return: datetime of starting time of observation
        """

        if "date" in prod_dict.keys():
            return [
                dt.datetime.fromisoformat(t.replace('Z', '+00:00'))
                for t in prod_dict['date'].split('/')
            ][0]
        else:
            raise ValueError("start time not found in product dictionary")

    def find_stop_time(self, prod_dict: dict) -> Union[dt.datetime, str]:
        """
        Function to find the best end time for a scene (depends on information provided by provider).

        :param prod_dict: eumdac product dictionary
        :return: datetime of end time of observation
        """

        if "date" in prod_dict.keys():
            return [
                dt.datetime.fromisoformat(t.replace('Z', '+00:00'))
                for t in prod_dict['date'].split('/')
            ][1]
        else:
            raise ValueError("stop time not found in product dictionary")

    def extract_filter_attributes(self, prod_dict: dict) -> dict:
        """
        Function to extract information that can later be used for filtering,
        and convert the name from the provider specific attribute, to that expected by matchmaker.

        :param prod_dict: eumdac product dictionary
        :return: dictionary with filter attributes
        """
        filter_dict = {}

        # To be implemented if any suitable filter attributes are identified in future

        return filter_dict

    def _download_product(
        self,
        product: Union[eumdac.product.Product, str],
        path: str,
        product_id: str,
    ) -> Union[list, str]:
        """
        Download catalogue product(s) at defined URL to local path

        :param product: search result from a eumdac product query
        :param path: path to write product to
        :param product_id: product id (used for naming downloaded file)
        :return: path to which product has been downloaded
        """
        if isinstance(product, eumdac.product.Product) or isinstance(product, str):
            product_title = product_id
            if os.path.exists(os.path.join(path, product_title)):
                print(f"{product_title} exists in {path}")
            else:
                print(f"{product_title} needs downloading to {path}")
                if not os.path.exists(path):
                    os.makedirs(path)

                if isinstance(product, eumdac.product.Product):
                    for attempt in range(self.context.get("max_retrys", 3)):
                        try:
                            with product.open() as fsrc, open(os.path.join(path, product_title), mode='wb') as fdst:
                                shutil.copyfileobj(fsrc, fdst)
                                print(f'Download of product {product} finished.')
                            if os.path.exists(os.path.join(path, product_title)):
                                break
                            else:
                                raise ValueError(f"{product_title} not downloaded.")

                        except Exception as e:
                            print(f"Download attempt {attempt + 1} failed with error: {e}")
                            if attempt < self.context.get("max_retrys", 3) - 1:
                                print(f"Retrying download after {self.context.get('retry_wait', 5)} seconds...")
                                time.sleep(self.context.get("retry_wait", 5))
                            else:
                                print(f"Max download attempts reached. Download failed for product {product_title}.")
                                raise e

                elif isinstance(product, str):     
                    for attempt in range(self.context.get("max_retrys", 3)):
                        try:
                            response = requests.get(product,
                                                    headers={"Authorization": f"Bearer {self.eumdac_token}"}
                                                    )
                            with open(os.path.join(path, product_title), "wb") as f:
                                f.write(response.content)
                                print(f'Download of product {product} finished.')
                            if os.path.exists(os.path.join(path, product_title)):
                                break
                            else:
                                raise ValueError(f"{product_title} not downloaded.")

                        except Exception as e:
                            print(f"Download attempt {attempt + 1} failed with error: {e}")
                            if attempt < self.context.get("max_retrys", 3) - 1:
                                print(f"Retrying download after {self.context.get('retry_wait', 5)} seconds...")
                                time.sleep(self.context.get("retry_wait", 5))
                            else:
                                print(f"Max download attempts reached. Download failed for product {product_title}.")
                                raise e 


            return os.path.join(path, product_title)

        else:
            raise ValueError(
                "products are not in the right format for download by scrappi EUMDAC (eumdac.product.Product or URL)"
            )

    def download_product(
        self,
        product: Union[str, ProductItem, ProductItemSet],
    ) -> Optional[Union[list, str]]:
        """
        Download catalogue product(s) from query results to local path

        :param product: ProductItem or ProductItemSet that contains all the products as returned by a given query. Alternatively, a filename (id field in ProductItem) can be provided.
        :return: path (or list of paths) to downloaded product(s)
        """

        if isinstance(product, ProductItemSet):
            return [self.download_product(prod) for prod in product]

        # next perform download based on type of product provided
        if product is None:
            warnings.warn("no product was provided to download")
            return None

        elif isinstance(product, ProductItem):
            path, exists = product.filesystem.return_path(product, check_exists=True)

            if exists:
                print(f"{path} exists")
                return path

            elif product.api_product is not None and isinstance(product.api_product, eumdac.product.Product):
                eoprod = product.api_product

                return self._download_product(eoprod, os.path.dirname(path), product.id)

            else:
                if product.prod_dict is not None and "links" in product.prod_dict.keys():
                    url = product.prod_dict['links']['data'][0]['href']
                    return self._download_product(url, os.path.dirname(path), product.id)

            return None

        else:
            raise ValueError(
                "products are not in the right format for download by scrappi EUMDAC (ProductItem, ProductItemSet)"
            )

    def download_product_filename(
        self,
        product: Union[str, List],
        collection: str,
        fs: Optional[BaseFileSystem] = None,
    ) -> Optional[Union[list, str]]:
        """
        Download catalogue product(s) from query results to local path

        :param product: filename (id field in ProductItem)
        :param collection: collection name of product to download (ProductItem.collection)
        :param fs: file system to use when writing the data. Alternatively, an existing product path can be provided as a string. If nothing is provided, it defaults to the path of scrappi/examples/downloaded_data
        :return: path (or list of paths) to downloaded product(s)
        """

        if isinstance(product, list):
            return [self.download_product_filename(prod, fs) for prod in product]

        from scrappi import make_fs

        if fs:
            resolved_fs = make_fs(fs.directory, self.context)
        else:
            resolved_fs = make_fs(context=self.context)

        # next perform download based on type of product provided
        if product is None:
            warnings.warn("no product was provided to download")
            return None

        elif isinstance(product, str):
            found = False
            eumdac_product: Any = None
            product_prov = self.api.get_product(collection_id=collection, product_id=product)
            if len(product_prov) > 0:
                found = True
                eumdac_product = product_prov[0]

            if not found:
                warnings.warn(
                    "No product was found for %s. Please check the filename and ensure it is in the right format for scrappi EUMDAC download by filename (str). Do not include file extensions."
                    % (product,)
                )
                return None

            path = resolved_fs.directory

            return self._download_product(
                eumdac_product, path, eumdac_product._id
            )

        else:
            raise ValueError("products are not in the right format for filename download by scrappi EUMDAC (str)")
