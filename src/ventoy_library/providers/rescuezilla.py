"""Rescuezilla primary 64-bit release, as identified in official release notes."""

import json
import re

from packaging.version import Version

from ..errors import LibraryError
from ..models import Release
from .common import HTTPProvider, checksum, read_text


class RescuezillaProvider(HTTPProvider):
    name = "rescuezilla"
    display_name = "Rescuezilla"
    category = "rescue"
    architecture = "x86_64"
    metadata_url = "https://api.github.com/repos/rescuezilla/rescuezilla/releases?per_page=30"

    def parse(self, data: list) -> tuple[Release, str | None]:
        try:
            stable = []
            for row in data:
                tag = row["tag_name"]
                if (
                    row["draft"]
                    or row["prerelease"]
                    or not isinstance(tag, str)
                    or not re.fullmatch(r"v?\d+(?:\.\d+)+", tag)
                ):
                    continue
                stable.append((Version(tag.removeprefix("v")), tag, row))
            if not stable:
                raise LibraryError("No stable Rescuezilla release found.")
            _, tag, row = max(stable, key=lambda item: item[0])
            version = tag.removeprefix("v")
            # Release notes distinguish one recommended image from other codename builds.
            primary = re.findall(
                rf"\*\*Download the 64-bit version[^\n]*?\["
                rf"(rescuezilla-{re.escape(version)}-64bit\.[a-z]+\.iso)\]",
                row["body"],
                re.I,
            )
            if len(primary) != 1:
                raise LibraryError("Rescuezilla primary 64-bit ISO is missing or ambiguous.")
            filename = primary[0]
            assets = row["assets"]
            matches = [asset for asset in assets if asset["name"] == filename]
            if len(matches) != 1:
                raise LibraryError("Rescuezilla primary 64-bit ISO is missing or ambiguous.")
            asset = matches[0]
            prefix = f"https://github.com/rescuezilla/rescuezilla/releases/download/{tag}/"
            if asset["browser_download_url"] != prefix + filename:
                raise LibraryError("Unexpected Rescuezilla asset URL.")
            sums = [item for item in assets if item["name"] == "SHA256SUM"]
            if len(sums) > 1 or sums and sums[0]["browser_download_url"] != prefix + "SHA256SUM":
                raise LibraryError("Unexpected Rescuezilla checksum URL.")
            release = Release(
                self.name,
                self.display_name,
                version,
                self.category,
                self.architecture,
                filename,
                prefix + filename,
                asset["size"],
            )
            return release, prefix + "SHA256SUM" if sums else None
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            raise LibraryError("Malformed Rescuezilla release metadata.") from exc

    def get_latest_release(self) -> Release:
        with self.connection() as client:
            try:
                data = json.loads(read_text(client, self.metadata_url, {"api.github.com"}))
            except ValueError as exc:
                raise LibraryError("Malformed Rescuezilla release JSON.") from exc
            release, sums_url = self.parse(data)
            if sums_url:
                digest = checksum(
                    read_text(
                        client, sums_url, {"github.com", "release-assets.githubusercontent.com"}
                    ),
                    release.filename,
                )
                return Release(
                    release.provider,
                    release.display_name,
                    release.version,
                    release.category,
                    release.architecture,
                    release.filename,
                    release.url,
                    release.size,
                    "sha256",
                    digest,
                )
            return release
