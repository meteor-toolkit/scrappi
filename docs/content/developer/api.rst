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

In-situ handlers
+++++++++++++++++
A handler for a ground-based (in-situ) network -- RadCalNet, HYPERNETS -- inherits
from ``scrappi.api.insitubase.InSituCallHandler`` instead of ``BaseAPICallHandler``
directly. It adds a site -> region-of-interest registry (``roi_dict``,
``get_roi_shapely``, ``set_roi_bounding_box``) that the query/collocation code relies
on, and declares ``list_collections`` and ``download_file`` abstract on top of the
base's ``perform_query`` / ``download_product``.

Offline (archive-backed) handlers
+++++++++++++++++++++++++++++++++++
An *offline* handler exposes the same query/download interface but resolves product
files from a local directory tree the user already holds, rather than a network
service -- for data that isn't published online (yet, or ever), or simply as a
fallback. It inherits from ``scrappi.api.offlinebase.OfflineArchiveHandler``, which
provides:

* **archive-path resolution** -- ``__init__(context, archive_path=None)`` sets
  ``self.archive_path`` from the ``archive_path`` argument, else the nested context
  keys named in the class attribute ``ARCHIVE_PATH_CONTEXT_KEYS`` (e.g.
  ``("RadCalNet", "offline_archive_path")``), else ``_default_archive_path()``
  (override it if there is a sensible fixed fallback, otherwise the base raises);
* ``_index_of(root)`` -- a cached ``name -> path`` map from a single walk of
  ``root`` (``_archive_index`` is ``_index_of(self.archive_path)``); a directory
  whose name ends with one of ``INDEX_DIRECTORY_SUFFIXES`` (e.g. ``.SAFE``) is one
  entry, not its contents. ``_archive_path_for(product)`` matches ``product.id``
  exactly, then ``id`` + each ``PRODUCT_NAME_SUFFIXES`` entry (empty by default:
  in-situ ids *are* the filenames). The cache is not invalidated -- call
  ``clear_cache()`` if the archive is written to during the handler's life (it is
  reused across queries via ``Factory``'s ``use_cache``);
* ``_flat_filesystem(dirpath)`` -- a flat-layout ``STACFileSystem`` (``flat=True``:
  no ``<root>/data`` + ``<root>/stac`` split, no organised date tree) to hand each
  ``ProductItem`` built in ``perform_query`` as its ``filesystem=``. Read-only by
  default (``ARCHIVE_READ_ONLY``: an offline archive is the user's, not scrappi's
  to write to); the read-only flag survives ``download_product``'s re-pin;
* ``download_product`` -- resolves the product locally (no network, no copy) and
  repins its filesystem, so it also works for a product rebuilt from a STAC
  catalogue (which arrives with none).

An in-situ subclass implements only ``perform_query`` and ``list_collections``,
plus its own filename grammar and (via
``InSituOfflineCallHandler(OfflineArchiveHandler, InSituCallHandler)``) its ROI
registry.

Register the handler in ``scrappi.api.factory`` after its online sibling so the
online source is preferred when it has the data; the interface's candidate-API
fan-out (``scrappi.interface.perform_query`` / ``download_product``) then falls
through to the offline handler only when the online one can't serve a
query/download.

Satellite offline handler
^^^^^^^^^^^^^^^^^^^^^^^^^^^
``scrappi.api.satellite_offline.SatelliteOfflineCallHandler`` (registered
``"eodag_offline"``, after ``"eodag"``) is the satellite counterpart. **Status:
skeleton** -- structure and flow are in place, the ``TODO``\ s in the module need a
real archive layout to settle.

A satellite scene's footprint, times and cloud cover aren't in its filename, so
this handler reads them from **scrappi's own STAC catalogue tree**. scrappi writes
that tree (``<root>/stac/<collection>/items/.../<id>.json`` + ``collection.json`` +
``catalog.json``) for every product it downloads *when*
``context["fs"]["register_stac_items"]`` is true -- **the default** (see
``scrappi/etc/defaults.yaml``). So an archive scrappi itself populated is served by
this handler; an archive of bare product files with no ``stac/`` tree is not
(``perform_query`` returns empty and warns).

It is mission-agnostic -- ``product_item_from_stac`` rebuilds any mission's item
and a ``scrappi.api.offline_query.CompiledQuery`` (the query geometry / datetimes
parsed once, then ``.matches(product)`` per candidate) applies the filters
client-side, so no per-satellite subclass is needed. ``perform_query``: discover
the requested collections' roots, walk each ``<root>/stac`` once (grouping
collections that share a root), filter each item, and only then build a
filesystem for the survivors. Configuration:

* ``context["api"]["offline_archive_path"]`` -- the archive root (or pass
  ``archive_path=``); no built-in default, an unconfigured handler is inert;
* ``context["api"]["offline_archive_paths"]`` -- optional ``{collection: path}``
  overrides. Otherwise each collection is searched under ``<root>/<collection>/``
  if it holds a ``stac/`` dir, else ``<root>`` -- so a query doesn't traverse a
  multi-terabyte shared archive;
* ``list_collections`` reads ``stac/*/collection.json`` (a bounded glob, cached),
  not a recursive walk -- it runs on every ``get_api_name`` probe;
* ``INDEX_DIRECTORY_SUFFIXES = (".SAFE", ".SEN3")`` -- extracted scenes are
  whole-product directories; ``PRODUCT_NAME_SUFFIXES`` -- the extensions a scene's
  data may carry that its STAC id does not (never ``.json``).

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

