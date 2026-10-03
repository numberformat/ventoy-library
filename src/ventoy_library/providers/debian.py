"""Debian current amd64 netinst ISO."""

from ..downloader import HTTPDownloader
from ..models import Release
from .common import HTTPProvider, checksum, exact_link, index_artifact, read_text


class DebianProvider(HTTPProvider):
    name = "debian"
    display_name = "Debian Live"
    category = "desktop"
    architecture = "x86_64"
    metadata_url = "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/"
    pattern = r"debian-(\d+\.\d+\.\d+)-amd64-netinst\.iso"

    def parse(self, html: str) -> tuple[str, str, str, str]:
        version, filename, url = index_artifact(html, self.metadata_url, self.pattern)
        return version, filename, url, exact_link(html, self.metadata_url, "SHA256SUMS")

    def get_latest_release(self) -> Release:
        with self.connection() as client:
            version, filename, url, sums_url = self.parse(
                read_text(client, self.metadata_url, {"cdimage.debian.org"})
            )
            digest = checksum(read_text(client, sums_url, {"cdimage.debian.org"}), filename)
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
