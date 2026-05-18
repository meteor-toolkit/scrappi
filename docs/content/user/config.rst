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






