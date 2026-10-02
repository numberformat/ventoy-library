"""Catalog-ordered registration with explicit automatic/manual acquisition status."""

from ..errors import LibraryError
from ..safety import component
from .base import Provider


class Registry:
    def __init__(self):
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        component(provider.name)
        component(provider.category)
        if provider.name in self._providers:
            raise LibraryError(f"Duplicate provider: {provider.name}")
        self._providers[provider.name] = provider

    def add_snapshots(self, snapshots: dict) -> None:
        """Replace catalog-managed manual adapters with usable candidate snapshots."""
        from ..catalog import CATALOG
        from .snapshot import SnapshotProvider

        entries = {entry.name: entry for entry in CATALOG}
        for name, release in snapshots.items():
            if name not in entries or name in self._providers and not self._providers[name].manual:
                raise LibraryError(f"Cannot apply a release snapshot to provider {name}.")
            self._providers[name] = SnapshotProvider(entries[name], release)

    def select(self, names: list[str] | None = None) -> list[Provider]:
        if not names:
            return list(self._providers.values())
        unknown = set(names) - self._providers.keys()
        if unknown:
            raise LibraryError(f"Unknown provider(s): {', '.join(sorted(unknown))}")
        return [self._providers[name] for name in dict.fromkeys(names)]


def default_registry(snapshots=None) -> Registry:
    from ..catalog import CATALOG
    from .arch import ArchProvider
    from .manual import ManualProvider
    from .snapshot import SnapshotProvider
    from .systemrescue import SystemRescueProvider
    from .ubuntu import UbuntuServerProvider
    from .ubuntu_desktop import UbuntuDesktopProvider

    automatic = {
        "arch": ArchProvider,
        "systemrescue": SystemRescueProvider,
        "ubuntu-server": UbuntuServerProvider,
        "ubuntu-desktop": UbuntuDesktopProvider,
    }
    registry = Registry()
    snapshots = snapshots or {}
    for entry in CATALOG:
        if entry.name in automatic:
            provider = automatic[entry.name]()
        elif entry.name in snapshots:
            provider = SnapshotProvider(entry, snapshots[entry.name])
        else:
            provider = ManualProvider(entry)
        registry.register(provider)
    return registry
