.. _product:

##################################
Product Item and Product Item Set
##################################

Product Item
=============

.. ipython:: python
   :okwarning:

      # Try to build a shapely Polygon if available; otherwise use a simple tuple
      try:
         from shapely.geometry import Polygon
         s2_polygon = Polygon(
                  (
                     (148.1127268619, -36.227897298303),
                     (149.3338263627, -36.210306946434),
                     (149.30514540706, -35.22112283106),
                     (148.11635294039, -35.23784402863),
                     (148.09975983609, -35.290089152181),
                     (148.1127268619, -36.227897298303),
                  )
               )
      except Exception:
         s2_polygon = (
            (148.1127268619, -36.227897298303),
            (149.3338263627, -36.210306946434),
            (149.30514540706, -35.22112283106),
            (148.11635294039, -35.23784402863),
            (148.09975983609, -35.290089152181),
            (148.1127268619, -36.227897298303),
         )

Items from product catalogues can be represented with :py:class:`~scrappi.product.ProductItem` objects.
They are built with a set of metadata that uniquely defines the product item.
There are also attributes for the api and filesystem of the :py:class:`~scrappi.product.ProductItem` object,
which are used to define the path and allow for easy downloads (see below):

.. ipython:: python
   :okwarning:
   from datetime import datetime
   from scrappi import ProductItem
   from scrappi import set_credentials

   s2_pi = ProductItem(
      constellation='Sentinel-2',
      platform='S2A',
      collection='S2_MSI_L1C',
      id='S2A_MSIL1C_20220608T000231_N0400_R030_T55HFA_20220608T012804',
      geometry=s2_polygon,
      start_time='2022-06-08T00:02:31',
      stop_time='2022-06-08T00:02:31',
      quicklook = "",
      api='eodag',
      filesystem="./",
   )
   print(s2_pi)

These product metadata are then accessible as attributes of the :py:class:`~scrappi.product.ProductItem` object.

.. ipython:: python
   :okwarning:
   print(s2_pi.geometry)


:py:class:`~scrappi.product.ProductItem` objects allow you to very easily plot the product geometry with the :py:meth:`~scrappi.product.ProductItem.plot_geometry()` method.

.. ipython:: python
   :okwarning:
   # plotting may not be available in all build environments; swallow errors
   try:
      s2_pi.plot_geometry(padding_type="rel", padding_val=1, geometry_color="y")
   except Exception:
      pass

There are also helper functions for easily getting the path where the product should be stored, and for downloading
the products to this path.

.. ipython:: python
   :okwarning:
   print(s2_pi.get_path())

The above functions for getting the path use the file system (see :ref:`filesystem`) to generate these paths.
The file system associated with a given ProductItem can be updated using the set_fs() function:

.. ipython:: python
   :okwarning:
    s2_pi.set_fs("t-drive")
    print(s2_pi.get_path())

It is also possible to move a ProductItem from the current file system (to which the product has been previously downloaded) to a new filesystem.

.. ipython:: python
   :okwarning:
    s2_pi.move_product("t-drive")
    print(s2_pi.get_path())

Product Item Sets
=================

.. ipython:: python
   :okwarning:
   from datetime import datetime
   from shapely.geometry import Polygon

   S3_PRODUCT_EXAMPLE_1 = {
                    "constellation": "Sentinel-3",
                    "platform": "S3B",
                    "collection": "S3_EFR",
                    "id": "S3B_OL_1_EFR____20220517T083238_20220517T083538_20220517T205009_0179_066_078_3420_PS2_O_NT_002",
                    "geometry": "POLYGON ((21.252 -34.5187, 21.8983 -31.8836, 22.5277 -29.2403, 23.1427 -26.5948, 23.7457 -23.9471, 23.0766 -23.8181, 22.4168 -23.6878, 21.7545 -23.554, 21.095 -23.4188, 20.4393 -23.2775, 19.781 -23.1351, 19.1288 -22.9881, 18.4738 -22.8428, 17.8229 -22.6926, 17.1738 -22.5451, 16.5212 -22.3887, 15.8711 -22.23, 15.2236 -22.0691, 14.5757 -21.9053, 13.9278 -21.7384, 13.2816 -21.5691, 12.6433 -21.3989, 12.0034 -21.2254, 11.3643 -21.0485, 10.5243 -23.6423, 9.63737 -26.2286, 8.698 -28.8061, 7.70076 -31.3688, 8.38884 -31.5712, 9.07972 -31.7691, 9.77638 -31.964, 10.4712 -32.1537, 11.1726 -32.3406, 11.8722 -32.5222, 12.5793 -32.7012, 13.286 -32.8756, 13.9979 -33.0466, 14.7147 -33.2089, 15.4305 -33.3715, 16.1486 -33.5271, 16.871 -33.6842, 17.5955 -33.834, 18.3207 -33.9817, 19.0503 -34.1217, 19.781 -34.2582, 20.5158 -34.3907, 21.252 -34.5187))",
                    "start_time": "2022-05-17T08:32:38+00:00",
                    "stop_time": "2022-05-17T08:35:38+00:00",
                    "url": "",
                    "quicklook": "",
                    "filter_dict": {},
                }
               
   L8_PRODUCT_EXAMPLE_1 = {
                    "constellation": "Landsat-8",
                    "platform": "LC08",
                    "collection": "LANDSAT_C2L1",
                    "id": "LC08_L1TP_172030_20220120_20220127_02_T2C",
                    "geometry": "POLYGON ((41.0856816815745 44.24112580952904, 41.08680806465548 44.24110522982958, 43.393265796852866 43.82234984482247, 43.39318664569185 43.821272570187, 42.777074012665516 42.11245652952103, 42.777074012665516 42.11245652952103, 40.531355852298944 42.52837451259882, 40.531362450839524 42.52864459095809, 41.0856816815745 44.24112580952904))",
                    "start_time": "2022-06-07T23:40:08.609447+00:00",
                    "stop_time": "2022-06-07T23:45:40.379447+00:00",
                    "url": "",
                    "quicklook": "",
                    "filter_dict": {},
                }
   L8_PRODUCT_EXAMPLE_2 = {
                    "constellation": "Landsat-8",
                    "platform": "LC08",
                    "collection": "LANDSAT_C2L1",
                    "id": "LC08_L1TP_172030_20220120_20220127_02_T2B",
                    "geometry": "POLYGON ((40.17522471269021 41.3861400123577, 40.17558345095594 41.3861363475318, 42.38002952306863 40.978818955572315, 42.38000194853155 40.978279401481856, 41.80764599721697 39.26470702042967, 41.805909323763835 39.26474891065633, 39.65908676451177 39.6694679250438, 39.65908676451177 39.6694679250438, 40.17522471269021 41.3861400123577))",
                    "start_time": "2022-06-07T23:30:08.609447+00:00",
                    "stop_time": "2022-06-07T23:45:40.379447+00:00",
                    "url": "",
                    "quicklook": "",
                    "filter_dict": {},
                }
   L8_PRODUCT_EXAMPLE_3 =
                {
                    "constellation": "Landsat-8",
                    "platform": "LC08",
                    "collection": "LANDSAT_C2L1",
                    "id": "LC08_L1TP_172030_20220120_20220127_02_T2A",
                    "geometry": "POLYGON ((42.06239725042473 47.09014884645623, 42.063186749290715 47.090169109917824, 44.48843284961724 46.65748606317669, 44.48843284961724 46.65748606317669, 43.81882313084526 44.953559032103655, 43.81806263359167 44.95355116301529, 41.46673146290274 45.381351153094556, 41.46671465356733 45.381620678652574, 42.06239725042473 47.09014884645623))",
                    "start_time": "2022-06-07T23:35:08.609447+00:00",
                    "stop_time": "2022-06-07T23:45:40.379447+00:00",
                    "url": "",
                    "quicklook": "",
                    "filter_dict": {},
                }
            
   l8_pi_1 = ProductItem(
      constellation=L8_PRODUCT_EXAMPLE_1["constellation"],
      platform=L8_PRODUCT_EXAMPLE_1["platform"],
      collection=L8_PRODUCT_EXAMPLE_1["collection"],
      id=L8_PRODUCT_EXAMPLE_1["id"],
      geometry=L8_PRODUCT_EXAMPLE_1["geometry"],
      start_time=L8_PRODUCT_EXAMPLE_1["start_time"],
      stop_time=L8_PRODUCT_EXAMPLE_1["stop_time"],
      prod_dict=L8_PRODUCT_EXAMPLE_1["prod_dict"],
   )
   l8_pi_2 = ProductItem(
      constellation=L8_PRODUCT_EXAMPLE_2["constellation"],
      platform=L8_PRODUCT_EXAMPLE_2["platform"],
      collection=L8_PRODUCT_EXAMPLE_2["collection"],
      id=L8_PRODUCT_EXAMPLE_2["id"],
      geometry=L8_PRODUCT_EXAMPLE_2["geometry"],
      start_time=L8_PRODUCT_EXAMPLE_2["start_time"],
      stop_time=L8_PRODUCT_EXAMPLE_2["stop_time"],
      prod_dict=L8_PRODUCT_EXAMPLE_2["prod_dict"],
   )
   l8_pi_3 = ProductItem(
      constellation=L8_PRODUCT_EXAMPLE_3["constellation"],
      platform=L8_PRODUCT_EXAMPLE_3["platform"],
      collection=L8_PRODUCT_EXAMPLE_3["collection"],
      id=L8_PRODUCT_EXAMPLE_3["id"],
      geometry=L8_PRODUCT_EXAMPLE_3["geometry"],
      start_time=L8_PRODUCT_EXAMPLE_3["start_time"],
      stop_time=L8_PRODUCT_EXAMPLE_3["stop_time"],
      prod_dict=L8_PRODUCT_EXAMPLE_3["prod_dict"],
   )

Several :py:class:`~scrappi.product.ProductItem` objects can be stored together as a :py:class:`~scrappi.product.ProductItemSet`.

.. ipython:: python
   :okwarning:
   from scrappi import ProductItemSet
   pis = ProductItemSet([l8_pi_1, l8_pi_2, l8_pi_3])
   print(pis)

.. ipython:: python
   :okexcept:
   print(len(pis))
   print(pis[0].id)
   for pi in pis:
      print(pi.start_time)

.. ipython:: python
   :okwarning:
   pis.sort(sort_by="start_time")
   print(pis)

.. ipython:: python
   :okwarning:
   try:
      pis.plot_geometries(padding_type=None, label_by="collection")
   except Exception:
      pass

.. ipython:: python
   :okwarning:
   pis.set_fs("t-drive")
   pis.move_product("./")
   print(pis.get_path())