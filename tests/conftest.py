import hashlib
import socket
from dataclasses import replace

import pytest

from ventoy_library.models import AcquisitionMethod, ManagedImage, Release, VerificationStatus


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Tests must mock all network activity")

    monkeypatch.setattr(socket.socket, "connect", fail)


@pytest.fixture
def root(tmp_path):
    return tmp_path.resolve()


@pytest.fixture
def release():
    return Release(
        "example",
        "Example",
        "1.0",
        "rescue",
        "x86_64",
        "example-1.iso",
        "https://example.invalid/image.iso",
        3,
        "sha256",
        hashlib.sha256(b"abc").hexdigest(),
    )


@pytest.fixture
def record(release):
    return ManagedImage(
        release.provider,
        release.display_name,
        release.version,
        release.filename,
        f"ISO/{release.category}/{release.provider}/{release.filename}",
        release.url,
        release.size,
        release.checksum_algorithm,
        release.checksum,
        "2026-01-01T00:00:00Z",
        VerificationStatus.VERIFIED,
        AcquisitionMethod.AUTOMATIC,
    )


@pytest.fixture
def provider(release):
    class Example:
        name = release.provider
        display_name = release.display_name
        category = release.category
        architecture = release.architecture

        def get_latest_release(self):
            return release

    return Example()


@pytest.fixture
def new_record(record):
    return replace(
        record,
        version="2.0",
        filename="example-2.iso",
        relative_path="ISO/rescue/example/example-2.iso",
    )


@pytest.fixture(autouse=True)
def no_hardware_inventory(monkeypatch):
    from ventoy_library.volumes import Inventory

    monkeypatch.setattr("ventoy_library.destinations.scan_volumes", Inventory)


@pytest.fixture(autouse=True)
def empty_bundled_release_snapshots(monkeypatch):
    """Keep ordinary CLI tests offline; catalog loading has focused tests."""
    from ventoy_library import cli
    from ventoy_library.release_catalog import CatalogDocument

    monkeypatch.setattr(cli, "load_bundled_catalog", lambda: CatalogDocument({}))
