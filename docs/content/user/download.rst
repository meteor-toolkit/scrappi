.. currentmodule:: scrappi

.. _download:

##########################
Downloading with *scrappi*
##########################

The main objective of scrappi is to find and store satellite data matching certain criteria.
Downloading the data from the data providers is obviously a very important part of this.
Within scrappi, there are a few ways the data can be downloaded.

Downloading ProductItemSet
===========================
The main usecase for scrappi is when the user first performs a query (see :ref:`query`), and then wants to
download the files in the resulting ProductItemSet. In order to download the files to the right directory, it is
important the file system (see :ref:`filesystem`) is first correctly set in the ProductItem or ProductItemSet.
Once the file system is set, the ProductItemSet can be passed to the associated interface function,
or the user can use the build-in function in the ProductItem(Set) class. In the latter case, one also has
to ensure the correct api is set in the ProductItem(Set)::

    from scrappi.interface import download_product
    api_name = "eodag"

    # here we assume products is a ProductItemSet with the filesystem already set correctly
    path_list=download_product(api_name, products)

    # or alternatively
    products.set_api(api_name)
    path_list=products.download_product()

The files will be downloaded, skipping any file which already exists in the file system, and the path to each product will be returned.
(WARNING: scrappi can only partially check if the downloaded file is correct - it checks if the file exists, and if it is a valid .zip or .tar.gz file, but it cannot verify if all the files within that archive are present.)


Filename Download
==================
In some cases, the user might want to download files based on the filename, when a ProductItem is not immediately available.
This option is not possible for every API/provider.
When it is available, it is possible to download the data as follows::

    from scrappi.interface import download_product_filename, make_fs
    api_name = "eodag"
    file_system= make_fs("./")

    path_list=download_product_filename(api_name, "S2A_MSIL1C_20221001T084801_N0400_R107_T33KWP_20221001T123324", file_system)

