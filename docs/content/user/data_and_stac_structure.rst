
Data and STAC Catalogue Structure
================================

This document describes how data are organised on disk and how they are
represented in the STAC catalogue exposed by the API. The design follows a
clear separation of concerns:

* **The data directory structure** is optimised for human navigation,
  provenance, and preservation of original files.
* **The STAC catalogue** provides the authoritative semantic and queryable
  description of the data.

The two structures are aligned, but they are not required to mirror each
other exactly.

--------------------------------
Design Principles
--------------------------------

The following principles guide the design:

* Original data files and filenames are preserved unchanged.
* Directory names convey intuitive, high-level meaning for users.
* All scientific meaning and query semantics live in STAC metadata.
* The same structural pattern is used for satellite, in situ, and
  model/reanalysis data.
* Temporal coverage is described in metadata, not inferred from paths.

--------------------------------
Data Directory Structure
--------------------------------

All data are stored under a single root directory, organised by
**constellation**, **platform**, **collection**, and time.

The canonical on-disk layout is:

.. code-block:: text

   data/
   └── <constellation>/
       └── <platform>/
           └── <collection>/
               └── <YYYY>/
                   └── <MM>/        (optional)
                       └── <DD>/    (optional)
                           └── original data files

--------------------------------
Examples
--------------------------------

Satellite data example (Sentinel‑2)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   data/
   └── Sentinel-2/
       └── Sentinel-2A/
           └── S2_MSI_L2A/
               └── 2024/06/10/
                   └── S2A_MSIL2A_20240610T103421_....SAFE/

In situ data example (RadCalNet)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   data/
   └── RadCalNet/
       └── GONA/
           └── RCN_TOA/
               └── 2023/02/07/
                   └── GONA01_2023_038_v04.09.output

Reanalysis / model data example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   data/
   └── ECMWF/
       └── ERA5/
           └── era5-single-levels-hourly/
               └── 2024/06/10/
                   └── era5_sl_20240610_00.nc

--------------------------------
STAC Catalogue Structure
--------------------------------

STAC metadata are stored separately from the data files and provide the
primary means of search and discovery.

The STAC catalogue follows a conventional structure:

.. code-block:: text

   stac/
   ├── catalog.json
   ├── collections/
   │   ├── <collection-id>/
   │   │   └── collection.json
   │   └── ...
   └── items/
       └── YYYY/
           └── MM/
               └── DD/
                   └── <item-id>.json

Alignment Between Data Paths and STAC Metadata
---------------------------------------------


====================  =====================================
Data hierarchy level  STAC field
====================  =====================================
constellation         ``properties.constellation``
platform              ``properties.platform``
collection            ``collection`` (Item top-level field)
YYYY/MM/DD            ``properties.datetime``
files                 ``assets[].href``
====================  =====================================

--------------------------------
Summary
--------------------------------

The combined data and STAC structure provides:

* A single, consistent hierarchy across data types
* Intuitive navigation for users
* Robust, queryable metadata via STAC
* Full support for satellite, in situ, and model/reanalysis data
* Long-term stability without renaming or restructuring files
