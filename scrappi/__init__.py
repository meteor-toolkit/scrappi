"""scrappi - EO Satellite product catalogue retrieval by API or file system"""

__author__ = "Pieter De Vis <pieter.de.vis@npl.co.uk>"
__all__ = [
    "ProductItem",
    "ProductItemSet",
    "open_product_item",
    "open_product_item_set",
    "product_item_from_dict",
    "product_item_set_from_dict",
    "ScrappiContext",
    "make_api",
    "make_fs",
    "make_query_with_tolerance",
    "make_query_start_stop",
    "perform_query",
    # download_metadata,
    "download_product",
    "generate_bounding_box",
    "get_api_name",
    "set_credentials",
    "update_context_file",
]

import os
from importlib.metadata import version, PackageNotFoundError
from processor_tools import Context, read_config, write_config
from typing import Optional, Dict, Any, List, Union
from eodag import EODataAccessGateway

THIS_DIRECTORY = os.path.dirname(__file__)
user_home_directory = os.path.expanduser("~")
eodag_config_file_path = os.path.join(user_home_directory, ".config", "eodag", "eodag.yml")
try:
    eodag_config = {"eodag": read_config(eodag_config_file_path)}
except:
    EODataAccessGateway()
    eodag_config = {"eodag": read_config(eodag_config_file_path)}


from scrappi.config import config_init

if not config_init.is_initialised():
    print(f"Initialising config at {config_init.get_config_directory()}...")
    config_init.init()


class ScrappiContext(Context):
    default_config: Optional[Union[str, List[str]]] = None

    def __init__(self, context: Optional[Union[dict, str]] = None):
        self.default_config = [
            os.path.join(THIS_DIRECTORY, "etc", "defaults.yaml"),
            eodag_config,
        ]
        super(ScrappiContext, self).__init__(context, config_init=config_init)

    def set_preferred_provider_all(self, provider: str, remove_other_providers: Optional[bool] = False):
        self["api"]["prefered_provider"] = provider

    def set_preferred_api(self, api: str, remove_other_apis: Optional[bool] = False):
        self["api"]["preferred_api"] = api


from scrappi.interface import (
    make_api,
    make_fs,
    make_query_with_tolerance,
    make_query_start_stop,
    perform_query,
    # download_metadata,
    download_product,
    generate_bounding_box,
    get_api_name,
    set_credentials,
    update_context_file,
)
from scrappi.product import (
    ProductItem,
    ProductItemSet,
    open_product_item_set,
    open_product_item,
    product_item_from_dict,
    product_item_set_from_dict,
)


def register_productitem_in_fs(product_item, filesystem=None, root_stac_dir_name="stac", overwrite=False):
    """Convenience wrapper to register a single ProductItem into a filesystem STAC catalog.

    :param product_item: instance of `ProductItem`
    :param filesystem: optional filesystem (defaults to product_item.filesystem)
    :param root_stac_dir_name: folder name under filesystem.directory to store STAC
    :param overwrite: whether to overwrite existing item json
    :return: path to saved item json
    """
    return product_item.register_in_filesystem_catalog(
        filesystem=filesystem,
        root_stac_dir_name=root_stac_dir_name,
        overwrite=overwrite,
    )


def register_productitemset_in_fs(product_item_set, filesystem=None, root_stac_dir_name="stac", overwrite=False):
    """Convenience wrapper to register a ProductItemSet into filesystem STAC catalogs.

    :param product_item_set: instance of `ProductItemSet`
    :param filesystem: optional filesystem (defaults to each product's filesystem)
    :param root_stac_dir_name: folder name under filesystem.directory to store STAC
    :param overwrite: whether to overwrite existing item jsons
    :return: path to root catalog json
    """
    return product_item_set.update_filesystem_catalogs(
        filesystem=filesystem,
        root_stac_dir_name=root_stac_dir_name,
        overwrite=overwrite,
    )


try:
    __version__ = version("scrappi")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
