"""Catalog-only acquisition; no upstream release discovery is claimed."""

from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from ..catalog import CatalogEntry
from ..errors import LibraryError
from ..models import Release, http_url
from ..safety import component


class ManualRequired(LibraryError):
    pass


class ManualProvider:
    manual = True

    def __init__(self, entry: CatalogEntry):
        self.name = entry.name
        self.display_name = entry.display_name
        self.category = entry.category
        self.architecture = entry.architecture

    def get_latest_release(self) -> Release:
        raise ManualRequired(
            "Automatic discovery is not implemented. Provide an official "
            "bootable image file or direct URL, or skip this image."
        )

    def release_from_source(self, source: str) -> Release:
        if source.startswith(("https://", "http://")):
            url = http_url(source)
            filename = unquote(PurePosixPath(urlsplit(url).path).name)
        else:
            url = None
            filename = Path(source).expanduser().name
        component(filename)
        return Release(
            self.name,
            self.display_name,
            "user-supplied",
            self.category,
            self.architecture,
            filename,
            url,
        )
