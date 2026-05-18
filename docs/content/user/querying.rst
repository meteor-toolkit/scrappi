.. _querying:

######################
Quering with *scrappi*
######################

*scrappi* uses a unified querying format across all APIs and file system retrieval systems via use of
interface functions. This page provides information on accepted query inputs and query generation functions,
as well as how to use these queries to retrieve products of interest.

Acceptable query formats
========================
Most APIs and file system retrievals allow you to filter products by region of interest (roi), time window
and product type. Although some call handlers allow for a greater specification of querying parameters these parameters
are ignored if used with call handlers without this functionality.

Queries are passed to *scrappi* in the form of dictionaries.

Query inputs
------------

Product type
++++++++++++
Product type (or dataset) refers to the name of the product dataset for which you wish to query.
For consistency the format of the product type names have been unified to *eodag*'s naming system.

Some example names are:
    * **LANDSAT_C2L1**  -    ``Landsat Collection 2 Level 1``
    * **S2_MSI_L1C**    -    ``Sentinel 2 MSI Level 1C``
    * **S3_EFR**        -    ``Sentinel 3 OLCI Earth Observation Full Resolution Level 1B``

To get a list of all accepted product types/datasets you can run::

    from scrappi.interface import list_satellite_products_api

    # get list of product types
    list_satellite_products_api()

If you have a specific product type/dataset in mind you can filter the list of product types with a ``guess``, for
example if you're looking for available Sentinel-3 datasets you can use::

    list_satellite_products_api(guess="s3")

which returns any product types with "S3" or "s3" in::

    ['S3_EFR',
     'S3_ERR',
     'S3_LAN',
     'S3_OLCI_L2LFR',
     'S3_OLCI_L2LRR',
     'S3_OLCI_L2WFR',
     'S3_OLCI_L2WRR',
     'S3_RAC',
     'S3_SLSTR_L1RBT',
     'S3_SLSTR_L2AOD',
     'S3_SLSTR_L2FRP',
     'S3_SLSTR_L2LST',
     'S3_SLSTR_L2WST',
     'S3_SRA',
     'S3_SRA_A',
     'S3_SRA_BS',
     'S3_SY_AOD',
     'S3_SY_SYN',
     'S3_SY_V10',
     'S3_SY_VG1',
     'S3_SY_VGP',
     'S3_WAT']


Region of interest
++++++++++++++++++
Different call handlers have a different way of using a region of interest to query their catalogues, although these
have been unified within *scrappi*, on occasion some products may be returned outside of your specified roi.

The types of formats accepted by *scrappi* for defining a region of interest are listed below.
    * **list** - ``[latitude_minimum, longitude_minimum, latitude_maximum, longitude_maximum]``
    * **dict** - ``{"latitude_minimum": latitiude_minimum, "longitude_minimum": longitude_minimum, "latitude_maximum": latitude_maximum, "longitude_maximum": longitude_maximum}``
    * **shapely.geometry** - any type of shapely geometry, i.e. ``shapely.geometry.Point``, ``shapely.geometry.Polygon`` etc.
    * **wkt** - any Well-Known Text str defining a region of interest/shape

**NB: The order of coordinates used within scrappi is (latitude, longitude), though shapely.geometries use (longitude, latitude),
and thus need to be used with caution**

If you require data surrounding a single point, rather than a ROI, then utilise the `make_query_with_tolerance()` function described below.

Time window
+++++++++++
A time window is defined by using a start and stop time in a query.
Accepted start and stop time formats are either valid date strings (given by
`datetime.datetime.fromisoformat <https://docs.python.org/3/library/datetime.html#datetime.datetime.fromisoformat>`_
and `datetime.time.isoformat <https://docs.python.org/3/library/datetime.html#datetime.time.fromisoformat>`_ and a
number of variations thereof) or datetime.datetime objects.

Example query
-------------
::

        query = {
        "collections": [dataset],
        "geom": {"latitude_minimum": latitiude_minimum, "longitude_minimum": longitude_minimum, "latitude_maximum": latitude_maximum, "longitude_maximum": longitude_maximum},
        "start_time": datetime_start,
        "stop_time": datetime_stop,
        }

Creating a query
================
There are a couple of functions that enable you to create queries with tolerances and start and end parameters.

These are listed below:
    * ``make_query_with_tolerance`` - Make a query with a given spatial and temporal tolerance
        - inputs
            - ``dataset: str`` - name of the satellite dataset to search through
            - ``latitude: Union[float, int]`` - latitude of the point to search for
            - ``longitude: Union[float, int]`` - longitude of the point to search for
            - ``datetime: Union[dt.datetime, str]`` - datetime around which to search for
            - ``spatial_tolerance_deg: Optional[Union[float, int]] = None`` - spatial tolerance about point in degrees
            - ``spatial_tolerance_m: Optional[Union[float, int]] = None`` - spatial tolerance about point in meters
            - ``temporal_tolerance_min: Optional[Union[float, int]] = None`` - temporal tolerance about datetime in minutes
            - ``temporal_tolerance_hours: Optional[Union[float, int]] = None`` - temporal tolerance about datetime in hours

    * ``make_query_list_with_tolerance`` - Make a list of queries for a given set of spatial and temporal tolerances
        - inputs
            - ``dataset: Union[str, list]`` - name of the satellite dataset to search through
            - ``latitude: Union[float, list]`` - latitude of the point to search for
            - ``longitude: Union[float, list]`` - longitude of the point to search for
            - ``datetime: Union[dt.datetime, str, list]`` - datetime around which to search for
            - ``spatial_tolerance_deg: Optional[Union[float, int, list]] = None`` - spatial tolerance about point in degrees
            - ``spatial_tolerance_m: Optional[Union[float, int, list]] = None`` - spatial tolerance about point in meters
            - ``temporal_tolerance_min: Optional[Union[float, int, list]] = None`` - temporal tolerance about datetime in minutes
            - ``temporal_tolerance_hours: Optional[Union[float, int, list]] = None`` - temporal tolerance about datetime in hours

Example usage of one of the functions::

    query_S2 = make_query_with_tolerance(
        "S2_MSI_L1C",
        latitude=-23.6015,
        longitude=15.1258,
        datetime="2022-07-13T09:30",
        temporal_tolerance_min=120,
        spatial_tolerance_m=500,
    )

    print(query_S2)

    {'collections': ['S2_MSI_L1C'],
     'start_time': '2022-07-13T07:30:00',
     'stop_time': '2022-07-13T11:30:00',
     'geom': [-23.605615801556784,
      15.1213084235794,
      -23.597384069261146,
      15.130291576420598]}

Using a query to find products
==============================
*scrappi* contains the functionality to query with both a single query (as formatted above)
or a list of queries.

Example uses of both these cases is shown below.
Single query::

    from scrappi.interface import perform_query
    from scrappi import ScrappiContext

    context = ScrappiContext('path_to_user_config.yaml')

    products = perform_query(
                         {
                             "collections": ["LANDSAT_C2L1"],
                             "start_time": dt.datetime(2022, 1, 20, 7),
                             "stop_time": dt.datetime(2022, 1, 20, 8, 30),
                             "geom": {"latitude_minimum": 40, "longitude_minimum": 29, "latitude_maximum": 50, "longitude_maximum": 50},
                         },
                         context
                )

Multiple queries::

    from scrappi.interface import perform_query_list
    from scrappi import ScrappiContext

    context = ScrappiContext('path_to_user_config.yaml')

    products = perform_query_list(
        list_of_queries,
        context
    )

Note that the returned products will have the default file system (t-drive, see :ref:`filesystem`), unless a different file system is set, or assigned to the ProductItem(s) once they are returned.