.. _config:

###############################
Configuring scrappi
###############################

This page explains how to configure the necessary files so scrappi can query and download products from the API of your choice, and save them to the desired location on your computer. The configuration process involves setting up API credentials, defining file system paths, and customizing scrappi's behavior through user config files.

This page covers:

* preparing scrappi config files
* creating an eodag configuration and credentials


Templates and example files:
========

The project includes default templates and configs you should copy and edit:

  * **Default API config:** ``etc/default_api_config.yaml``
  * **User config template:** ``etc/config_templates/user_config.yaml``
  * **Example query script:** ``examples/eodag_example.py``

How scrappi uses API configs
========

scrappi reads API configuration from the repository ``etc`` files and from the user config you place on your system. Typical steps:

* Copy the default API config into your editable config (or merge values into your global scrappi user config).
* Point scrappi to the ``api`` name you want to use (for eodag this is typically ``eodag``).


Important:

* Provider configuration keys vary between providers. Consult eodag's provider docs for exact names and authentication methods.
* Keep credentials secure (do not commit private keys or passwords to a repository).

scrappi API config example
========
The following is a minimal example of how to configure scrappi to use eodag as the API for data access. This would be part of the user config file, e.g., ``scrappi\etc\config_templates\user_config.yaml``:

.. code-block:: yaml

    fs:
        path: # Path to the filesystem root (e.g., "t-drive" or a local directory)


    api:
        preferred_api: "eodag" 
        preferred_provider: "cop_dataspace"

    max_retries: 3 # Number of times to retry a failed download (Default: 3)
    retry_wait: 5 # Time to wait between retries in seconds (Default: 5)
    delete_usgs_tmp_file: False # Whether to delete the temporary file created by the USGS provider, which can cause issues with query authentication (Default: false)

    eodag:
        cop_dataspace: # For each provider you want to use, add a section with the provider name (e.g., "cop_dataspace") and your specific credentials and settings:
            priority: 8 # Lower value means lower priority (Default: 0)
            api:
                credentials:
                    username: YOUR_USERNAME
                    password: YOUR_REMOVED_PASSWORD

Adding a provider's credentials
-------------------------------

Any *eodag* provider can be configured under ``eodag``, by its *eodag* provider name, with a ``priority`` and its
credentials (the credential keys -- e.g. under ``auth`` or ``api`` -- depend on the provider; see *eodag*'s provider
docs). ``priority`` decides which provider a collection served by several providers is fetched from (higher wins); a
provider needs a positive priority for *scrappi* to apply its entry when setting up *eodag*. Providers already in
*scrappi*'s defaults only need their credentials filling in -- a user config made from an older template still
inherits any provider added to the defaults since.

Some providers let anyone search but need an account to download. For example, DLR's EOC Geoservice
(``dlr_eoc_geoservice``, which publishes e.g. the EnMAP collections -- see :ref:`querying`) is in the defaults at
priority 1, below the providers preferred for the few collections it shares with them; downloading from it needs a DLR
geoservice login:

.. code-block:: yaml

    eodag:
        dlr_eoc_geoservice:
            priority: 1 # Lower value means lower priority (Default: 0)
            auth:
                credentials:
                    username: YOUR_USERNAME
                    password: YOUR_REMOVED_PASSWORD

The credentials can equally come from environment variables, e.g.
``EODAG__DLR_EOC_GEOSERVICE__AUTH__CREDENTIALS__USERNAME`` and ``..._REMOVED_PASSWORD`` (see below).

Credentials in a notebook, script or CI job
-------------------------------------------

Credentials do not have to be written to a config file. Whichever way they are provided, an unset entry (the default
``username: null``) never overrides a credential found elsewhere, and a credential in the context takes priority over the
environment variables.

* **In the context**, for example from a secrets store, by adding them to the dictionary (or ``eomatch`` context) that scrappi is given:

  .. code-block:: python

      context = ScrappiContext(
          {
              "eodag": {"cop_dataspace": {"auth": {"credentials": {"username": "...", "password": "..."}}}},
              "RadCalNet": {"credentials": {"username": "...", "password": "..."}},
          }
      )

* **As environment variables**: ``RADCALNET_USERNAME`` and ``RADCALNET_REMOVED_PASSWORD`` for RadCalNet, and
  ``EODAG__<PROVIDER>__AUTH__CREDENTIALS__USERNAME`` and ``EODAG__<PROVIDER>__AUTH__CREDENTIALS__REMOVED_PASSWORD`` for an eodag
  provider (for example ``EODAG__COP_DATASPACE__AUTH__CREDENTIALS__USERNAME``).






