"""The requested image catalog. Order is user-visible: append entries, never reorder IDs."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    display_name: str
    category: str
    architecture: str = "x86_64"


CATALOG = (
    CatalogEntry("arch", "Arch Linux", "desktop"),
    CatalogEntry("alpine", "Alpine Linux", "desktop"),
    CatalogEntry("fedora", "Fedora Workstation", "desktop"),
    CatalogEntry("debian", "Debian Live", "desktop"),
    CatalogEntry("linux-mint", "Linux Mint", "desktop"),
    CatalogEntry("knoppix", "Knoppix", "desktop"),
    CatalogEntry("tinycore", "Tiny Core Linux", "desktop"),
    CatalogEntry("systemrescue", "SystemRescue", "rescue"),
    CatalogEntry("gparted", "GParted Live", "rescue"),
    CatalogEntry("clonezilla", "Clonezilla Live", "rescue"),
    CatalogEntry("rescuezilla", "Rescuezilla", "rescue"),
    CatalogEntry("hirens", "Hiren's BootCD PE", "rescue"),
    CatalogEntry("memtest86plus", "Memtest86+", "rescue"),
    CatalogEntry("kali", "Kali Linux", "security"),
    CatalogEntry("parrot", "Parrot Security", "security"),
    CatalogEntry("tails", "Tails", "security"),
    CatalogEntry("opnsense", "OPNsense", "network"),
    CatalogEntry("openwrt", "OpenWrt x86-64", "network"),
    CatalogEntry("openmediavault", "OpenMediaVault", "server"),
    CatalogEntry("ubuntu-server", "Ubuntu Server LTS", "server"),
    CatalogEntry("freebsd", "FreeBSD", "other"),
    CatalogEntry("freedos", "FreeDOS", "other", "x86"),
    CatalogEntry("reactos", "ReactOS", "other", "x86"),
    CatalogEntry("ubuntu-desktop", "Ubuntu Desktop LTS", "desktop"),
)

BUILTIN_PROVIDER_NAMES = frozenset({"arch", "systemrescue", "ubuntu-server", "ubuntu-desktop"})
