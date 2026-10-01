"""scrappi.api.aws - AWS class for API call handler implementations"""

import os
import warnings
import shapely
import datetime as dt
from typing import Any, Optional, Union, List, Tuple
import boto3
import math
from botocore import UNSIGNED
from botocore.config import Config
import re
import numpy as np
from scrappi.api.base import BaseAPICallHandler
from scrappi.product import ProductItem, ProductItemSet
from scrappi import ScrappiContext
from scrappi.utils.utils import convert_geom_list
__all__ = ["AWSCallHandler"]


class AWSCallHandler(BaseAPICallHandler):
    """
    AWS-backed implementation of :class:`BaseAPICallHandler`.

    This handler provides access to publicly available datasets hosted on AWS
    S3, including:

    - ESA WorldCover
    - Copernicus DEM 30m
    - Copernicus DEM 90m

    Queries are translated into S3 bucket and object key searches and returned
    as :class:`ProductItem` objects.
    """

    name = "aws"

    WORLDCOVER_VERSION_YEAR = {
        100: 2020,
        200: 2021,
    }

    def __init__(
        self,
        context: Optional[Union[str, list, ScrappiContext]] = None,
    ) -> None:
        """
        Initialise the AWS API handler.

        Parameters
        ----------
        context : str | list | ScrappiContext, optional
            Scrappi execution context containing configuration and credentials.
        """
        super().__init__(context)

        self.collections = [
            "ESA_WorldCover",
            "Copernicus_dem_30m",
            "Copernicus_dem_90m",
        ]

        self.buckets = {
            "ESA_WorldCover": "esa-worldcover",
            "Copernicus_dem_30m": "copernicus-dem-30m",
            "Copernicus_dem_90m": "copernicus-dem-90m",
        }

        self.s3_resource = None

        try:
            self.s3_resource = boto3.resource(
                "s3",
                config=Config(signature_version=UNSIGNED),
            )
        except Exception:
            warnings.warn(
                "Could not establish connection to AWS resources.",
                stacklevel=2,
            )

    def _get_tiles(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        tile_size: int = 3,
    ) -> list[list[str]]:
        """
        Determine tiles intersecting a bounding box.

        Parameters
        ----------
        min_lon, min_lat, max_lon, max_lat : float
            Bounding box coordinates.
        tile_size : int
            Tile size in degrees (e.g. 3 for WorldCover, 1 for Copernicus DEM).

        Returns
        -------
        list[list[str]]
            Tile identifiers of the form [["N00", "E003"], ...].
        """

        lats = range(
            math.floor(min_lat / tile_size) * tile_size,
            math.floor(max_lat / tile_size) * tile_size + 1,
            tile_size,
        )

        lons = range(
            math.floor(min_lon / tile_size) * tile_size,
            math.floor(max_lon / tile_size) * tile_size + 1,
            tile_size,
        )

        tiles = []

        for lat in lats:
            for lon in lons:
                ns = "N" if lat >= 0 else "S"
                ew = "E" if lon >= 0 else "W"

                tiles.append(
                    [
                        f"{ns}{abs(lat):02d}",
                        f"{ew}{abs(lon):03d}",
                    ]
                )

        return tiles

    def _set_product_type(self, collection) -> str:
        return self.buckets[collection]

    def _set_geom(self, geom, collection) -> List[List[str]]:
        min_lon, min_lat, max_lon, max_lat = self._get_geom_bounds(geom)

        tile_size = 3 if "WorldCover" in collection else 1

        return self._get_tiles(
            min_lon,
            min_lat,
            max_lon,
            max_lat,
            tile_size=tile_size,
        )

    def _format_query(self, query: dict) -> dict:
        """
        Format input query to be aws compatible

        :param query: dict of query parameters (e.g. collection, start_time, stop_time, geom)
        :return: formatted query dict
        """

        aws_query = query.copy()
        aws_query["bucket"] = self._set_product_type(query["collection"])

        if "version" in query and "WorldCover" in query["collection"]:
            aws_query["version"] = query["version"]

            try:
                aws_query["start_time"] = self.WORLDCOVER_VERSION_YEAR[query["version"]]
            except KeyError:
                raise ValueError(
                    f"Version {query['version']} not supported for "
                    f"{query['collection']}. Available versions are: "
                    f"{list(self.WORLDCOVER_VERSION_YEAR.keys())}."
                )
        if query["geom"]:
            aws_query["tiles"] = self._set_geom(
                query["geom"],
                query["collection"],
            )
        return aws_query

    def list_collections(self) -> List:
        return self.collections

    def _perform_query(self, query: dict) -> list:
        """
        Return catalogue product DataGranules that satisfy query

        :param query: catalogue query
        :returns: product urls satisfying query
        """
        if self.s3_resource is None:
            raise RuntimeError("AWS S3 resource is not available.")

        aws_query = self._format_query(query)
        bucket = self.s3_resource.Bucket(aws_query["bucket"])

        if "tiles" not in aws_query.keys():
            return list(bucket.objects.all())

        # prefix will determin the spatial info
        tiles = aws_query["tiles"]
        products = []
        for tile in tiles:
            if "worldcover" in aws_query["bucket"]:
                product = list(
                    bucket.objects.filter(
                        Prefix=f"v{aws_query['version']}/{aws_query['start_time']}/map/ESA_WorldCover_10m_{aws_query['start_time']}_v{aws_query['version']}_{tile[0]}{tile[1]}_Map.tif"
                    )
                )
                if len(product) != 0:
                    products.append(product)
                else:
                    warnings.warn(f"Tile {tile[0]}_{tile[1]} not found.")
                    continue
            elif "dem" in aws_query["bucket"]:
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
                    constellation=self.get_constellation(prod_dict),  # Copernicus DEM
                    platform=self.get_platform(prod_dict),  # Copernicus DEM
                    collection=query["collection"],  # Copernicus DEM 30m
                    id=self._get_id(prod[0].key),  # first part of the key
                    geometry=self.tile_bbox(prod[0].key, tile_size=self._get_tile_size(query["collection"])).wkt,
                    start_time=self._get_time(prod[0].key),
                    stop_time=self._get_time(prod[0].key),
                    api=self,
                    context=self.context,
                    api_product={"bucket": prod[0].bucket_name, "key": self._get_api_product(prod[0].key)},
                )
            )

        return ProductItemSet(product_list)

    def _get_time(self, key: str) -> dt.datetime | None:
        if "DEM" in key.upper():
            return dt.datetime(2021, 1, 1)
        elif "worldcover" in key.lower():
            version_match = re.search(r"v(\d+)", key.lower())

            if version_match:
                version = int(version_match.group(1))
                year = self.WORLDCOVER_VERSION_YEAR.get(version)

                if year is not None:
                    return dt.datetime(year=year, month=1, day=1)

    def _get_api_product(self, key: str) -> str | None:
        if "DEM" in key.upper():
            return key.split("/")[0]
        elif "worldcover" in key.lower():
            return key

    def _get_id(self, key: str) -> str | None:
        if "DEM" in key.upper():
            return key.split("/")[0]
        elif "worldcover" in key.lower():
            return key.split("/")[-1]

    def get_platform(self, prod_dict: dict) -> str | None:
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

    def get_constellation(self, prod_dict: dict) -> str | None:
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

    def tile_bbox(self, key: str, tile_size: int = 1) -> shapely.Polygon:
        lat_m = re.search(r"([NS])(\d{2})", key)
        lon_m = re.search(r"([EW])(\d{3})", key)

        if not lat_m or not lon_m:
            raise ValueError(f"Could not extract tile coordinates from {key}")

        lat = int(lat_m.group(2))
        lon = int(lon_m.group(2))

        if lat_m.group(1) == "S":
            lat = -lat

        if lon_m.group(1) == "W":
            lon = -lon

        return shapely.box(
            lon,
            lat,
            lon + tile_size,
            lat + tile_size,
        )

    def _get_tile_size(self, collection: str) -> int:
        if "WorldCover" in collection:
            return 3
        elif "dem" in collection.lower():
            return 1
        else:
            raise ValueError(f"Unknown collection {collection}")

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
                bucket, key = search["bucket"], search["key"]
                return self._download(bucket, key, path)

            else:
                new_query = {
                    "collection": product.collection,
                    "geom": {
                        "latitude_minimum": product.geometry.bounds[1],
                        "longitude_minimum": product.geometry.bounds[0],
                        "latitude_maximum": product.geometry.bounds[3],
                        "longitude_maximum": product.geometry.bounds[2],
                    },
                }
                if product.collection=='ESA_WorldCover':
                    new_query["version"]=next((k for k, v in self.WORLDCOVER_VERSION_YEAR.items() if v == product.start_time.year), None)

                # search catalogue with query
                searchresult = self.perform_query(new_query)
                search_ids = np.array([prod.id for prod in searchresult])
                correct_ids = np.where(search_ids == product.id)[0]
                if len(correct_ids) == 0:
                    warnings.warn("no products found that satisfy download criterea")
                    return None
                elif len(correct_ids) > 1:
                    warnings.warn(
                        "multiple products found that satisfy download criterea (%s), only first will be downloaded."
                        % searchresult
                    )

                search = searchresult[0].api_product
                bucket, key = search["bucket"], search["key"]
                return self._download(bucket, key, path)

        else:
            raise ValueError(
                "products are not in the right format for download by scrappi earthaccess (ProductItem, ProductItemSet)"
            )

    def _download(self, bucket: str, key: str, path: str) -> str:
        s3_client = boto3.client("s3", config=Config(signature_version=UNSIGNED))
        s3_bucket = self.s3_resource.Bucket(bucket)
        products = list(s3_bucket.objects.filter(Prefix=key))

        if len(products) == 1:
            if "worldcover" in products[0].key.lower():
                os.makedirs(os.path.dirname(path), exist_ok=True)
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

    def _get_filename(self, key: str) -> str | None:
        if "DEM" in key.upper():
            return os.path.join(*key.split("/")[1:])
        elif "worldcover" in key.lower():
            return key
