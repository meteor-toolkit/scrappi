import os
from datetime import datetime as dt
from scrappi.interface import *
import matplotlib.pyplot as plt
from scrappi import ScrappiContext

example_download_path = os.path.join(
    os.path.dirname(__file__),
    "downloaded_data",
)
context = ScrappiContext()
context["fs"]["path"] = example_download_path
if __name__ == "__main__":
    start = "2025-11-01T00:00:00"
    end = "2025-11-02T00:00:00"
    context["api"]["preferred_api"] = "stac"

    query = {
        "collections": ["LHYP_L2B_REF"],  # ["S3_EFR"], ["S2_MSI_L1C"],
        # "geom": site_def[site],
        "start_time": start,
        "stop_time": end,
        "asset_state": "downloaded",
    }

    products = perform_query(query, context)

    path = download_product(products, context)
    print(path)
