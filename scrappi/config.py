from processor_tools.config import ConfigInit
import os.path

config_init = ConfigInit(
    package_name="scrappi",
    configs={
        "scrappi_config.yaml": os.path.join(
            os.path.dirname(__file__), "etc", "config_templates", "initial_config.yaml"
        ),
    },
    config_directory=None,  # default is ~/.scrappi, but can be set to a different directory if desired (e.g. for testing)
    config_directory_file_path=None,  # default is ~/.processor_tools/scrappi_config_directory.txt, but can be set to a different file if desired (e.g. for testing)
)


def init_cli():
    config_init.cli()
