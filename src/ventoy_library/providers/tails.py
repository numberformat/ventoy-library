"""Tails stable amd64 ISO from its machine-readable update metadata."""

import json
import re

from packaging.version import Version

from ..errors import LibraryError
from ..models import Release
from .common import HTTPProvider, read_text


class TailsProvider(HTTPProvider):
    name = "tails"
    display_name = "Tails"
    category = "security"
    architecture = "x86_64"
    metadata_url = "https://tails.net/install/v2/Tails/amd64/stable/latest.json"

    def parse(self, data: dict) -> Release:
        try:
            if (
                data["build_target"] != "amd64"
                or data["channel"] != "stable"
                or data["product-name"] != "Tails"
            ):
                raise LibraryError("Unexpected Tails product, architecture or channel.")
            candidates = []
            for installation in data["installations"]:
                version = installation["version"]
                if not isinstance(version, str) or not re.fullmatch(r"\d+(?:\.\d+)+", version):
                    continue
                for path in installation["installation-paths"]:
                    if path["type"] != "iso":
                        continue
                    files = path["target-files"]
                    if len(files) != 1:
                        raise LibraryError("Ambiguous Tails ISO metadata.")
                    artifact = files[0]
                    filename = f"tails-amd64-{version}.iso"
                    url = (
                        f"https://download.tails.net/tails/stable/tails-amd64-{version}/{filename}"
                    )
                    if artifact["url"] != url:
                        raise LibraryError("Unexpected Tails ISO URL.")
                    candidates.append(
                        (
                            Version(version),
                            Release(
                                self.name,
                                self.display_name,
                                version,
                                self.category,
                                self.architecture,
                                filename,
                                url,
                                artifact["size"],
                                "sha256",
                                artifact["sha256"],
                            ),
                        )
                    )
            if not candidates:
                raise LibraryError("No stable amd64 Tails ISO found.")
            return max(candidates, key=lambda item: item[0])[1]
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            raise LibraryError("Malformed Tails release metadata.") from exc

    def get_latest_release(self) -> Release:
        with self.connection() as client:
            try:
                data = json.loads(read_text(client, self.metadata_url, {"tails.net"}))
            except ValueError as exc:
                raise LibraryError("Malformed Tails release JSON.") from exc
            return self.parse(data)
