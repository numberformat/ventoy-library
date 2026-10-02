"""A catalog candidate release snapshot from the optional YAML catalog."""

from ..catalog import CatalogEntry
from ..models import Release


class SnapshotProvider:
    manual = False
    snapshot = True

    def __init__(self, entry: CatalogEntry, release: Release):
        self.name = entry.name
        self.display_name = entry.display_name
        self.category = entry.category
        self.architecture = entry.architecture
        self.release = release

    def get_latest_release(self) -> Release:
        """Return the catalog snapshot; this does not discover a newer release."""
        return self.release
