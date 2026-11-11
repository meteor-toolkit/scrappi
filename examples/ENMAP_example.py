"""Query (and optionally download) EnMAP hyperspectral products from DLR's EOC Geoservice through scrappi.

The ENMAP_HSI_* collections are published only in DLR's own STAC catalogue, not in eodag's built-in collection list;
scrappi finds them by asking eodag's providers for their collections (see docs: querying, "Collections published by a
provider's own catalogue"), so they are queried like any other collection.

Searching needs no account. Downloading needs a DLR geoservice login in the scrappi config (``eodag:
dlr_eoc_geoservice: auth: credentials``) or in ``EODAG__DLR_EOC_GEOSERVICE__AUTH__CREDENTIALS__USERNAME`` /
``..._REMOVED_PASSWORD`` -- see docs: config.
"""

import os

from scrappi import ScrappiContext
from scrappi.interface import download_product, make_fs, perform_query

DOWNLOAD = False  # set True to download the first product found (one L1C product is several hundred MB)

# Libya-4 (a pseudo-invariant calibration site), centre
libya4 = {"latitude_minimum": 28.45, "longitude_minimum": 23.29, "latitude_maximum": 28.65, "longitude_maximum": 23.49}

if __name__ == "__main__":
    context = ScrappiContext()
    query = {
        "collections": ["ENMAP_HSI_L1C"],  # also ENMAP_HSI_L1B (sensor geometry), ENMAP_HSI_L2A (surface reflectance)
        "geom": libya4,
        "start_time": "2024-01-01T00:00:00",
        "stop_time": "2024-12-31T23:59:59",
    }
    products = perform_query(query, context)
    print(f"{len(products)} EnMAP L1C product(s) over Libya-4 in 2024")
    for product in products:
        print(" ", product.id, product.start_time, f"cloud={product.cloud_fraction}")

    if DOWNLOAD and len(products):
        path = os.path.join(os.path.dirname(__file__), "downloaded_data")
        products.set_fs(make_fs(path))
        first = products[0]
        print("Downloaded to", download_product(first, context))
