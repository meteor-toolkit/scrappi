# scrappi

EO Satellite product catalogue retrieval by API or file system.

`scrappi` queries Earth Observation satellite product catalogues from online
APIs (e.g. EODAG, Copernicus Data Space) and local file systems, and returns
structured product datasets ready for download or further processing.

> **Warning:** This software is in beta. Results should be used with
> caution. Please share any feedback via the issue tracker.

## Usage

### Virtual environment

It is always recommended to use a virtual environment for each Python project.
Use your preferred environment manager, or create one with:

```bash
python -m venv venv
```

Activate it on Windows with `venv\Scripts\activate`, or on macOS/Linux with
`source venv/bin/activate`.

### Installation

Install the package and its core dependencies:

```bash
pip install -e .
```

Optional extras are available depending on your use case:

```bash
pip install -e ".[dev]"    # Development tools (ruff, mypy, pytest, …)
pip install -e ".[docs]"   # Documentation build (sphinx, …)
```

### Development

Install the pre-commit hooks after cloning:

```bash
pre-commit install
```

When you commit, `ruff` will lint and format your code. If it makes
corrections the commit will be aborted so you can review the changes — just
commit again once you are happy.

Run the test suite with:

```bash
pytest
```

### Quickstart

#### Setting credentials

Most online satellite catalogues require authentication before they can be
queried for products. This can be done using the config file.

#### Perform a query

Once a suitable API has been identified for a product, use it to perform a
query:

```python
from scrappi.interface import perform_query
import datetime as dt

api_name = "eodag"
products = perform_query(
    api_name,
    {
        "collections": ["LANDSAT_C2L1"],
        "start_time": dt.datetime(2022, 1, 20, 7),
        "stop_time": dt.datetime(2022, 1, 20, 8, 30),
        "geom": {
            "latitude_minimum": 40,
            "longitude_minimum": 30,
            "latitude_maximum": 50,
            "longitude_maximum": 50,
        },
    },
)
```

#### Download an identified product

After querying, set a filesystem and download the products:

```python
from scrappi.interface import download_product, make_fs

fs = make_fs("./", organise_data=False)
products.set_fs(fs)
path_list = download_product(api_name, products)
```

Please refer to the [documentation](https://scrappi.readthedocs.io/en/latest/)
for further information.

## Compatibility

`scrappi` requires Python 3.11 or later and is tested on Python 3.11, 3.12,
and 3.13.

## Licence

`scrappi` is released under the GNU Lesser General Public License v3 (LGPLv3).
See the [LICENSE](https://github.com/meteor-toolkit/scrappi/blob/main/LICENSE) file for the full licence text.

## Authors

`scrappi` is developed and maintained by the
[MetEOR Toolkit Team](mailto:team@comet-toolkit.org).
