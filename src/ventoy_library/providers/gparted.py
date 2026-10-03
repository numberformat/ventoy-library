"""GParted Live stable ISO advertised on the official download page."""

import re
from urllib.parse import urlsplit

from packaging.version import Version

from ..downloader import HTTPDownloader
from ..errors import LibraryError
from ..models import Release
from .common import HTTPProvider, checksum, links, read_text


class GPartedProvider(HTTPProvider):
    name = "gparted"
    display_name = "GParted Live"
    category = "rescue"
    architecture = "x86_64"
    metadata_url = "https://gparted.org/download.php"
    checksum_url = "https://gparted.org/gparted-live/stable/CHECKSUMS.TXT"

    def parse(self, html: str) -> tuple[str, str, str]:
        start = html.find("Stable Releases")
        end = html.find("Testing Releases", start + 1)
        if start < 0 or end < 0:
            raise LibraryError("GParted stable release section is missing.")
        stable_html = html[start:end]
        candidates = []
        for url in links(stable_html, self.metadata_url):
            parsed = urlsplit(url)
            if (
                (parsed.scheme, parsed.hostname, parsed.path.rpartition("/")[0])
                != ("https", "downloads.sourceforge.net", "/gparted")
                or parsed.query
                or parsed.fragment
            ):
                continue
            filename = parsed.path.rpartition("/")[2]
            match = re.fullmatch(r"gparted-live-(\d+\.\d+\.\d+-\d+)-amd64\.iso", filename)
            if match:
                candidates.append((Version(match[1]), match[1], filename, url))
        if not candidates:
            raise LibraryError("No stable amd64 GParted ISO advertised on the official page.")
        _, version, filename, url = max(candidates)
        if self.checksum_url not in links(stable_html, self.metadata_url):
            raise LibraryError("GParted checksum manifest link is missing.")
        return version, filename, url

    def get_latest_release(self) -> Release:
        with self.connection() as client:
            version, filename, url = self.parse(
                read_text(client, self.metadata_url, {"gparted.org"})
            )
            digest = checksum(read_text(client, self.checksum_url, {"gparted.org"}), filename)
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
