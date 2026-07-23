"""scrappi.api.aws - AWS class for API call handler implementations"""

import os
import warnings
import shapely
import shapely.wkt
import shapely.geometry
import time
import numpy as np
import datetime as dt
from shapely.geometry import Polygon, MultiPolygon
from typing import Any, Optional, Union, List
import boto3
import math
from botocore import UNSIGNED
from botocore.config import Config
import re
from scrappi.api.base import BaseAPICallHandler
from scrappi.product import ProductItem, ProductItemSet
from scrappi.fs.base import BaseFileSystem
from scrappi import ScrappiContext

_all_=["AWSCallHandler"]

class AWSCallHandler(BaseAPICallHandler):
    """
    Class for AWS call handler implementations. Extend `BaseAPICallHandler`.

    """
    
    # query is just bucket, key 
    # spatial filterng is not going into the query
    #
    name = "aws"
    def __init__(self, context: Optional[Union[str, List, ScrappiContext]] = None):

        super().__init__(context)
        self.collections = ["ESA_WorldCover", "Copernicus-dem-30m", "Copernicus-dem-90m"]
        self.buckets = {"ESA_WorldCover":"esa-worldcover",
                                    "Copernicus-dem-30m": "copernicus-dem-30m", 
                                    "Copernicus-dem-90m": "copernicus-dem-90m"}

        try:
            #os.environ["EARTHDATA_USERNAME"] = self.context["earthaccess"]["credentials"]["username"]
            #os.environ["EARTHDATA_REMOVED_PASSWORD"] = self.context["earthaccess"]["credentials"]["password"]
            self.s3_resource = boto3.resource('s3', config=Config(signature_version=UNSIGNED))
            
        except Exception as e:
            warnings.warn(
                "Could not establish connection to AWS resources."
            )

    def return_path(self, product_item: ProductItem, check_exists: bool = False):
        """
        Returns path from info in ProductItem

        :param product_info: productItem defining info, including ``"product_name"`` and ``"datetime"``
        :param check_exists: if true, returns None if product not in archive
        :return: product path
        """
        pass
    
    def _worldcover_tiles(self, min_lon, min_lat, max_lon, max_lat):
        lats = range(
            math.floor(min_lat / 3) * 3,
            math.floor(max_lat / 3) * 3 + 1,
            3,
        )

        lons = range(
            math.floor(min_lon / 3) * 3,
            math.floor(max_lon / 3) * 3 + 1,
            3,
        )

        tiles = []

        for lat in lats:
            for lon in lons:
                ns = "N" if lat >= 0 else "S"
                ew = "E" if lon >= 0 else "W"

                tiles.append(
                    [f"{ns}{abs(lat):02d}",
                    f"{ew}{abs(lon):03d}"]
                )
        return tiles
    
    def _get_keys(self, tiles):
        # get from the query
        version = self._get_version() # v100
        year = self._get_year() #2020

        keys = []
        for tile in tiles:
            keys.append(
                f"{version}/{year}/map/"
                f"ESA_WorldCover_10m_{year}_{version}_"
                f"{tile}_Map.tif"
            )
        return keys
    
    def _get_version(self):
        pass

    def _get_year(self):
        pass
    def _set_product_type(self, collection):
        return self.buckets[collection]
    
    def _set_geom(self, geom):
        if isinstance(geom, list):
            min_lat, min_lon, max_lat, max_lon = geom
        
        if isinstance(geom, dict):
            min_lat, min_lon, max_lat, max_lon = geom['latitude_minimum'], geom['longitude_minimum'], geom["latitude_maximum"], geom["longitude_maximum"]
        
        tiles = self._worldcover_tiles(min_lon, min_lat, max_lon, max_lat)
        return tiles
    
    def _format_query(self, query: dict) -> dict:
        """
        Format input query to be aws compatible

        :param query: dict of query parameters (e.g. collection, start_time, stop_time, geom)
        :return: formatted query dict
        """
        # translate to the bucket and a key
        #
        aws_query = query.copy()
        aws_query["bucket"] = self._set_product_type(query["collection"])
        #aws_query["date"] = (
        #    self._set_datetime(query["start_time"]),
        #    self._set_datetime(query["stop_time"]),
        #)
        if "version" in query.keys() and "WorldCover" in query['collection']:
            aws_query["version"] = query["version"] 
            if query["version"] == 200:
                aws_query['start_time'] = 2021
            elif query["version"] == 100:
                aws_query['start_time'] = 2020
            else:
                raise ValueError(f"Version {query["version"]} not supported for {query['collection']}. Available versions are: 100, 200.")

        if query["geom"]:
            aws_query["tiles"] = self._set_geom(query["geom"]) # List of lists of tiles["NS", "EW"]

        return aws_query
    
    def list_collections(self) -> List:
        return self.collections

    def _perform_query(self, query: dict) -> list:
        """
        Return catalogue product DataGranules that satisfy query

        :param query: catalogue query
        :returns: product urls satisfying query
        """

        # reformat query into style suitable for earthaccess searching
        aws_query = self._format_query(query)
        # ["bucket", "version", "tiles"
        # Bucket, key, filter?
        #Copernicus_DSM_COG_10_N09_00_W063_00_DEM
        #v100/2020/map/ESA_WorldCover_10m_2020_v100_N00E006_Map.tif
        bucket = self.s3_resource.Bucket(aws_query['bucket'])

        if "tiles" not in aws_query.keys():
            return list(bucket.objects.all())
    
        # prefix will determin the spatial info
        tiles = aws_query['tiles']
        products = []
        for tile in tiles:
            if "worldcover" in aws_query['bucket']:
                product = list(bucket.objects.filter(Prefix=f"v{aws_query['version']}/{aws_query['start_time']}/map/ESA_WorldCover_10m_{aws_query['start_time']}_v{aws_query['version']}_{tile[0]}{tile[1]}_Map.tif"))
                if len(product) != 0:
                    products.append(product)
                else:
                    warnings.warn(f"Tile {tile[0]}_{tile[1]} not found.")
                    continue
            elif "dem" in aws_query['bucket']:
                product = list(bucket.objects.filter(Prefix=f"Copernicus_DSM_COG_10_{tile[0]}_00_{tile[1]}_00_DEM"))
                if len(product) != 0:
                    products.append(product)
                else:
                    warnings.warn(f"Tile {tile[0]}_{tile[1]} not available (most likely it is an ocean tile).")
                    continue
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

        aws_objects_list = self._perform_query(query)

        if len(aws_objects_list) == 0:
            return ProductItemSet()

        product_list = []
        for i, prod in enumerate(aws_objects_list):
            prod_dict = prod

            # store product item
            product_list.append(
                ProductItem(
                    constellation=self.get_constellation(prod_dict), #Copernicus DEM
                    platform=self.get_platform(prod_dict), #Copernicus DEM
                    collection=query["collections"][0], # Copernicus DEM 30m
                    id=self._get_id(prod[0].key), # first part of the key
                    geometry=self.tile_bbox(prod[0].key).wkt,
                    start_time= self._get_time(prod[0].key),
                    stop_time=self._get_time(prod[0].key),
                    api=self,
                    context=self.context,
                    api_product={"bucket":prod[0].bucket_name, "key":self._get_api_product(prod[0].key)},
                )
            )

        return ProductItemSet(product_list)
    
    def _get_time(self, key):
        if "DEM" in key.upper():
            return dt.datetime(2021, 1, 1)
        elif "worldcover" in key.lower():
            if "v100" in key.lower():
                return dt.datetime(year=2020, month=1, day=1)
            elif "v200" in key.lower():
                return dt.datetime(year=2021, month=1, day=1)
            
    def _get_api_product(self, key):
        if "DEM" in key.upper():
            return key.split("/")[0]
        elif "worldcover" in key.lower():
            return key
        
    def _get_id(self, key):
        if "DEM" in key.upper():
            return key.split("/")[0]
        elif "worldcover" in key.lower():
            # need to change the id as it is being used for the path organising
            # 
            return key.split("/")[-1]
        
    def get_platform(self, prod_dict: dict) -> str:
        """
        Function to extract to platform identifier

        :param prod_dict: earthaccess product dictionary
        :return: platform identifier
        """
        try:
            if isinstance(prod_dict, list):
                if "dem" in prod_dict[0].bucket_name:
                    return "Copernicus_DEM"
                elif "worldcover" in prod_dict[0].bucket_name:
                    return "ESA_WorldCover"
        except NotImplementedError:
            raise NotImplementedError("platform name could not be parsed")

    def get_constellation(self, prod_dict: dict) -> str:
        """
        Function to extract constellation identifier

        :param prod_dict: earthaccess product dictionary
        :return: constellation identifier
        """

        try:
            if isinstance(prod_dict, list):
                if "dem" in prod_dict[0].bucket_name:
                    return "Copernicus_DEM"
                elif "worldcover" in prod_dict[0].bucket_name:
                    return "ESA_WorldCover"
        except NotImplementedError:
            raise NotImplementedError("platform name could not be parsed")
        
    def tile_bbox(self, key):
        lat_m = re.search(r'([NS])(\d{2})', key)
        lon_m = re.search(r'([EW])(\d{3})', key)

        if not lat_m or not lon_m:
            raise ValueError(f"Could not extract tile coordinates from {key}")

        lat = int(lat_m.group(2))
        lon = int(lon_m.group(2))

        if lat_m.group(1) == "S":
            lat = -lat
        if lon_m.group(1) == "W":
            lon = -lon

        return shapely.box(lon, lat, lon + 1, lat + 1)
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

            elif product.api_product is not None:
                search = product.api_product
                bucket, key = search['bucket'], search['key']
                return self._download(bucket, key, path)
        else:
            raise ValueError(
                "products are not in the right format for download by scrappi earthaccess (ProductItem, ProductItemSet)"
            )
    def _download(self, bucket, key, path):

        s3_client = boto3.client('s3', config=Config(signature_version=UNSIGNED))
        s3_bucket = self.s3_resource.Bucket(bucket)
        products = list(s3_bucket.objects.filter(Prefix=key))

        if len(products) == 1:
            # path from fs and the key
            if "worldcover" in products[0].key.lower():
                #filename = os.path.join(path, self._get_filename(products[0].key))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                #s3_client.download_file(Bucket=bucket, Key=products[0].key, Filename=path)
                s3_client.download_file(bucket, products[0].key, path)
                return path
            else:
                filename = os.path.join(path, self._get_filename(products[0].key))
                os.makedirs(os.path.dirname(filename), exist_ok=True)
                s3_client.download_file(Bucket=bucket, Key=products[0].key, Filename=filename)
                return filename
        else:
            for prod in products:
                filename = os.path.join(path, self._get_filename(prod.key))
                os.makedirs(os.path.dirname(filename), exist_ok=True) 
                s3_client.download_file(Bucket=bucket, Key=prod.key, Filename=filename)
                # filename of the last one
            return os.path.dirname(os.path.dirname(filename))

    def _get_filename(self, key):
        if "DEM" in key.upper():
            return "\\".join(key.split("/")[1:])
        elif "worldcover" in key.lower():
            return key
   