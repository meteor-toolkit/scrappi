.. _common_queries:

################
Common Queries
################

This page contains example queries for some of the more commonly used datasets. As not every provider holds all the data for a given product, it is important to select the right provider for your purpose. The providers used in these examples have the most complete datasets for each product.

Examples
========


Sentinel-2 MSI Level-1C and Level-2A, and Sentinel-3 OLCI and SLSTR Level-1B 
--------------

Preferred provider: ``cop_dataspace``

::

        query = {
        "collections": "S2_MSI_l1C", # OLCI: S3_EFR, SLSTR: S3_SLSTR_L1RBT, MSI L2: S2_MSI_L2A
        "geom": {"latitude_minimum": latitiude_minimum, "longitude_minimum": longitude_minimum, "latitude_maximum": latitude_maximum, "longitude_maximum": longitude_maximum},
        "start_time": datetime_start,
        "stop_time": datetime_end,
        }

Landsat-8/9 OLI/TIRS Collection-2 Level-1
--------------

Preferred provider: ``usgs``

::

        query = {
        "collections": "LANDSAT_C2L1",
        "geom": {"latitude_minimum": latitiude_minimum, "longitude_minimum": longitude_minimum, "latitude_maximum": latitude_maximum, "longitude_maximum": longitude_maximum},
        "start_time": datetime_start,
        "stop_time": datetime_end,
        }


Preferred Providers
========
Commonly used product types and their preferred providers:

.. list-table::
   :stub-columns: 1
   :header-rows: 1

   * - Product Type
     - Provider
   * - S2_MSI_L1C
     - ``cop_dataspace``
   * - S2_MSI_L2A
     - ``cop_dataspace``
   * - S3_EFR
     - ``cop_dataspace``
   * - S3_SLSTR_L1RBT
     - ``cop_dataspace``
   * - LANDSAT_C2L1
     - ``usgs``
