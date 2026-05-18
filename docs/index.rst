=========================================================
scrappi Documentation
=========================================================

*scrappi* is a Python package for retrieving EO (Earth Observation) Satellite and Reference products by API or file system.
It's designed to provide an easy way to access products through a unified API regardless of the data provider/location.

Current supported providers include:
    `usgs <https://earthexplorer.usgs.gov/>`_, `copernicus open access hub <https://scihub.copernicus.eu/>`_, and any supported by `eodag <https://eodag.readthedocs.io/en/stable/>`_.

.. note::

   To be able to download/query products from `USGS (Landsat Products) <https://earthexplorer.usgs.gov/>`_, `Machine-to-Machine <https://m2m.cr.usgs.gov/api/docs/json/>`_ access is required, this can be requested from https://ers.cr.usgs.gov/profile/access once you have registered.

.. grid:: 2
   :gutter: 2

   .. grid-item-card::  User Guide
      :link: content/user/user_guide
      :link-type: doc

      The user guide provides information on how to get started with *scrappi*,
      as well as some more detailed information about its features.

   .. grid-item-card::  ATBD
      :link: content/user/atbd
      :link-type: doc

      The algorithm theoretical basis documentation describes the science underpinning
      *scrappi*

   .. grid-item-card::  API Reference
      :link: content/user/function_api
      :link-type: doc

      The reference guide contains a detailed description of the scrappi
      API. It describes how the functions, classes and methods of the package work.

   .. grid-item-card::  Developer Guide
      :link: content/developer/developer_guide
      :link-type: doc

      The developer guide describes how to contribute to scrappi.


Acknowledgements
----------------

scrappi has been developed by `CEO Group <pieter.de.vis@npl.co.uk, harry.morris@npl.co.uk, mattea.goalen@npl.co.uk, sam.hunt@npl.co.uk>`_.

Project status
--------------

scrappi is under active development. It is beta software.

.. toctree::
   :maxdepth: 3
   :hidden:
   :caption: For users

   User Guide <content/user/user_guide>
   ATBD <content/user/atbd>
   API Reference <content/user/api>

.. toctree::
   :maxdepth: 3
   :hidden:
   :caption: For developers/contributors

   Developer Guide <content/developer/developer_guide>