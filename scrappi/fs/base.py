"""scrappi.fs.base - base class for file system call handler implementations"""

from abc import ABC, abstractmethod
from typing import Optional
import os
from scrappi.product import ProductItem

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]
__all__ = ["BaseFileSystem"]


class BaseFileSystem(ABC):
    """
    Base class for file system call handler implementations for product archives.

    Should be subclassed for each product archive structure we want to interface to (e.g. CEDA archive).

    Subclasses must implement abstract methods.

    :param directory: (default: current working directory) file system base directory
    """

    def __init__(self, directory):
        if directory is None:
            raise ValueError(
                "Cannot create a filesystem without specifying the path (either manually or through context['fs']['path'])."
            )
        self.directory = directory

    @abstractmethod
    def return_path(self, product_item: ProductItem, check_exists: bool = False) -> str:
        """
        Returns path from info in ProductItem

        :param product_info: productItem defining info, including ``"product_name"`` and ``"datetime"``
        :param check_exists: if true, returns None if product not in archive
        :return: product path
        """
        pass


if __name__ == "__main__":
    pass
