.. _quickstart:

################
Quickstart Guide
################

The guide aims to get you using *scrappi* productively as quickly as possible.
In this guide, you will find installation instructions, basic descriptions and
examples to describe how to use *scrappi* to retrieve satellite and reference data.
Full examples downloading one month of satellite data over the Gobabeb RadCalNet site are available in scrappi/examples/ for the different API's.

Installation
++++++++++++

Install your package and its dependancies by using::

    pip install -e .

Virtual Environment
===================

It's always recommended to make a virtual environment for each of your python
projects.

If you are using conda you can create and activate your environment using::

    conda create -n yourenvname -k python=3.x

followed by::

    conda activate yourenvname (activate environment in windows)

or::

    source activate yourenvname (activate environment on a UNIX operating system)

Package Installation
====================

*scrappi* is installable via pip.

First clone the project repository from Gitlab::

   $ git clone https://gitlab.npl.co.uk/eco/tools/scrappi.git


Then install the module with pip. For development it is recommended to install in editable mode with the optional developer dependenies, i.e.::

    $ pip install -e ".[dev]"

Interface
+++++++++

It's very quick to get started with *scrappi*, only a few functions are required for all searching and downloading of products.

APIs
====
Before use
^^^^^^^^^^

To query and download products from online catalogues you are required to select a suitable API for the product type of interest.
Suitable APIs for a product type can be found by running::

    from scrappi.interface import get_api_name
    get_api_name(dataset)

For a full list of suitable APIs for a product type (returned in recommended order of use), specify ``all_apis=True`` ::

    get_api_name(dataset, all_apis=True)

If you are unsure of your product type a full list of accepted product types can be found using::

    from scrappi.interface import list_satellite_products_api
    list_satellite_products_api()

Commonly used product types include:

.. list-table::
   :stub-columns: 1
   :header-rows: 1

   * - Product Type/Satellite Dataset
     - Satellite Product
   * - LANDSAT_C2L1
     - Landsat Collection 2 Level 1
   * - S2_MSI_L1C
     - Sentinel 2 Level 1C

Setting credentials
^^^^^^^^^^^^^^^^^^^
Most online satellite catalogues require authentication before they can be queried for products. It is recommended to use a configuration file, as described in :ref:`config`, using::

    from scrappi import ScrappiContext
    context = ScrappiContext(config_file_path="path/to/your/config.yaml")


Useful credential setting information
    * ``eodag``
        - ``usgs`` - is recommended for landsat products using `EarthExplorer <https://earthexplorer.usgs.gov/>`_ credentials
        - ``cop_dataspace`` - is recommended for sentinel products using `Copernicus Data Space <https://dataspace.copernicus.eu/>`_ credentials

For the eodag API, the credentials can also be set in the eodag configuration file (either using the eodag standard
config file, or providing a config file manually) (see:ref:`config`).

A list of providers used by eodag can be found `here <https://eodag.readthedocs.io/en/stable/getting_started_guide/providers.html>`_
and you can find which provider supplies the data you require by using this search `table <https://eodag.readthedocs.io/en/stable/getting_started_guide/product_types.html>`_.


Perform a query
^^^^^^^^^^^^^^^

Once a suitable API has been determined for a product that information can be used to perform a query. ::

    from scrappi import ScrappiContext
    from scrappi.interface import perform_query
    
    context = ScrappiContext(config_file_path="path/to/your/config.yaml")
    api_name = "eodag"  # name of suitable API for product
    query = {
            "collections": ["LANDSAT_C2L1"],
            "start_time": dt.datetime(2022, 1, 20, 7),
            "stop_time": dt.datetime(2022, 1, 20, 8, 30),
            "geom": {"latitude_minimum": 40, "longitude_minimum": 30, "latitude_maximum": 50, "longitude_maximum": 50}
        }
        
    products = perform_query(
        query,
        context
    )

These products are returned as a ProductItemSet, which contains one or multiple ProductItem objects.
These contain all the key information as attributes and have useful helper functions (see :ref:`product`)

Set file system
^^^^^^^^^^^^^^^
In order to generate the appropriate paths for each product, every ProductItem has a file system associated with it, as detailed in :ref:`filesystem`.
One can either use one of the named file systems (such as "t-drive") or provide an existing path and optionally a bool whether the data should be organised by platform/collection/year/month/day. ::

    from scrappi.interface import make_fs
    file_system = make_fs(r"C:\Users\pdv\data\SatelliteData\RadCalNet\GONA",organise_data=False)

 The filesystem of a ProductItem (or all ProductItems in a ProductItemSet) can be set independently. ::
    
    from scrappi import ScrappiContext
    context = ScrappiContext()

    products = perform_query(
        {
            "collections": ["LANDSAT_C2L1"],
            "start_time": dt.datetime(2022, 1, 20, 7),
            "stop_time": dt.datetime(2022, 1, 20, 8, 30),
            "geom": {"latitude_minimum": 40, "longitude_minimum": 30, "latitude_maximum": 50, "longitude_maximum": 50}
        },
        context
    )
    
    products.set_fs(file_system)

Download an identified product
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Once queried, the products can be easily downloaded::

    from scrappi.interface import download_product
    download_product(products, context)

Any of the filesystems provided in :ref:`filesystem` can be used by setting the file system in products.

Moving products
^^^^^^^^^^^^^^^
After they have been downloaded, products (ProductItem or ProductItemSet) can also be moved from the current file system, to a new file system::

    new_fs = make_fs("t-drive")
    products.move_product(new_fs)


Using the example scripts
========
The repository includes example scripts, such as ``examples/eodag_example.py`` which demonstrates a typical workflow:
- Create a filesystem with ``make_fs('t-drive')`` (scrappi filesystem factory)
- Create a ``ScrappiContext()`` using the defined config
- Build a query dictionary with ``collections``, ``geom``, ``start_time``, ``stop_time``
- Run ``perform_query(query, context)`` and then ``download_product(products, context)``

Run it from the project root after you have configured eodag:

.. code-block:: bash

  python examples/eodag_example.py


Troubleshooting
===============
- Authentication failures: verify the credentials in your user config and that provider endpoints are reachable.
- No products returned: expand your spatial or temporal query window and confirm collection names match those available to your provider.
- Download errors: check the retry settings in your config and ensure you have sufficient permissions and storage space for downloads.
