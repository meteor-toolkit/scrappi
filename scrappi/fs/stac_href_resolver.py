from pathlib import Path
from urllib.parse import urlparse

from typing import Union
from pystac import STACObject
import json

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]


class StacHrefResolver:
    """
    Resolves logical STAC and asset URIs to concrete locations.

    Logical schemes:
      - stac://...   -> STAC JSON files
      - asset://...  -> data assets

    Resolution targets can be:
      - local filesystem paths
      - HTTP base URLs
    """

    def __init__(
        self,
        stac_root: str | None = None,
        data_root: str | None = None,
        stac_base_url: str | None = None,
        data_base_url: str | None = None,
    ):
        self.stac_root = Path(stac_root).resolve() if stac_root else None
        self.data_root = Path(data_root).resolve() if data_root else None
        self.stac_base_url = stac_base_url.rstrip("/") + "/" if stac_base_url else None
        self.data_base_url = data_base_url.rstrip("/") + "/" if data_base_url else None

    # ---------- Resolution from logical URI to path / URL ----------

    def resolve(self, href: str) -> str | Path:
        """Resolve a logical HREF to a concrete path or URL.
        The HREF should use the "stac://" or "asset://" scheme to indicate the type of resource being referenced.
        :param href: logical HREF to resolve
        :return: resolved path or URL
        """
        parsed = urlparse(href)

        logical_path = parsed.netloc + parsed.path
        logical_path = logical_path.lstrip("/")

        if parsed.scheme == "stac":
            return self._resolve_stac(logical_path)

        if parsed.scheme == "asset":
            return self._resolve_asset(logical_path)

        raise ValueError(f"Unsupported HREF scheme: {href}")

    def _resolve_stac(self, rel: str):
        """Resolve a logical STAC HREF to a concrete path or URL.
        :param rel: relative path of the STAC JSON file to resolve
        :return: resolved path or URL
        """
        if self.stac_base_url:
            return self.stac_base_url + rel
        if self.stac_root:
            return self.stac_root / rel
        raise RuntimeError("No STAC resolution target configured")

    def _resolve_asset(self, rel: str):
        """Resolve a logical asset HREF to a concrete path or URL.

        :param rel: relative path of the asset file to resolve
        :return: resolved path or URL
        """
        if self.data_base_url:
            return self.data_base_url + rel
        if self.data_root:
            return self.data_root / rel
        raise RuntimeError("No asset resolution target configured")

    @staticmethod
    def write_stac_object(obj: STACObject, path: Union[str, Path]) -> None:
        """
        Persist a STAC object to disk WITHOUT:
        - resolving links
        - resolving root/parent
        - modifying hrefs
        :param obj: STAC object to write
        :param path: path to write the STAC JSON to
        """

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as f:
            json.dump(obj.to_dict(transform_hrefs=False), f, indent=2)
