"""Debian-based Clonezilla Live from the project-endorsed stable file directory."""

import re

from packaging.version import Version

from ..downloader import HTTPDownloader
from ..errors import LibraryError
from ..models import Release
from .common import HTTPProvider, exact_link, links, read_text


class ClonezillaProvider(HTTPProvider):
    name = "clonezilla"
    display_name = "Clonezilla Live"
    category = "rescue"
    architecture = "x86_64"
    # Clonezilla's own downloads page currently presents an HTTP browser challenge.
    # This is its endorsed stable (Debian-based) project directory, not alternative/testing.
    metadata_url = "https://sourceforge.net/projects/clonezilla/files/clonezilla_live_stable/"

    def parse_versions(self, html: str) -> list[tuple[str, str]]:
        candidates = []
        for url in links(html, self.metadata_url):
            match = re.fullmatch(re.escape(self.metadata_url) + r"(\d+\.\d+\.\d+-\d+)/", url)
            if match:
                candidates.append((match[1], url))
        if not candidates:
            raise LibraryError("No stable Clonezilla release directory found.")
        return sorted(
            set(candidates), key=lambda item: Version(item[0].replace("-", ".")), reverse=True
        )

    def parse_release(self, html: str, version: str, directory: str) -> tuple[str, str]:
        filename = f"clonezilla-live-{version}-amd64.iso"
        url = exact_link(html, directory, filename + "/download")
        return filename, url

    def get_latest_release(self) -> Release:
        with self.connection() as client:
            versions = self.parse_versions(
                read_text(client, self.metadata_url, {"sourceforge.net"})
            )
            for version, directory in versions:
                html = read_text(client, directory, {"sourceforge.net"})
                try:
                    filename, url = self.parse_release(html, version, directory)
                except LibraryError:
                    continue
                return Release(
                    self.name,
                    self.display_name,
                    version,
                    self.category,
                    self.architecture,
                    filename,
                    url,
                    HTTPDownloader(client).size(url),
                )
        raise LibraryError("No stable amd64 Clonezilla ISO found.")
