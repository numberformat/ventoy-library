from importlib.resources import files
from pathlib import Path

import pytest
import yaml

from ventoy_library.catalog import BUILTIN_PROVIDER_NAMES, CATALOG
from ventoy_library.errors import LibraryError
from ventoy_library.planner import build_plan
from ventoy_library.providers import default_registry
from ventoy_library.release_catalog import load_bundled_catalog, load_catalog

EXPECTED = (
    "arch alpine fedora debian linux-mint knoppix tinycore systemrescue gparted "
    "clonezilla rescuezilla hirens memtest86plus kali parrot tails opnsense openwrt "
    "openmediavault ubuntu-server freebsd freedos reactos ubuntu-desktop"
).split()
REMOVED = {"puppy", "ubcd", "pfsense", "truenas", "haiku"}
REMOVED_FIELDS = {"size_bytes", "checksum_algorithm", "checksum", "checksum_url", "reviewed_at"}


def manifest():
    images = {}
    for entry in CATALOG:
        if entry.name in BUILTIN_PROVIDER_NAMES:
            images[entry.name] = {
                "status": "builtin", "source_page": None,
                "discovery_url": None, "notes": "Built-in discovery.",
            }
        else:
            images[entry.name] = {
                "status": "manual", "source_page": None,
                "discovery_url": None, "version": None,
                "architecture": entry.architecture, "filename": None,
                "url": None, "notes": "Research pending.",
            }
    return {"schema_version": 1, "researched_at": None, "images": images}


def candidate():
    return {
        "status": "candidate",
        "source_page": "https://example.invalid/download",
        "discovery_url": "https://example.invalid/releases",
        "version": "3.1.0",
        "architecture": "x86_64",
        "filename": "alpine-3.1.0-x86_64.iso",
        "url": "https://example.invalid/alpine.iso",
        "notes": "Synthetic artifact for tests.",
    }


def write(path: Path, data) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def test_bundled_catalog_loads_from_package_and_has_expected_ids():
    document = load_bundled_catalog()
    bundled = yaml.safe_load(files("ventoy_library").joinpath("releases.yaml").read_text())
    assert list(bundled["images"]) == EXPECTED
    assert set(document.releases) <= set(EXPECTED)
    assert len(EXPECTED) == 24


def test_removed_distributions_and_fields_absent_from_bundled_catalog():
    text = files("ventoy_library").joinpath("releases.yaml").read_text()
    raw = yaml.safe_load(text)
    assert not (REMOVED & set(raw["images"]))
    assert list(raw["images"]) == EXPECTED
    for entry in raw["images"].values():
        assert not (REMOVED_FIELDS & set(entry))


def test_builtin_entries_load_without_release_artifact_fields(tmp_path):
    document = load_catalog(write(tmp_path / "releases.yaml", manifest()))
    assert set(BUILTIN_PROVIDER_NAMES).isdisjoint(document.releases)
    providers = default_registry(document.releases).select(
        ["arch", "systemrescue", "ubuntu-server", "ubuntu-desktop"]
    )
    assert len(providers) == 4
    assert all(not provider.manual for provider in providers)


def test_candidate_is_usable_without_size_checksum_or_review_metadata(tmp_path):
    data = manifest()
    data["images"]["alpine"] = candidate()
    release = load_catalog(write(tmp_path / "releases.yaml", data)).releases["alpine"]
    assert release.version == "3.1.0"
    assert release.filename == "alpine-3.1.0-x86_64.iso"
    assert release.size is None and release.checksum is None
    provider = default_registry({"alpine": release}).select(["alpine"])[0]
    assert provider.get_latest_release() == release
    plan = build_plan([provider], tmp_path, [])
    assert plan.items[0].action.value == "DOWNLOAD"


def test_manual_entry_accepts_null_release_fields(tmp_path):
    data = manifest()
    data["images"]["alpine"].update({"version": None, "filename": None, "url": None})
    assert "alpine" not in load_catalog(write(tmp_path / "releases.yaml", data)).releases


def test_removed_metadata_fields_are_not_accepted_as_schema(tmp_path):
    for field in REMOVED_FIELDS:
        data = manifest()
        data["images"]["alpine"][field] = None
        with pytest.raises(LibraryError, match="Invalid fields"):
            load_catalog(write(tmp_path / "releases.yaml", data))


def test_catalog_structure_and_useful_validation_remain(tmp_path):
    data = manifest()
    data["images"]["alpine"] = candidate()
    data["images"]["alpine"]["url"] = "file:///tmp/alpine.iso"
    with pytest.raises(LibraryError, match=r"HTTP\(S\)"):
        load_catalog(write(tmp_path / "releases.yaml", data))
    data = manifest()
    data["images"]["arch"]["status"] = "candidate"
    with pytest.raises(LibraryError, match="Invalid status"):
        load_catalog(write(tmp_path / "releases.yaml", data))
    data = manifest()
    data["images"]["alpine"] = candidate()
    data["images"]["alpine"]["status"] = "ready"
    with pytest.raises(LibraryError, match="Invalid status"):
        load_catalog(write(tmp_path / "releases.yaml", data))


def test_registry_retains_builtin_providers():
    registry = default_registry()
    assert [p.name for p in registry.select(
        ["arch", "systemrescue", "ubuntu-server", "ubuntu-desktop"]
    )] == ["arch", "systemrescue", "ubuntu-server", "ubuntu-desktop"]
