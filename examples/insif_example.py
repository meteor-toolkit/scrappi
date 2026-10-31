import os
from datetime import datetime as dt
from scrappi.interface import *
import matplotlib.pyplot as plt
from scrappi import ScrappiContext

from scrappi.api.insif import INSIFCallHandler

example_download_path = os.path.join(
    os.path.dirname(__file__),
    "downloaded_data",
)
file_system = make_fs("t-drive") #example_download_path)
context = ScrappiContext()

if __name__ == "__main__":
    start = "2026-10-03T08:00:00"
    end = "2026-10-03T10:00:00"
    context["api"]["preferred_api"] = "insif"

    query = {
        "collections": ["INSIF_RADIRRREF"],  # ["S3_EFR"], ["S2_MSI_L1C"],
        "flox_sn": "JB-010-ES",
        # "geom": site_def[site],
        "start_time": start,
        "stop_time": end,
    }

    products = perform_query(query, context)

    products.set_fs(file_system)

    path = download_product(products, context)
    print(path)
