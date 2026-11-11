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

    max_retrys: 3 # Number of times to retry a failed download (Default: 3)
    retry_wait: 5 # Time to wait between retries in seconds (Default: 5)
    delete_usgs_tmp_file: False # Whether to delete the temporary file created by the USGS provider, which can cause issues with query authentication (Default: false)

    eodag:
        cop_dataspace: # For each provider you want to use, add a section with the provider name (e.g., "cop_dataspace") and your specific credentials and settings:
            priority: 8 # Lower value means lower priority (Default: 0)
            api:
                credentials:
                    username: YOUR_USERNAME
                    password: YOUR_REMOVED_PASSWORD

Providers only reached through a catalogue: DLR EOC Geoservice (EnMAP)
---------------------------------------------------------------------

The default config includes the ``dlr_eoc_geoservice`` provider, which serves e.g. the EnMAP collections
``ENMAP_HSI_L1B``/``L1C``/``L2A`` (see :ref:`querying`). Searching it needs no account; downloading needs a DLR
geoservice login, added like any other provider's:

.. code-block:: yaml

    eodag:
        dlr_eoc_geoservice:
            priority: 1 # Lower value means lower priority (Default: 0)
            auth:
                credentials:
                    username: YOUR_USERNAME
                    password: YOUR_REMOVED_PASSWORD

Keep its priority below the providers you prefer for collections several providers share (it also serves some
Sentinel-2 products). The credentials can equally come from ``EODAG__DLR_EOC_GEOSERVICE__AUTH__CREDENTIALS__USERNAME``
and ``EODAG__DLR_EOC_GEOSERVICE__AUTH__CREDENTIALS__REMOVED_PASSWORD`` (see below). The entry comes from scrappi's defaults, so
an existing user config only needs the ``credentials`` adding (a user config created from the template before this
provider was added won't list it, but still inherits it from the defaults).

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






