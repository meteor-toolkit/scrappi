.. _developer_api:

################
Adding an API
################

On this page you can find information relating to the steps required to add an API call handler
to *scrappi*.

Creating an API Call Handler Class
==================================
Most API's download data from online catalogues.
These API call handlers all inherit from ``scrappi.api.base.BaseAPICallHandler`` and can make use of methods
within the class.

Required
++++++++
API call handlers all inherit from ``scrappi.api.base.BaseAPICallHandler`` and must therefore
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
     - ``perform_query(self, query: dict) -> ProductItemSet``
     - ``Return catalogue product objects that satisfy query``
     -
   * -
     - ``download_metadata(self, product: Union[str, ProductItem, ProductItemSet],fs: Optional[Union[str, BaseFileSystem]])``
     - ``Download catalogue product(s) metadata at defined URL to local path``
     - Currently downloaded metadata are saved in folders within the path specified according to their acquisition date, e.g. 'path/2022/08/21'
   * -
     - ``download_product(self, product: Union[str, ProductItem, ProductItemSet],fs: Optional[Union[str, BaseFileSystem]])-> Union[list, str]``
     - ``Download catalogue product(s) at defined URL to local path``
     - Currently downloaded products are saved in folders within the path specified according to their acquisition date, e.g. 'path/2022/08/21'
   * - @properties
     -
     -
     -
   * -
     - ``platforms``
     - ``Return a dictionary of all acceptable product type inputs as keys and their respective api specific product type name as values``
     - Acceptable product types are ones from `eodag <https://eodag.readthedocs.io/en/stable/>`_, so ``platforms`` provides a mapping from their values to the ones required to query your api
   * - class attributes
     -
     -
     -
   * -
     - ``name``
     - ``str``
     - Name of api call handler, e.g. eodag

New API's should also be added to scrappi.api.factory.

Suggested implementations for abstract methods (using base class methods)
+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

A number of similar methods have been implemented across different API Call Handler Classes
which might be useful to those considering contributing their own API Call Handler to *scrappi*.
The format of these methods and their purpose can be found below.

Useful methods to consider implementing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

::

    def _set_datetime(self, date_time):
        """
        Convert input datetime to a datetime suited to the api query format

        :param date_time: input datetime string or object
        :return: datetime formatted in whichever way the api requires
        """
        return self._get_datetime(date_time)  # in required format for api querying

    def _set_geom(self, geom):
        """
        Convert input geometries to ones suited to the api query format

        :param geom: input geometry
        :return: geometry formatted in whichever way the api requires
        """
        geom = self._get_geom(geom)  # check and change geometries
        if isinstance(geom, dict):
            return geom  # in required format for api querying
        if isinstance(
            geom,
            (
                shapely.geometry.base.BaseGeometry,
                shapely.geometry.base.BaseMultipartGeometry,
            ),
        ):
            return geom  # in required format for api querying
        else:
            return geom  # in required format for api querying

    def _set_product_type(self, collection):
        """
        Return appropriate product type for api

        :param collection: collection name corresponding to desired product type
        :return: corresponding product type required for querying the api
        """
        product_type = self._get_product_type(collection)  # check valid product type for api
        return product_type  # in required format for api querying


Suggested abstract method implementations
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Example *perform_query* implementation::

    def perform_query(self, query: dict) -> list:
        """
        Return catalogue product objects that satisfy query

        :param query: catalogue query
        :return: product objects satisfying query
        """
        # convert input query to a style suitable for api
        new_query = {
            "dataset": self._set_product_type(query["collections"][0]),
            "bbox": self._set_geom(query["geom"]),
            "start_date": self._set_datetime(query["start_time"]),
            "end_date": self._set_datetime(query["stop_time"]),
        }

        # query products
        products = self.api.search(**new_query)

        # store individual query results in ProductItem
        product_list = []
        for prod in products:
            prod_dict = prod.as_dict()
            product_list.append(
                ProductItem(
                  constellation="Unknown",
                  collection=prod_dict["properties"]["product_type"],
                  id=prod_dict["id"],
                  geometry=Polygon(prod_dict["geometry"]["coordinates"][0]),
                  start_time=prod_dict["properties"]["startTime"],
                  stop_time=prod_dict["properties"]["completionTime"],
                  properties=prod_dict,
                )
            )

        #now return them as ProductItemSet
        return ProductItemSet(product_list)

