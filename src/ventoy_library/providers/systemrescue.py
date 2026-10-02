import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from packaging.version import Version

from ..downloader import HTTPDownloader
from ..errors import LibraryError
from ..models import Release
from .common import HTTPProvider, checksum, links, read_text


class SystemRescueProvider(HTTPProvider):
    name = "systemrescue"
    display_name = "SystemRescue"
    category = "rescue"
    architecture = "x86_64"
    metadata_url = "https://www.system-rescue.org/Download/"

    def get_latest_release(self) -> Release:
        with self.connection() as client:
            version, filename, url, sums_url = self.parse(read_text(client, self.metadata_url))
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

    def parse(self, html: str) -> tuple[str, str, str, str]:
        urls = links(html, self.metadata_url)
        candidates = []
        for url in urls:
            parsed = urlsplit(url)
            filename = PurePosixPath(parsed.path).name
            match = re.fullmatch(r"systemrescue-(\d+\.\d+)-amd64\.iso", filename)
            if (
                parsed.scheme != "https"
                or parsed.hostname != "fastly-cdn.system-rescue.org"
                or not match
            ):
                continue
            version = match[1]
            sums = [
                u
                for u in urls
                if urlsplit(u).scheme == "https"
                and urlsplit(u).hostname == "www.system-rescue.org"
                and PurePosixPath(urlsplit(u).path).name == filename + ".sha256"
            ]
            if len(sums) != 1:
                raise LibraryError("SystemRescue checksum link is missing or ambiguous.")
            candidates.append((version, filename, url, sums[0]))
        if not candidates:
            raise LibraryError("No stable amd64 SystemRescue ISO found on the official page.")
        return max(candidates, key=lambda item: Version(item[0]))
