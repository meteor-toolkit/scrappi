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

Offline (``"eodag_offline"``)
    Resolves satellite scenes from a local archive instead of the network, as a
    fallback in the candidate-API list (after ``"eodag"``) -- for data received
    directly from a provider with no online API, e.g. a dataset not yet published.
    It reads each scene's metadata from a STAC catalogue tree (``<root>/stac/...``)
    -- either the one scrappi writes automatically on download (when
    ``fs.register_stac_items`` is true, the default), or one you build once for an
    archive scrappi never downloaded:

    .. code-block:: python

        from scrappi import make_api

        handler = make_api("eodag_offline")
        handler.harvest("S2_MSI_L1C")   # once, or re-run later for new arrivals

    Querying never reads a product file -- only the already-built STAC index --
    so it stays fast regardless of archive size. ``harvest`` is the slower,
    explicit step that reads a product's own manifest (footprint, acquisition
    time, cloud cover; not the actual imagery) via `eoio
    <https://gitlab.npl.co.uk/eco/tools/eoio>`_ for any product whose metadata
    isn't derivable from its filename alone. eoio is an optional extra, needed
    only for ``harvest``, not for querying an already-harvested archive::

        pip install 'scrappi[satellite_offline]'

    An archive (or collection within it) with **no** ``stac/`` tree at all is not
    served by ``perform_query`` -- it returns nothing and warns, naming ``harvest``
    as the fix.

    Re-running ``harvest`` for new arrivals is safe: a product that already has a
    STAC item (harvested before, or downloaded online) is skipped, never
    duplicated, unless you pass ``overwrite=True`` to rewrite it. If a
    long-lived process queried the archive before a ``harvest`` run happened
    elsewhere, call ``handler.clear_cache()`` (or re-create the handler) so it
    notices the newly-harvested products.

    .. code-block:: yaml

        api:
            offline_archive_path: /path/to/satellite/archive
            offline_archive_paths:            # optional per-collection overrides
                S2_MSI_L1C: /fast/disk/s2

    Each collection is searched under ``<root>/<collection>/`` if present, else
    ``<root>``. Works for any mission with no per-satellite code required for
    querying.


RadCalNet
=========
RadCalNet (`radcalnet.org <https://www.radcalnet.org>`_) is a network of instrumented
sites providing near-simultaneous surface and top-of-atmosphere reflectance for
satellite radiometric calibration and validation. Each site and day is delivered as
two files: ``*.output`` (the modelled **top-of-atmosphere** reflectance, collection
``RCN_TOA``) and ``*.input`` (the measured **surface / bottom-of-atmosphere**
reflectance and atmospheric state, collection ``RCN_BOA``).

**Built-in sites** (GONA, BTCN, BSCN, LCFR, RVUS) work with no configuration.
Any other site -- e.g. a newer one not yet on the portal -- needs its
latitude/longitude and half-ROI added to the context, no code change:

.. code-block:: yaml

    RadCalNet:
        site_definitions:
            ERUS:
                latitude: 43.7380
                longitude: -96.6304
                default_roi: 45          # metres from the centre to each edge

Online (``"radcalnet"``)
    Fetches files from the RadCalNet JSON API. Credentials go under
    ``RadCalNet`` in the config (``username`` / ``password``).

Offline (``"radcalnet_offline"``)
    Resolves files from a local archive instead of the network -- for a site not
    published online, or as a fallback. Point it at the archive root with:

    .. code-block:: yaml

        RadCalNet:
            offline_archive_path: /path/to/radcalnet/archive

    The tree is searched recursively; only the filename matters (the standard
    ``<site><instrument>_<year>_<doy>_<version>.input``/``.output`` convention), so
    any layout works. When several reprocessings of one day are present, only the
    newest version is returned. ``radcalnet_offline`` is listed after ``radcalnet``
    in the candidate list, so the online portal is used whenever it has the data.
