from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from .errors import LibraryError
from .safety import component


class Action(StrEnum):
    CURRENT = "CURRENT"
    RELOCATE = "RELOCATE"
    ADOPT = "ADOPT"
    DOWNLOAD = "DOWNLOAD"
    UPDATE = "UPDATE"
    MANUAL = "MANUAL"
    SKIP = "SKIP"
    ERROR = "ERROR"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"


class AcquisitionMethod(StrEnum):
    AUTOMATIC = "automatic"
    LOCAL_FILE = "local-file"
    ALTERNATE_URL = "alternate-url"
    EXISTING_FILE = "existing-file"


def http_url(url: str) -> str:
    if not isinstance(url, str):
        raise LibraryError("Expected an HTTP(S) URL string.")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise LibraryError("Expected an HTTP(S) URL without embedded credentials.")
    return url


@dataclass(frozen=True)
class Release:
    provider: str
    display_name: str
    version: str
    category: str
    architecture: str
    filename: str
    url: str | None
    size: int | None = None
    checksum_algorithm: str | None = None
    checksum: str | None = None

    def __post_init__(self):
        for value in (self.provider, self.category, self.filename):
            component(value)
        if any(
            not isinstance(v, str) or not v.strip()
            for v in (self.version, self.architecture, self.display_name)
        ):
            raise LibraryError("Release identity must not be empty.")
        if self.url is not None:
            http_url(self.url)
        if self.size is not None and (type(self.size) is not int or self.size < 0):
            raise LibraryError("Image size must be a nonnegative integer or unknown.")
        if (self.checksum is None) != (self.checksum_algorithm is None):
            raise LibraryError("Checksum and algorithm must be supplied together.")
        if self.checksum is not None:
            import re

            lengths = {"sha256": 64, "sha512": 128}
            length = lengths.get(self.checksum_algorithm)
            if (
                length is None
                or not isinstance(self.checksum, str)
                or not re.fullmatch(rf"[0-9a-fA-F]{{{length}}}", self.checksum)
            ):
                raise LibraryError("Invalid checksum or unsupported algorithm.")


@dataclass(frozen=True)
class ManagedImage:
    provider: str
    display_name: str
    version: str
    filename: str
    relative_path: str
    source_url: str | None
    expected_size: int | None
    checksum_algorithm: str | None
    checksum: str | None
    download_timestamp: str
    verification_status: VerificationStatus
    acquisition_method: AcquisitionMethod


@dataclass(frozen=True)
class PlannedDownload:
    provider: str
    release: Release | None
    destination: Path | None
    action: Action
    installed: ManagedImage | None = None
    source: str | None = None
    acquisition_method: AcquisitionMethod = AcquisitionMethod.AUTOMATIC
    reason: str = ""


@dataclass(frozen=True)
class Plan:
    items: tuple[PlannedDownload, ...]

    @property
    def downloads(self) -> tuple[PlannedDownload, ...]:
        return tuple(i for i in self.items if i.action in {Action.DOWNLOAD, Action.UPDATE})

    @property
    def known_bytes(self) -> int:
        return sum(i.release.size or 0 for i in self.downloads)

    @property
    def unknown_sizes(self) -> int:
        return sum(i.release.size is None for i in self.downloads)

    @property
    def total_bytes(self) -> int | None:
        return None if self.unknown_sizes else self.known_bytes
