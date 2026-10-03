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

    def add_snapshots(self, snapshots: dict, researched_at=None, versions=None) -> None:
        """Replace catalog-managed manual adapters with usable candidate snapshots."""
        from ..catalog import CATALOG
        from .snapshot import SnapshotProvider

        entries = {entry.name: entry for entry in CATALOG}
        for name, provider in self._providers.items():
            provider.catalog_version = (versions or {}).get(name)
            provider.researched_at = researched_at
        for name, release in snapshots.items():
            if name not in entries or name in self._providers and not self._providers[name].manual:
                raise LibraryError(f"Cannot apply a release snapshot to provider {name}.")
            provider = SnapshotProvider(entries[name], release)
            provider.catalog_version = release.version
            provider.researched_at = researched_at
            self._providers[name] = provider

    def select(self, names: list[str] | None = None) -> list[Provider]:
        if not names:
            return list(self._providers.values())
        unknown = set(names) - self._providers.keys()
        if unknown:
            raise LibraryError(f"Unknown provider(s): {', '.join(sorted(unknown))}")
        return [self._providers[name] for name in dict.fromkeys(names)]


def default_registry(snapshots=None) -> Registry:
    from ..catalog import CATALOG
    from .alpine import AlpineProvider
    from .arch import ArchProvider
    from .clonezilla import ClonezillaProvider
    from .debian import DebianProvider
    from .freebsd import FreeBSDProvider
    from .gparted import GPartedProvider
    from .kali import KaliProvider
    from .manual import ManualProvider
    from .rescuezilla import RescuezillaProvider
    from .snapshot import SnapshotProvider
    from .systemrescue import SystemRescueProvider
    from .tails import TailsProvider
    from .ubuntu import UbuntuServerProvider
    from .ubuntu_desktop import UbuntuDesktopProvider

    automatic = {
        "arch": ArchProvider,
        "alpine": AlpineProvider,
        "debian": DebianProvider,
        "systemrescue": SystemRescueProvider,
        "gparted": GPartedProvider,
        "clonezilla": ClonezillaProvider,
        "rescuezilla": RescuezillaProvider,
        "kali": KaliProvider,
        "tails": TailsProvider,
        "ubuntu-server": UbuntuServerProvider,
        "freebsd": FreeBSDProvider,
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
