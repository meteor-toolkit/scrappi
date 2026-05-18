.. currentmodule:: scrappi

.. _api:

##################
API call handlers
##################

scrappi is essentially a wrapper around existing functionality implemented in other API tools, such as
eodag and RadCalNet. Scrappi allows to use these API's using a consistent input and output format.
Scrappi is designed so that new API's can be easily added (see :ref:`_developer_api`).
All the api's have some core functionality implemented, such as querying and downloading products.
This functionality is accessed in the same way for each API through the interface functions (see :ref:`interface`).
Here we provide some details on the included API's, and specifically how credentials should be provided.


eodag
========
EODAG (Earth Observation Data Access Gateway; `EODAG readthedocs <https://eodag.readthedocs.io/>`_) is a
command line tool and a Python package for searching and downloading remotely sensed images while offering
a unified API for data access regardless of the data provider. It provides a unified access to many different
data providers such as usgs, peps, creodias, ecmwf and many more (see `this link for complete list <https://eodag.readthedocs.io/en/stable/getting_started_guide/providers.html>`_).

In order to access the data from these data providers, typically an account first has to be made by registering with the provider.
EODAG provides further info on how to do this `here <https://eodag.readthedocs.io/en/stable/getting_started_guide/register.html>`_
For some providers, data can be queried without a user account, but registration is still necessary for data download.

Once an account has been created with the provider, the login information must be provided to EODAG.
The recommended option is to provide a configurations file, as described in :ref:`config`::

    from scrappi import ScrappiContext
    context = ScrappiContext(r"path/to/your/config.yaml")

In addition to setting the credentials, it is also possible to set a priority for the different providers in this file. To find out which
provider supplies your data use this `table <https://eodag.readthedocs.io/en/stable/getting_started_guide/product_types.html>`_ and search for the product.
It is recommended that high priority is given to providers that supply the required product,
see `this link <https://eodag.readthedocs.io/en/stable/getting_started_guide/configure.html>`_ for further information.
It is also possible to increase the timeout parameter to enable longer searches for larger datasets.
If experiencing a timeout error with the previous two methods, attempt to provide credentials with the .yml file

The configuration file also allows to specify a "preferred_provider", which allows to specify which provider should be used first.
Alternatively, it is also possible to set the prefered provider for eodag by using a ":" in the api name::

    from scrappi.interface import make_api
    api=make_api("eodag:usgs")
