from typing import Protocol

from ..models import Release


class Provider(Protocol):
    """Upstream adapters own stable selection, architecture, URLs, sizes and checksums."""

    name: str
    display_name: str
    category: str
    architecture: str

    def get_latest_release(self) -> Release:
        """Discover official stable metadata, or raise LibraryError with useful context."""
        ...
