import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from packaging.version import Version

from ..downloader import HTTPDownloader
from ..errors import LibraryError
from ..models import Release
from .common import HTTPProvider, checksum, links, read_text


class UbuntuServerProvider(HTTPProvider):
    name = "ubuntu-server"
    display_name = "Ubuntu Server LTS"
    category = "server"
    architecture = "x86_64"
    artifact = "live-server"
    metadata_url = "https://changelogs.ubuntu.com/meta-release-lts"
    index_url = "https://releases.ubuntu.com/"

    @staticmethod
    def latest_lts(text: str) -> str:
        candidates = []
        for block in re.split(r"\n\s*\n", text.strip()):
            fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
            version = fields.get("Version", "")
            if fields.get("Supported") == "1" and re.fullmatch(r"\d+\.\d+(?:\.\d+)? LTS", version):
                candidates.append(version.removesuffix(" LTS"))
        if not candidates:
            raise LibraryError("No supported stable Ubuntu LTS release found.")
        return max(candidates, key=Version)

    def get_latest_release(self) -> Release:
        with self.connection() as client:
            lts = self.latest_lts(read_text(client, self.metadata_url))
            # Resolve a version directory actually advertised by the official index.
            index = links(read_text(client, self.index_url), self.index_url)
            major = ".".join(lts.split(".")[:2])
            directory = next(
                (
                    u
                    for u in index
                    if urlsplit(u).hostname == "releases.ubuntu.com"
                    and urlsplit(u).scheme == "https"
                    and urlsplit(u).path == f"/{major}/"
                ),
                None,
            )
            if directory is None:
                raise LibraryError(
                    "Ubuntu LTS release directory is missing from the official index."
                )
            page_links = links(read_text(client, directory), directory)
            candidates = []
            for url in page_links:
                filename = PurePosixPath(urlsplit(url).path).name
                match = re.fullmatch(
                    rf"ubuntu-(\d+\.\d+(?:\.\d+)?)-{self.artifact}-amd64\.iso", filename
                )
                if (
                    match
                    and ".".join(match[1].split(".")[:2]) == major
                    and url.startswith(directory)
                ):
                    candidates.append((match[1], filename, url))
            if not candidates:
                raise LibraryError(f"No stable amd64 {self.display_name} ISO found.")
            version, filename, url = max(candidates, key=lambda c: Version(c[0]))
            sums_url = next((u for u in page_links if u == directory + "SHA256SUMS"), None)
            if sums_url is None:
                raise LibraryError("Ubuntu SHA256 manifest link is missing.")
            digest = checksum(read_text(client, sums_url), filename)
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
