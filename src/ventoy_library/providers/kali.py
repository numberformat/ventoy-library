"""Kali's tested current live amd64 release."""

from packaging.version import Version

from ..downloader import HTTPDownloader
from ..errors import LibraryError
from ..models import Release
from .common import HTTPProvider, checksum, exact_link, index_artifact, read_text


class KaliProvider(HTTPProvider):
    name = "kali"
    display_name = "Kali Linux"
    category = "security"
    architecture = "x86_64"
    metadata_url = "https://cdimage.kali.org/current/"
    pattern = r"kali-linux-(\d{4}\.\d+)-live-amd64\.iso"

    def parse(self, html: str) -> tuple[str, str, str, str]:
        try:
            direct = index_artifact(html, self.metadata_url, self.pattern)
        except LibraryError:
            direct = None
        try:
            torrent = index_artifact(html, self.metadata_url, self.pattern + r"\.torrent")
        except LibraryError:
            torrent = None
        if torrent and (direct is None or Version(torrent[0]) > Version(direct[0])):
            raise LibraryError(
                f"Kali {torrent[0]} lists the live amd64 ISO only as a torrent; "
                "direct ISO download is unavailable and torrent acquisition is unsupported."
            )
        if direct is None:
            raise LibraryError("No stable live amd64 Kali ISO found in the official index.")
        version, filename, url = direct
        return version, filename, url, exact_link(html, self.metadata_url, "SHA256SUMS")

    def get_latest_release(self) -> Release:
        with self.connection() as client:
            version, filename, url, sums_url = self.parse(
                read_text(client, self.metadata_url, {"cdimage.kali.org"})
            )
            digest = checksum(read_text(client, sums_url, {"cdimage.kali.org"}), filename)
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
