import os
from datetime import datetime as dt
from scrappi.interface import *
import matplotlib.pyplot as plt
from scrappi import ScrappiContext

context = ScrappiContext()
hypernets_archive_path = r"T:\ECO\EOServer\data\insitu\hypernets\archive"
context["fs"]["path"] = hypernets_archive_path

if __name__ == "__main__":
    start = "2025-11-01T00:00:00"
    end = "2025-11-02T00:00:00"

    query = {
        "collections": ["LHYP_L2B_REF"],  # ["S3_EFR"], ["S2_MSI_L1C"],
        "site": "GHNA",
        # "geom": site_def[site],
        "start_time": start,
        "stop_time": end,
    }

    products = perform_query(query, context)

    path = download_product(products, context)
    print(path)
