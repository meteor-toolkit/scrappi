"""Product item and product set utilities.

This module defines `ProductItem` and `ProductItemSet`, the canonical in-
memory representations of catalogue search results in scrappi. A
`ProductItem` encapsulates spatial/temporal metadata, asset hrefs and
provider-specific metadata. `ProductItemSet` is a light-weight container
with helpers for filtering, sorting and STAC materialisation.
"""

import warnings
import json
from typing import Dict, Any, Optional, Sequence, Union, List, Tuple, NamedTuple
from typing_extensions import Self
import datetime as dt
import shapely as sh
from shapely.geometry import Polygon, MultiPolygon, Point, mapping
import pystac
from matplotlib.axes import Axes
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
from matplotlib import pyplot as plt
import os.path
import cartopy.crs as ccrs
import numpy as np
import shutil
from processor_tools.utils.formatters import convert_datetime
from pathlib import Path

from scrappi.utils.plot_utils import pad_plot_bounds, prepare_map_plot
from scrappi import ScrappiContext
from scrappi.fs.stac_href_resolver import StacHrefResolver

__author__ = "Sam Hunt <sam.hunt@npl.co.uk>"
__all__ = [
    "ProductItem",
    "ProductItemSet",
    "open_product_item",
    "open_product_item_set",
    "product_item_from_dict",
    "product_item_set_from_dict",
]


class ProductItem:
    """
    Object representing a product item in a data catalogue

    :param platform: platform the product was measured by
    :param collection: dataset product belongs to
    :param id: unique ID of product within collection
    :param geometry: spatial extent covered by product, as a :py:class:`shapely.Polygon`, WKT string, or value to instantiate a :py:class:`shapely.Polygon`
    :param start_time: initial time-bound of product
    :param stop_time: final time-bound of product
    :param prod_dict: all information returned by query, will not be saved to JSON
    :param filter_dict: dictionary with attributes that can be used to filter the data
    :param url: optional keyword to provide download url
    :param quicklook: optional keyword to provide quickook url
    :param filesystem: optional keyword to set filesystem, defaults to t-drive filesystem
    :param organise_data: When a path is provided as a string (or when using default) instead of a filesystem, the organise_data boolean decides whether the data is organised by collection/year/month/day or not. Defaults to True.
    :param api: optional keyword to set api, defaults to eodag
    """

    def __init__(
        self,
        constellation: str,
        platform: str,
        collection: str,
        id: str,
        geometry: Union[Polygon, Sequence, str],
        start_time: Union[dt.datetime, str],
        stop_time: Union[dt.datetime, str],
        prod_dict: Optional[Dict] = None,
        filter_dict: Optional[Dict] = {},
        version: Optional[str] = None,
        url: Optional[str] = "",
        quicklook: Optional[str] = "",
        filesystem: Optional[str] = None,
        api: Optional[str] = None,
        cloud_fraction: Optional[float] = None,
        context: Optional[ScrappiContext] = None,
        api_product: Optional[Any] = None,
    ):
        self.constellation = constellation
        self.platform = platform
        self.collection = collection
        self.version = version
        self.id = id
        self._geometry: Union[Polygon, Sequence, str] = geometry
        self.start_time = convert_datetime(start_time)
        self.stop_time = convert_datetime(stop_time)
        self.prod_dict = prod_dict
        self.filter_dict = filter_dict
        self.url = url
        self.quicklook = quicklook
        self.cloud_fraction = cloud_fraction
        self.api_product = api_product
        if not context:
            self.context = ScrappiContext()
        else:
            self.context = context
        self.set_api(api, context)
        self.set_fs(filesystem, context)

    def __str__(self) -> str:
        """Custom __str__"""

        repr_str = "<scrappi.ProductItem>\nid:\t\t{}\ncollection:\t{}\nstart_time:\t{}\nstop_time:\t{}".format(
            self.id, self.collection, self.start_time, self.stop_time
        )

        return repr_str

    def __repr__(self) -> str:
        """Custom  __repr__"""

        return str(self)

    def to_json(self, path: Optional[str] = None) -> dict:
        """
        Prepare JSON representation of ProductItem

        :param path: (optional) if set write JSON object to this file path
        :return: JSON representation of ProductItem as a dictionary
        """

        product_item_dict = dict()

        product_item_dict["constellation"] = self.constellation
        product_item_dict["platform"] = self.platform
        product_item_dict["collection"] = self.collection
        product_item_dict["id"] = self.id
        product_item_dict["geometry"] = self.geometry.wkt
        product_item_dict["start_time"] = self.start_time.isoformat()
        product_item_dict["stop_time"] = self.stop_time.isoformat()
        product_item_dict["url"] = self.url
        product_item_dict["quicklook"] = self.quicklook
        product_item_dict["prod_dict"] = self.prod_dict
        product_item_dict["filter_dict"] = self.filter_dict

        if path is not None:
            with open(path, "w") as f:
                json.dump(product_item_dict, f, indent=2)

        return product_item_dict

    @property
    def stac(self) -> "pystac.Item":
        """Return a pystac.Item representing this ProductItem."""
        return self.to_stac_item()

    def to_stac_item(
        self,
        filesystem: Optional["STACFileSystem"] = None,
        overwrite: bool = False,
    ) -> "pystac.Item":
        """
        Convert this ProductItem to a pystac.Item. Read existing file if available

        :param assets: optional mapping of asset_key -> {href, media_type, title}
        :return: `pystac.Item` representing the product
        """
        fs = filesystem or self.filesystem
        if fs is None:
            raise ValueError("No filesystem provided")

        item_path = fs.return_stac_item_path(self)
        if os.path.exists(item_path) and not overwrite:
            stac_item = pystac.Item.from_file(item_path)

        else:
            stac_item = self.to_new_stac_item(fs)

        return stac_item

    def to_new_stac_item(self, fs):
        # GeoJSON geometry and bbox
        geom = mapping(self.geometry)
        bbox = list(self.geometry.bounds)

        # Properties - include product metadata
        properties = {}
        properties["constellation"] = self.constellation
        properties["platform"] = self.platform
        # properties["collection"] = self.collection
        if self.context["fs"].get("store_prod_dict_in_stac", False):
            properties["prod_dict"] = self.prod_dict or {}
        if self.context["fs"].get("store_filter_dict_in_stac", False):
            properties["filter_dict"] = self.filter_dict or {}

        # Create STAC Item (use start_time as datetime; stop_time added to properties)
        item = pystac.Item(
            id=self.id,
            geometry=geom,
            bbox=bbox,
            datetime=self.start_time,
            properties=properties,
        )

        # add end time as property when available
        if self.stop_time is not None:
            item.properties["end_datetime"] = self.stop_time.isoformat()

        # ---------------- Item ----------------
        asset_disk_path = fs.return_path(self)
        if os.path.exists(asset_disk_path):
            data_root = Path(fs.data_root)
            rel_asset_path = Path(asset_disk_path).relative_to(data_root)

            if self.context["fs"]["use_relative_stac_paths"]:
                item.add_asset(
                    "data",
                    pystac.Asset(
                        href=fs.asset_href(*rel_asset_path.parts),
                        media_type="application/file",
                        title="data",
                        extra_fields={"scrappi:asset_state": "downloaded"},
                    ),
                )
            else:
                item.add_asset(
                    "data",
                    pystac.Asset(
                        href=fs.return_path(self),
                        media_type="application/file",
                        title="data",
                        extra_fields={"scrappi:asset_state": "downloaded"},
                    ),
                )

        # Add URL / quicklook as common assets when present
        if self.url and "data" not in item.assets:
            item.add_asset(
                "data",
                pystac.Asset(
                    href=self.url,
                    media_type="application/octet-stream",
                    title="data",
                    extra_fields={"scrappi:asset_state": "remote"},
                ),
            )

        if self.quicklook and "quicklook" not in item.assets:
            item.add_asset(
                "quicklook",
                pystac.Asset(href=self.quicklook, media_type="image/jpeg", title="quicklook"),
            )

        return item

    @staticmethod
    def expand_spatial_extent(extent, bounds):
        """
        extent: pystac.Extent
        bounds: (minx, miny, maxx, maxy)
        """
        cur_bbox = extent.spatial.bboxes[0]

        extent.spatial.bboxes[0] = [
            min(cur_bbox[0], bounds[0]),
            min(cur_bbox[1], bounds[1]),
            max(cur_bbox[2], bounds[2]),
            max(cur_bbox[3], bounds[3]),
        ]

    @staticmethod
    def expand_temporal_extent(extent, start_time, end_time):
        cur_interval = extent.temporal.intervals[0]

        cur_start, cur_end = cur_interval
        new_start = min(filter(None, [cur_start, start_time]))
        new_end = max(filter(None, [cur_end, end_time]))

        extent.temporal.intervals[0] = [new_start, new_end]

    def register_in_filesystem_catalog(
        self,
        filesystem: Optional["STACFileSystem"] = None,
        overwrite: bool = True,
    ) -> str:
        fs = filesystem or self.filesystem
        if fs is None:
            raise ValueError("No filesystem provided")

        # Filesystem locations (only used for writing)
        stac_root = Path(fs.stac_root)
        data_root = Path(fs.data_root)

        item_path = fs.return_stac_item_path(self)
        collection_json = stac_root / self.collection / "collection.json"
        root_catalog_json = stac_root / "catalog.json"

        collection_json.parent.mkdir(parents=True, exist_ok=True)
        Path(item_path).parent.mkdir(parents=True, exist_ok=True)
        stac_root.mkdir(parents=True, exist_ok=True)

        # ---------------- Root catalog ----------------
        if root_catalog_json.exists():
            root = pystac.Catalog.from_file(root_catalog_json)
        else:
            root = pystac.Catalog(
                id="scrappi-root",
                description="Root STAC catalog for scrappi",
            )

        root.set_self_href(fs.stac_href("catalog.json"))

        # ---------------- Collection ----------------
        if collection_json.exists():
            collection = pystac.Collection.from_file(collection_json)
        else:
            collection = pystac.Collection(
                id=self.collection,
                description=f"Collection {self.collection}",
                extent=pystac.Extent(
                    spatial=pystac.SpatialExtent([list(self.geometry.bounds)]),
                    temporal=pystac.TemporalExtent([[self.start_time, self.stop_time or self.start_time]]),
                ),
                license="other",
            )

            collection.extra_fields["constellation"] = self.constellation
            collection.extra_fields["platform"] = self.platform

        collection.set_self_href(fs.stac_href("collections", self.collection, "collection.json"))

        # ---------------- Item ----------------
        item = self.to_stac_item(filesystem=filesystem, overwrite=True)

        item_rel_path = Path(item_path).relative_to(stac_root)
        item.set_self_href(fs.stac_href(*item_rel_path.parts))

        if Path(item_path).exists() and not overwrite:
            raise RuntimeError(f"STAC item already exists: {item_path}")

        item.save_object(dest_href=item_path)

        # ---------------- Link item from collection ----------------
        if not any(l.rel == "item" and l.target == item.get_self_href() for l in collection.links):
            collection.add_link(
                pystac.Link(
                    rel="item",
                    target=item.get_self_href(),
                    media_type="application/geo+json",
                )
            )

        self.expand_spatial_extent(collection.extent, self.geometry.bounds)
        self.expand_temporal_extent(
            collection.extent,
            self.start_time,
            self.stop_time,
        )

        StacHrefResolver.write_stac_object(collection, collection_json)

        # ---------------- Link collection from root ----------------
        if not any(l.rel == "child" and l.target == collection.get_self_href() for l in root.links):
            root.add_link(
                pystac.Link(
                    rel="child",
                    target=collection.get_self_href(),
                    media_type="application/json",
                )
            )

        StacHrefResolver.write_stac_object(root, root_catalog_json)

        return str(item_path)

    def set_fs(
        self,
        filesystem: Optional[str] = None,
        context: ScrappiContext = None,
    ):
        """
        set filesystem

        """
        from scrappi.interface import make_fs

        self.filesystem = make_fs(filesystem, context)
        self.context["fs"]["path"] = self.filesystem.directory

    def set_api(self, api: Optional[str] = None, context: ScrappiContext = None):
        """
        set API

        :param api: keyword to set api
        :param credentials: API or auth and download credentials for providers
        :param config_dict: config dictionary (api dependent)
        """
        from scrappi.interface import make_api

        self.api = make_api(api, context)

    def move_product(self, new_fs: str, copy: bool = True) -> str:
        """
        Move or copy the file to a different filesystem

        :param new_fs: new filesystem, provided as name, path, or object
        :param copy: Boolean to indicate if the product should be copied (True) or moved (False)
        :return: path to product in new filesystem
        """
        from scrappi.interface import make_fs

        new_fs = make_fs(new_fs)

        old_path, exists = self.filesystem.return_path(self, True)
        if not exists:
            warnings.warn(
                "The product does not exist in the current file system (%s) and "
                "might still need to be downloaded. Returning empty string" % old_path
            )
            return ""

        new_path = new_fs.return_path(self, False)

        if copy:
            if new_fs.read_only:
                raise IOError("The new filesystem you are trying to copy data to is read only.")
            else:
                self.mk_fs_dirs(new_path)
                shutil.copy(old_path, new_path)
        else:
            if new_fs.read_only:
                raise IOError("The new filesystem you are trying to move data to is read only.")
            elif self.filesystem.read_only:
                raise IOError(
                    "The old filesystem you are trying to move data from is read only (maybe try setting copy=True instead)."
                )
            else:
                self.mk_fs_dirs(new_path)
                shutil.move(old_path, new_path)

        self.set_fs(new_fs)
        return new_path

    def mk_fs_dirs(self, p) -> bool:
        dirname = os.path.dirname(p)
        if not os.path.exists(dirname):
            from os import makedirs

            makedirs(dirname)

    def get_path(self) -> str:
        """
        return path to filesystem main folder

        :return: path to filesystem main folder
        """
        from scrappi.interface import make_fs

        return make_fs(self.filesystem).return_path(self, False)

    def download_product(self, context: ScrappiContext = None):
        """
        Function to download product using api and fs set in attributes
        :return: path to downloaded product
        """
        from scrappi.interface import download_product

        return download_product(self, context=context)

    @property
    def geometry(self) -> Polygon:
        """
        return geometry of product

        :return: geometry as polygon
        """
        # get polygon if exists
        if isinstance(self._geometry, (Polygon, MultiPolygon, Point)):
            pass

        # if provided as WKT load
        elif isinstance(self._geometry, str):
            self._geometry = sh.wkt.loads(self._geometry)

        # else assume Polygon buildable sequence
        else:
            try:
                self._geometry = Polygon(self._geometry)
            except:
                raise ValueError("Unable to form <shapely.Polygon> from geometry")

        return self._geometry

    def plot_geometry(
        self,
        ax: Optional[Axes] = None,
        padding_type: Optional[str] = "rel",
        padding_val: Optional[Union[float, str]] = 0.5,
        tick_step: Optional[float] = None,
        geometry_color: Optional[str] = None,
    ) -> None:
        """
        Plots product geometry on lon lat grid

        :param ax: plot axes object
        :param padding_val: padding value (as required by :py:func:`~scrappi.utils.plot_utils.pad_plot_bounds()`)
        :param padding_type: padding type (as required by :py:func:`~scrappi.utils.plot_utils.pad_plot_bounds()`)
        :param tick_step: plot lat, lon axis tick separation
        :param geometry_color: name of colour to draw geometry in

        Used as:

        .. code-block:: python

           from matplotlib import pyplot as plt
           from scrappi import ProductItem
           p = ProductItem(...)
           p.plot_geometry()
           plt.show()
        """

        # If Axes object not provided, build plot
        if ax is None:
            plt.figure()
            ax = plt.axes(projection=ccrs.PlateCarree())
            projection = ccrs.PlateCarree()

            # Set plot bounds
            # existing bounds (if applicable)
            (
                plot_lon_min_pre,
                plot_lon_max_pre,
                plot_lat_min_pre,
                plot_lat_max_pre,
            ) = ax.get_extent()

            (
                plot_latitude_minimum,
                plot_longitude_minimum,
                plot_latitude_maximum,
                plot_longitude_maximum,
            ) = pad_plot_bounds(self.geometry.bounds, padding_type, padding_val)

            ax.set_extent(
                [
                    min(plot_longitude_minimum, plot_lon_min_pre),
                    max(plot_longitude_maximum, plot_lon_max_pre),
                    min(plot_latitude_minimum, plot_lat_min_pre),
                    max(plot_latitude_maximum, plot_lat_max_pre),
                ]
            )

            # Add map styling
            prepare_map_plot(ax, tick_step=tick_step)

        else:
            projection = ccrs.PlateCarree()

            # if ax._projection_init[1] == {}:
            #     raise ValueError(
            #         """
            #         Input ax must contain a cartopy.crs projection. For example plt.axes(projection=cartopy.crs.PlateCarree()).
            #     """
            #     )
            #
            # else:
            #     projection = ax._projection_init[1]["projection"]

        # Draw geometry
        ax.add_geometries(self.geometry.exterior, crs=projection, alpha=0.4, color=geometry_color)

        plt.tight_layout()


class ProductItemSet:
    """
    Container for a set of :py:class:`~scrappi.product.ProductItem`

    :param products: products to add to the set
    """

    def __init__(self, products: Optional[List[ProductItem]] = None):
        # Initialise attributes
        self._products: List[ProductItem] = products if products is not None else []
        self._collections: Union[None, List[str]] = None

    def __str__(self) -> str:
        """Custom __str__"""

        repr_str = "<scrappi.ProductItemSet (n_prods: {})>\nProducts:".format(len(self))

        if len(self) < 10:
            for p in self:
                repr_str += "\n\t{}".format(p.id)

        else:
            for idx in [0, 1, 2, -3, -2, -1]:
                if idx == -3:
                    repr_str += "\n..."
                else:
                    repr_str += "\n\t{}".format(self[idx].id)

        return repr_str

    def __repr__(self) -> str:
        """Custom  __repr__"""

        return str(self)

    def __getitem__(self, idx):
        return self._products[idx]

    def __len__(self):
        return len(self._products)

    def __iter__(self):
        """Custom  __iter__"""

        self.i = 0  # Define counter
        return self

    def __next__(self) -> ProductItem:
        """
        Returns ith product item in product item set

        :return: ith product item
        """

        # Iterate through flag variable flags
        if self.i < len(self):
            self.i += 1  # Update counter
            return self[self.i - 1]

        else:
            raise StopIteration

    def to_json(self, path: Optional[str] = None) -> dict:
        """
        Prepare JSON representation of ProductItemSet

        :param path: (optional) if set write JSON object to this file path
        :return: JSON representation of ProductItemSet as a dictionary
        """

        product_item_set_dict = dict()

        product_item_set_dict["collections"] = self.collections
        product_item_set_dict["n_products"] = len(self)

        (
            product_item_set_dict["longitude_minimum"],
            product_item_set_dict["latitude_minimum"],
            product_item_set_dict["lon_maximum"],
            product_item_set_dict["lat_maximmum"],
        ) = self.product_bounds

        products = []
        for p in self:
            products.append(p.to_json())

        product_item_set_dict["products"] = products

        if path is not None:
            with open(path, "w") as f:
                json.dump(product_item_set_dict, f, indent=2)

        return product_item_set_dict

    def append_ProductItemSet(self, productset: Self):
        """
        Append provided ProductItemSet to self.products

        :param productset: ProductItemSet to be appended
        """

        self._products.extend(productset._products)

    def add_ProductItem(self, productitem: ProductItem):
        """
        Append provided ProductItem to self.products

        :param productset: ProductItem to be appended
        """

        self._products.append(productitem)

    def remove_ProductItem(self, ProductItem: ProductItem):
        """
        Remove provided ProductItem from self.products

        :param productset: ProductItem to be appended
        """

        self._products.remove(ProductItem)

    def set_api(self, api: str):
        """
        set API for each product item in the product item set

        :param api: keyword to set api
        """
        for p in self:
            p.set_api(api)

    def set_fs(self, filesystem: str, context: ScrappiContext = None):
        """
        set filesystem for each product item in the product item set

        :param filesystem: filesystem, provided as name, path, or object
        :param organise_data: When a path is provided as a string (or when using default) instead of a filesystem, the organise_data boolean decides whether the data is organised by collection/year/month/day or not. Defaults to True.
        """
        for p in self:
            p.set_fs(filesystem, context)

    def move_product(self, new_fs, copy: bool = True) -> List:
        """
        Move or copy all products to a different filesystem

        :param new_fs: new filesystem, provided as name, path, or object
        :param copy: Boolean to indicate if the product should be copied (True) or moved (False)
        :return: list of path to products in new filesystem
        """
        return [p.move_product(new_fs, copy) for p in self]

    def cloud_filter(self, cloud_threshold):
        """
        Function to remove products with cloud cover above a desired threshold

        :param cloud_threshold: float as a percentage for maximum cloud cover allowed
        :returns: ProductItemSet: ProductItemSet with products containing cloud removed
        """
        # for sentinel products
        for p in self._products[:]:
            if p.filter_dict["cloud_fraction"] > cloud_threshold:
                self.remove_ProductItem(p)

        return self

    def get_path(self) -> str:
        """
        return path to filesystem main folder

        :return: path to filesystem main folder
        """
        return [p.get_path() for p in self]

    def download_product(
        self,
        credentials: dict = None,
        config_dict: dict = None,
    ):
        """
        Function to download product using api and fs set in attributes
        :param credentials: dictionary with credentials
        :param config_dict: eodag config YAML file (default file is in home directory, ".config", "eodag", "eodag.yml")
        :return: path to downloaded product
        """
        return [p.download_product() for p in self]

    def to_stac_catalog(
        self,
        filesystem: Optional[Any] = None,
        catalog_id: str = "scrappi-productset",
        description: Optional[str] = None,
        materialise_missing_items: bool = False,
    ) -> pystac.Catalog:
        """
        Create a STAC Catalog representing this ProductItemSet.

        This catalog is created IN MEMORY by default.
        It may link to existing filesystem-backed STAC Items, or create
        in-memory Items if needed.

        Nothing is written to disk unless save() is explicitly called.
        """

        if description is None:
            description = f"STAC catalog for ProductItemSet ({len(self)} items)"

        catalog = pystac.Catalog(
            id=catalog_id,
            description=description,
        )

        fs = filesystem

        # Group products by collection
        collections_map: Dict[str, List[ProductItem]] = {}
        for p in self:
            collections_map.setdefault(p.collection, []).append(p)

        for collection_id, products in collections_map.items():
            # Compute extent
            bboxes = [p.geometry.bounds for p in products]
            spatial_extent = [
                min(b[0] for b in bboxes),
                min(b[1] for b in bboxes),
                max(b[2] for b in bboxes),
                max(b[3] for b in bboxes),
            ]

            temporal_extent = [
                min(p.start_time for p in products),
                max(p.stop_time or p.start_time for p in products),
            ]

            collection = pystac.Collection(
                id=collection_id,
                description=f"Ephemeral collection {collection_id}",
                extent=pystac.Extent(
                    spatial=pystac.SpatialExtent([spatial_extent]),
                    temporal=pystac.TemporalExtent([temporal_extent]),
                ),
                license="other",
            )

            catalog.add_child(collection)

            for p in products:
                item = None

                if fs is not None:
                    try:
                        item_path = fs.return_stac_item_path(p)
                        if os.path.exists(item_path):
                            item = pystac.Item.from_file(item_path)
                    except Exception:
                        item = None

                if item is None:
                    if not materialise_missing_items:
                        continue
                    item = p.to_stac_item()

                collection.add_item(item)

        return catalog

    def save_stac_catalogue(catalog, path):
        catalog.set_self_href(path)
        catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)

    def update_filesystem_catalogs(
        self,
        filesystem: Optional[Any] = None,
        overwrite: bool = False,
    ) -> str:
        """
        Register all ProductItems in this set into filesystem-based STAC collections.

        :param filesystem: optional BaseFileSystem instance to use (defaults to each item's filesystem)
        :param root_stac_dir_name: name of folder under filesystem.directory to store STAC data
        :param overwrite: pass to item registration to overwrite existing item JSONs
        """
        root_catalog_path = None
        for p in self:
            fs = filesystem if filesystem is not None else p.filesystem
            item_path = p.register_in_filesystem_catalog(filesystem=fs, overwrite=overwrite)

    @property
    def collections(self) -> List[str]:
        """
        Set of collections from which the set product items originate

        :return: Set collections
        """
        if self._collections is not None:
            pass

        else:
            collections = set()
            for p in self:
                collections.add(p.collection)

            self._collections = list(collections)
            self.collections.sort()

        return self._collections

    @property
    def product_bounds(self) -> Tuple[float, float, float, float]:
        """
        Returns minimum bounding region of set product items

        :return: bounding region of products (longitude_minimum, latitude_minimum, longitude_maximum, latitude_maximmum)
        """

        longitude_minimums = []
        latitude_minimums = []
        longitude_maximums = []
        latitude_maximums = []

        for p in self:
            p_lon_min, p_lat_min, p_lon_max, p_lat_max = p.geometry.bounds

            longitude_minimums.append(p_lon_min)
            latitude_minimums.append(p_lat_min)
            longitude_maximums.append(p_lon_max)
            latitude_maximums.append(p_lat_max)

        product_bounds = (
            min(longitude_minimums),
            min(latitude_minimums),
            max(longitude_maximums),
            max(latitude_maximums),
        )

        return product_bounds

    def argsort(self, sort_by: str):
        """
        Returns order indices of the ProductItems by defined parameter

        :param sort_by: parameter to sort by, may be:

        * `"collection"` - alphabetical order by collection products are in
        * `"id"` - alphabetical order by product ID
        * `"start_time"` - time ordered by product start times
        * `"area"` - ascending order of product geometric areas

        :return: ordered indices
        """

        def get_collection(pi):
            return pi.collection

        def get_id(pi):
            return pi.id

        def get_start_time(pi):
            return pi.start_time

        def get_area(pi):
            return pi.geometry.area

        if sort_by == "collection":
            sort_func = get_collection

        elif sort_by == "id":
            sort_func = get_id

        elif sort_by == "start_time":
            sort_func = get_start_time

        elif sort_by == "area":
            sort_func = get_area

        else:
            raise ValueError(
                "'sort_by' must be either ['collection', 'id', 'start_date', 'area'] - not " + str(sort_by)
            )

        # Assign product info dictionaries in alphabetical order
        idxs = np.argsort([sort_func(pi) for pi in self])

        return idxs

    def sort(self, sort_by: str) -> None:
        """
        Reorders ProductItems by defined parameter in place

        :param sort_by: parameter to sort by, as for :py:meth:`~scrappi.product.ProductItemSet.argsort()`
        """

        idxs = self.argsort(sort_by=sort_by)

        self._products[:] = [self._products[i] for i in idxs]
        self._product_bounds = None
        self._collections = None

    def filter_id_contains(self, id_contains_str) -> None:
        """
        Filter ProductItemSet by whether the id contains a certain string

        :param id_contains_str: string that should be contained in the id
        :return: None
        """
        self._products = [
            self._products[i] for i in range(len(self._products)) if id_contains_str in self._products[i].id
        ]
        self._product_bounds = None
        self._collections = None

    def plot_geometries(
        self,
        ax: Optional[Axes] = None,
        padding_type: Optional[str] = "rel",
        padding_val: Optional[Union[float, str]] = 0.5,
        tick_step: Optional[float] = None,
        label_by: str = "collection",
        colors: Optional[List[str]] = None,
        legend: bool = True,
        remake_axes: bool = False,
    ) -> None:
        """
        Plots product geometries on lon lat grid for products in set

        :param ax: plot axes object
        :param padding_type: (default: `"rel"`) padding type (as required by :py:func:`~scrappi.utils.plot_utils.pad_plot_bounds()`)
        :param padding_val: (default: `0.5`) padding value (as required by :py:func:`~scrappi.utils.plot_utils.pad_plot_bounds()`)
        :param tick_step: (default: `None`) plot lat, lon axis tick separation
        :param label_by: (default: `"collection"`) product attribute to colour geometries by, either `"collection"` or `"id"`
        :param colors: (default: matplotlib's `TABLEAU_COLOURS`) list of ordered colours for geometries
        :param legend: (default: `True`) switch for whether to display legend

        Used as:

        .. code-block:: python

           from matplotlib import pyplot as plt
           from scrappi import ProductItemSet
           ps = ProductItemSet(...)
           ps.plot_geometries()
           plt.show()
        """
        # skip if there are no products
        if len(self._products) == 0:
            return None

        # Set default colours if no user input
        if colors is None:
            colors = list(mcolors.TABLEAU_COLORS.keys())

        # If Axes object not provided, build plot
        if ax is None:
            plt.figure()
            ax = plt.axes(projection=ccrs.PlateCarree())

        # Initialise list of legend labels
        if label_by == "collection":
            legend_handles = [None] * len(self.collections)
        elif label_by == "id":
            legend_handles = [None] * len(self)
        else:
            raise ValueError("'label_by' must be either ['collection', 'id'] - not " + str(label_by))

        # Plot products in reverse size order to better display handle overlapping geometries
        for idx in self.argsort(sort_by="area")[::-1]:
            if label_by == "collection":
                i_collection = self.collections.index(self[idx].collection)
                # Add legend label per collection
                if legend_handles[i_collection] is None:
                    legend_handles[i_collection] = mpatches.Patch(
                        color=colors[i_collection], label=self[idx].collection
                    )

                geometry_color = colors[i_collection]

            elif label_by == "id":
                color_idx = idx % len(colors)
                geometry_color = colors[color_idx]
                id_label = self[idx].id if len(self[idx].id) < 10 else self[idx].id[:6] + " ... " + self[idx].id[-6:]

                legend_handles[idx] = mpatches.Patch(color=geometry_color, label=id_label)

            self[idx].plot_geometry(ax=ax, geometry_color=geometry_color)

        # Add determined legend
        if legend:
            ax.legend(handles=legend_handles)

        # Set plot bounds
        bounds = self.product_bounds
        (
            plot_longitude_minimum,
            plot_latitude_minimum,
            plot_longitude_maximum,
            plot_latitude_maximum,
        ) = pad_plot_bounds(bounds, padding_type, padding_val)

        ax.set_extent(
            [
                plot_longitude_minimum,
                plot_longitude_maximum,
                plot_latitude_minimum,
                plot_latitude_maximum,
            ],
            crs=ccrs.PlateCarree(),
        )

        # Add map styling
        prepare_map_plot(ax, tick_step=tick_step)

        plt.tight_layout()


def open_product_item(path: str, filesystem: str = None, api: str = "eodag") -> ProductItem:
    """
    Returns ProductItem object from JSON file

    :param path: product item JSON file path
    :param filesystem: optional keyword to set filesystem, defaults to t-drive filesystem
    :param api: optional keyword to set api, defaults to eodag
    :return: product item object
    """

    with open(path, "r") as f:
        product_item_dict = json.load(f)

    return product_item_from_dict(product_item_dict, api=api, filesystem=filesystem)


def product_item_from_dict(product_item_dict: dict, filesystem: str = None, api: str = "eodag") -> ProductItem:
    """
    Returns ProductItem object from defining dictionary

    :param product_item_dict: product item JSON file
    :param filesystem: optional keyword to set filesystem, defaults to t-drive filesystem
    :param api: optional keyword to set api, defaults to eodag
    :return: product item object
    """

    return ProductItem(**product_item_dict, api=api, filesystem=filesystem)


def product_item_from_stac(
    item_or_path: Union[str, "pystac.Item"],
    context: Optional[ScrappiContext] = None,
) -> ProductItem:
    """
    Create a `ProductItem` from a STAC `Item` or from a path to an Item JSON file.

    :param item_or_path: a `pystac.Item` instance or a filesystem path to a STAC item JSON
    :return: `ProductItem`
    """
    if isinstance(item_or_path, str):
        # assume path to item json
        item = pystac.Item.from_file(item_or_path)
    else:
        item = item_or_path

    # id
    pid = item.id

    # collection
    collection = None
    try:
        collection = item.collection
    except Exception:
        collection = item.properties.get("collection") if item.properties else None

    # platform from properties if present
    platform = item.properties.get("platform") if item.properties else None
    if platform is None:
        platform = item.properties.get("platform_name") if item.properties else None

    constellation = item.properties.get("constellation") if item.properties else None

    # geometry as shapely object
    try:
        geom = sh.geometry.shape(item.geometry)
    except Exception:
        geom = item.geometry

    # temporal
    start_time = item.datetime if hasattr(item, "datetime") else item.properties.get("start_datetime")
    stop_time = None
    if item.properties:
        stop_time = (
            item.properties.get("end_datetime")
            or item.properties.get("completionTime")
            or item.properties.get("stop_time")
        )

    # assets -> choose data and quicklook if available
    url = ""
    quicklook = ""
    if hasattr(item, "assets"):
        assets = item.assets
        # pick data asset
        if "data" in assets:
            url = assets["data"].href
        else:
            # pick first non-image asset
            for a in assets.values():
                if a.media_type and not a.media_type.startswith("image"):
                    url = a.href
                    break
            if not url:
                # fallback to first asset
                for a in assets.values():
                    url = a.href
                    break

        # quicklook
        if "quicklook" in assets:
            quicklook = assets["quicklook"].href
        else:
            for a in assets.values():
                if a.media_type and a.media_type.startswith("image"):
                    quicklook = a.href
                    break

    # cloud fraction
    cloud_fraction = None
    if item.properties:
        cloud_fraction = item.properties.get("cloud_fraction") or item.properties.get("eo:cloud_cover")

    prod_dict = item.to_dict() if hasattr(item, "to_dict") else item.properties

    return ProductItem(
        constellation=constellation or "",
        platform=platform or "",
        collection=collection or "",
        id=pid,
        geometry=geom,
        start_time=start_time,
        stop_time=stop_time,
        prod_dict=prod_dict,
        filter_dict={},
        url=url,
        quicklook=quicklook,
        cloud_fraction=cloud_fraction,
        api_product=prod_dict,
        context=context,
    )


def from_stac(cls, item_or_path: Union[str, "pystac.Item"], context: Optional[ScrappiContext] = None) -> "ProductItem":
    """Construct a ProductItem from a STAC Item or file.

    This is exposed as a regular module-level function for documentation
    introspection and then attached as a `classmethod` on
    `ProductItem` below.
    """
    return product_item_from_stac(item_or_path, context=context)


# attach classmethod to ProductItem (wrap the function to create a real classmethod)
setattr(ProductItem, "from_stac", classmethod(from_stac))


def open_product_item_set(path: str, filesystem: str = None, api: str = "eodag") -> ProductItemSet:
    """
    Returns ProductItemSet object from JSON file

    :param path: product item set JSON file path
    :param filesystem: optional keyword to set filesystem, defaults to t-drive filesystem
    :param api: optional keyword to set api, defaults to eodag
    :return: product item set object
    """

    with open(path, "r") as f:
        product_item_set_dict = json.load(f)

    return product_item_set_from_dict(product_item_set_dict, api=api, filesystem=filesystem)


def product_item_set_from_dict(
    product_item_set_dict: dict, filesystem: str = None, api: str = "eodag"
) -> ProductItemSet:
    """
    Returns ProductItemSet object from defining dictionary

    :param product_item_set_dict: product item set JSON file
    :param filesystem: optional keyword to set filesystem, defaults to t-drive filesystem
    :param api: optional keyword to set api, defaults to eodag
    :return: product item object
    """

    pis = ProductItemSet()

    for p in product_item_set_dict["products"]:
        pis.add_ProductItem(product_item_from_dict(p, api=api, filesystem=filesystem))

    return pis


if __name__ == "__main__":
    pass
