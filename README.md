# scrappi

EO Satellite product catalogue retrieval by API or file system.

`scrappi` queries Earth Observation satellite product catalogues from online
APIs (e.g. EODAG, Copernicus Data Space) and local file systems, and returns
structured product datasets ready for download or further processing.

> **Warning:** This software is in beta. Results should be used with
> caution. Please share any feedback via the issue tracker.

## Documentation

The full documentation is available online at:

- https://meteor-toolkit.github.io/scrappi/

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
pip install -e ".[dev]"            # Development tools (ruff, mypy, pytest, pre-commit, …)
pip install -e ".[docs]"           # Documentation build tools (Sphinx, MyST, themes, …)
pip install -e ".[earthaccess]"   # Optional Earthaccess support for the Earthaccess API handler
pip install -e ".[hypernets_api]" # Optional Hypernets API client support
pip install -e ".[all]"            # All optional extras combined
```

Use the extras that match the integrations you need. The core installation already includes the main runtime dependencies, while the optional groups add tools or integrations for development, documentation, Earthaccess, and Hypernets.

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

## Compatibility

`scrappi` requires Python 3.11 or later and is tested on Python 3.11, 3.12,
and 3.13.

## Licence

`scrappi` is released under the GNU Lesser General Public License v3 (LGPLv3).
See the [LICENSE](https://github.com/meteor-toolkit/scrappi/blob/main/LICENSE) file for the full licence text.

## Authors

`scrappi` is developed and maintained by the
[MetEOR Toolkit Team](mailto:team@comet-toolkit.org).
