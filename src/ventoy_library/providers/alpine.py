"""Alpine Standard ISO from the official latest-stable directory."""

from ..downloader import HTTPDownloader
from ..models import Release
from .common import HTTPProvider, checksum, exact_link, index_artifact, read_text


class AlpineProvider(HTTPProvider):
    name = "alpine"
    display_name = "Alpine Linux"
    category = "desktop"
    architecture = "x86_64"
    metadata_url = "https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/"
    pattern = r"alpine-standard-(\d+\.\d+\.\d+)-x86_64\.iso"

    def parse(self, html: str) -> tuple[str, str, str, str]:
        version, filename, url = index_artifact(html, self.metadata_url, self.pattern)
        return version, filename, url, exact_link(html, self.metadata_url, filename + ".sha256")

    def get_latest_release(self) -> Release:
        with self.connection() as client:
            version, filename, url, sums_url = self.parse(
                read_text(client, self.metadata_url, {"dl-cdn.alpinelinux.org"})
            )
            digest = checksum(read_text(client, sums_url, {"dl-cdn.alpinelinux.org"}), filename)
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
