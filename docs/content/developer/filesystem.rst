.. _developer_fs:

####################
Adding a filesystem
####################

On this page you can find information relating to the steps required to add a file system
to *scrappi*. File systems provide a way to generate product paths matching the file organisation on different systems.

Creating a file system Class
==============================
Different file systems can be defined. These can either be named file systems (e.g. "t-drive"), or LocalFyleSystems pointing to a given directory.
These file systems all inherit from ``scrappi.fs.base.BaseFileSystem`` and can make use of methods
within the class.

Required
++++++++
File systems all inherit from ``scrappi.fs.base.BaseFileSystem`` and must therefore
contain the following methods, properties and attributes:

.. list-table::
   :stub-columns: 1
   :widths: 10 30 30 30
   :header-rows: 1

   * -
     -
     - Docstring
     - Extra Info
   * - @abstractmethods
     -
     -
     -
   * -
     - ``return_path(self, product_item: ProductItem, check_exists: bool = False) -> str:``
     - ``Returns path from info in ProductItem``
     - if check_exists is True, the output should instead be a tuple with (path,exists), where path is the returned path, and exists is a boolean indicating whether this path exists.
   * -
     - ``return_path_platform_collection_year_month_day(self, collection: str, year: str, month: str, day: str) -> str``
     - ``Returns path from provided info``
     -
   * - class attributes
     -
     -
     -
   * -
     - ``directory``
     - ``str``
     - file system base directory (default: current working directory)

New file systems should also be added to scrappi.fs.factory.