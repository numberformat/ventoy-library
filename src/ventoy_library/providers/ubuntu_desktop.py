"""Ubuntu Desktop uses the same official LTS metadata and manifest as Server."""

from .ubuntu import UbuntuServerProvider


class UbuntuDesktopProvider(UbuntuServerProvider):
    name = "ubuntu-desktop"
    display_name = "Ubuntu Desktop LTS"
    category = "desktop"
    artifact = "desktop"
