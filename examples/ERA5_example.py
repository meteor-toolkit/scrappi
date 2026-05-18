import os
from scrappi import (
    ScrappiContext,
    perform_query,
    download_product,
    make_fs,
)

lat, lon = -23.60153, 15.12589  # GHNA location
example_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples")

context = ScrappiContext()
# context["api"]["eodag_logging_level"]=3
context["fs"]["path"] = example_path
file_system = make_fs(context=context)

if __name__ == "__main__":

    api_name = "eodag"
    start = "2025-07-01T00:00:00"
    end = "2025-08-01T00:00:00"

    query = {
        "collections": ["ERA5_SL"],
        "geom": [
            lat - 0.25,
            lon - 0.25,
            lat + 0.25,
            lon + 0.25,
        ],  # making sure there are at least 2 grid points in query
        "start_time": start,
        "stop_time": end,
        "variable": [
            "total_column_water_vapour",
            "total_column_ozone",
            "surface_pressure",
        ],
        "ecmwf_data_format": "netcdf",
        "ecmwf_download_format": "unarchived",
        "ecmwf_product_type": [
            "ensemble_members"
        ],  # use only one at a time: 'reanalysis', "ensemble_spread", "ensemble_mean"
        "time": [
            # '00:00', '01:00', '02:00',
            # '03:00', '04:00', '05:00',
            "06:00",  # '07:00', '08:00',
            "09:00",  # '10:00', '11:00',
            "12:00",  # '13:00', '14:00',
            "15:00",  # '16:00', '17:00',
            "18:00",  # '19:00', '20:00',
            # '21:00', '22:00', '23:00'
        ],
    }

    products = perform_query(query, context=context)

    products.set_fs(file_system)

    path = download_product(products, context=context)
    print(path)
