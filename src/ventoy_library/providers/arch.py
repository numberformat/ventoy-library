import json
import re
from urllib.parse import urljoin, urlsplit

from ..errors import LibraryError
from ..models import Release
from .common import HTTPProvider, read_text


class ArchProvider(HTTPProvider):
    name = "arch"
    display_name = "Arch Linux"
    category = "desktop"
    architecture = "x86_64"
    metadata_url = "https://archlinux.org/releng/releases/json/"
    mirror = "https://fastly.mirror.pkgbuild.com"

    def get_latest_release(self) -> Release:
        with self.connection() as client:
            return self.parse(json.loads(read_text(client, self.metadata_url)))

    def parse(self, data: dict) -> Release:
        try:
            candidates = []
            for row in data["releases"]:
                version = row["version"]
                if row["available"] is not True or not re.fullmatch(
                    r"\d{4}\.\d{2}\.\d{2}", version
                ):
                    continue
                filename = row["torrent"]["file_name"]
                if filename != f"archlinux-{version}-x86_64.iso":
                    continue
                path = row["iso_url"]
                if path != f"/iso/{version}/{filename}":
                    raise LibraryError("Unexpected Arch release URL path.")
                url = urljoin(self.mirror, path)
                if urlsplit(url).netloc != urlsplit(self.mirror).netloc:
                    raise LibraryError("Unexpected Arch mirror host.")
                candidates.append(
                    Release(
                        self.name,
                        self.display_name,
                        version,
                        self.category,
                        self.architecture,
                        filename,
                        url,
                        row["torrent"]["file_length"],
                        "sha256",
                        row["sha256_sum"],
                    )
                )
            if not candidates:
                raise LibraryError("No available stable x86-64 Arch Linux ISO found.")
            return max(candidates, key=lambda r: r.version)
        except (KeyError, TypeError, AttributeError) as exc:
            raise LibraryError("Malformed Arch Linux release metadata.") from exc
