.. _filesystem:

###############################
Filesystems for defining paths
###############################

The purpose of the filesystems is to generate paths that can then be used to save and find the products
catalogued by scrappi. This includes paths for existing files as well as generating paths for products to
be downloaded to. The different filesystems we define are appropriate for saving and finding data in different
contexts. For example, data on JASMIN (CEDA) might be stored in a different way as those saved on the NPL t-drive,
or those saved locally on someone's computer. The filesystems allow a flexible way of accessing these paths and using
them interchangeably.


Local File System
=================

The :py:class:`~scrappi.fs.localfilesystem.LocalFileSystem` class defines the most flexible filesystem.
It allows any existing path as its input, and has the option to either store data using our typical hierarchy
(platform/collection/year/month/day/id) for organise_data=True, or unorganised (all products in same folder) for organise_data=False.
Creating a local archive can be done as follows::

    from scrappi.fs.localfilesystem import LocalFileSystem
    local_fs=LocalFileSystem(directory=r"C:\Users\username\data\temp",organise_data=True)

If no directory is provided, the path defaults to the scrappi\examples\downloaded_data directory.
Another way to generate the local file system is through the following interface function::

    from scrappi.interface import make_fs
    local_fs=make_fs(r"C:\Users\username\data\temp",organise_data=True)

Here the first argument is the name of the filesystem, if an existing path is provided,
a :py:class:`~scrappi.fs.localfilesystem.LocalFileSystem` will be made using that path.

The main use of the filesystems is to generate product paths::

    product_path = local_fs.return_path(product_item)
    product_path, exists = local_fs.return_path(product, check_exists=True)

where product is a ProductItem or ProductItemSet, product_path is the desired product path, and exists is a boolean indicating whether the product already exists at that path.

t-drive
=========
There are also a number of predefined filesystems with a given name.
E.g. there is a filesystem for saving data on the NPL t-drive.
This filesystem always uses the same directory and the same hierarchy of files (platform/collection/year/month/day/id).
The easiest way to make this file system is using::

    from scrappi.interface import make_fs
    fs=make_fs("tdrive")
    product_path = fs.return_path(product_item)

Using file systems
===================
When using scrappi to download data (see :ref:`download`), the file system is used to work out where the downloaded data should be saved.
In order to do this, the filesystem attribute of the ProductItems to be downloaded should be set.
This can be done either by providing the file system as the optional filesystem keyword when calling perform_query.
Alternatively, the file system can be set after performing the query by using the set_fs() function of the ProductItem and ProductItemSet classes::

    # here we assume products is a ProductItemSet returned by perform_query()
    new_fs=make_fs("./", organise_data=False)
    products.set_fs(new_fs)
    products.get_path()

After downloading the data to the file system (see :ref:`download`), products can also be moved from one filesystem (the one currently in the ProductItemSet) to a new file system::

    new_fs=make_fs("t-drive")
    products.move_product(new_fs)
    products.get_path()

Note that 'move_product` does not have the functionality to create a new directory, please ensure that the path provided already exists.