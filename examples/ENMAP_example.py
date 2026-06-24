from pystac_client import Client

catalog = Client.open("https://geoservice.dlr.de/eoc/ogc/stac/v1/")

search = catalog.search(
    collections=["enmap-l2a"],
    bbox=[-90, 57.1, 90, 57.3],  # Aberdeen example
    datetime="2024-01-01/2025-12-31"
)

items = list(search.get_items())
print(len(items))
