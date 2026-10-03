"""FreeBSD production amd64 disc1 releases."""

import re

from packaging.version import Version

from ..downloader import HTTPDownloader
from ..errors import LibraryError
from ..models import Release
from .common import HTTPProvider, exact_link, links, read_text


class FreeBSDProvider(HTTPProvider):
    name = "freebsd"
    display_name = "FreeBSD"
    category = "other"
    architecture = "x86_64"
    metadata_url = "https://download.freebsd.org/releases/amd64/amd64/ISO-IMAGES/"

    def parse_versions(self, html: str) -> list[tuple[str, str]]:
        candidates = []
        for url in links(html, self.metadata_url):
            match = re.fullmatch(re.escape(self.metadata_url) + r"(\d+\.\d+)/", url)
            if match:
                candidates.append((match[1], url))
        if not candidates:
            raise LibraryError("No FreeBSD release directories found.")
        return sorted(candidates, key=lambda item: Version(item[0]), reverse=True)

    def parse_release(self, html: str, version: str, directory: str) -> tuple[str, str, str]:
        filename = f"FreeBSD-{version}-RELEASE-amd64-disc1.iso"
        url = exact_link(html, directory, filename)
        manifest = exact_link(html, directory, f"CHECKSUM.SHA256-FreeBSD-{version}-RELEASE-amd64")
        return filename, url, manifest

    @staticmethod
    def parse_checksum(text: str, filename: str) -> str:
        match = re.search(rf"^SHA256 \({re.escape(filename)}\) = ([0-9a-fA-F]{{64}})$", text, re.M)
        if not match:
            raise LibraryError(f"No authoritative FreeBSD SHA256 checksum for {filename}.")
        return match[1].lower()

    def get_latest_release(self) -> Release:
        with self.connection() as client:
            versions = self.parse_versions(
                read_text(client, self.metadata_url, {"download.freebsd.org"})
            )
            for version, directory in versions:
                html = read_text(client, directory, {"download.freebsd.org"})
                try:
                    filename, url, manifest = self.parse_release(html, version, directory)
                except LibraryError:
                    continue  # A newer directory may contain only BETA or RC files.
                digest = self.parse_checksum(
                    read_text(client, manifest, {"download.freebsd.org"}), filename
                )
                return Release(
                    self.name,
                    self.display_name,
                    version,
                    self.category,
                    self.architecture,
                    filename,
                    url,
                    HTTPDownloader(client).size(url),
                    "sha256",
                    digest,
                )
        raise LibraryError("No production FreeBSD amd64 disc1 ISO found.")
