import os
from datetime import datetime as dt
from scrappi import ScrappiContext
from scrappi import (
    perform_query,
    download_product,
    make_fs,
    get_api_name,
    make_api,
)
import matplotlib.pyplot as plt
import pickle

site_def = {
    "GONA": {
        "latitude_minimum": -23.60472105,
        "longitude_minimum": 15.11465119,
        "latitude_maximum": -23.59568076,
        "longitude_maximum": 15.12446109,
    },
    # "LCFR": [43.55829168, 4.863345627, 43.55948632, 4.86498836],  #same order as dict keys above
    # "RVUS": [38.48687306, -115.7028871, 38.50712799, -115.6771133],
}

example_download_path = os.path.join(
    os.path.dirname(__file__),
    "downloaded_data",
)
file_system = make_fs(example_download_path)
context = ScrappiContext()
context["api"]["preferred_api"] = "radcalnet"
if __name__ == "__main__":
    api_name = "radcalnet"
    start = "2023-02-01T00:00:00"
    end = "2023-03-01T00:00:00"

    query = {
        "collection": "RCN_BOA",
        "site": "GONA",  # ["GONA", "RVUS", "LCFR", "BSCN"],
        "start_time": start,
        "stop_time": end,
    }

    api=get_api_name("RCN_BOA")
    api=make_api(api)
    api.get_roi("GONA")

    products = perform_query(query, context)

    # products.plot_geometries()
    # plt.show()
    products.set_fs(file_system)

    path = download_product(products, context)
    print(path)
