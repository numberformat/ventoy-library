"""Load bundled candidate release snapshots and manual catalog notes."""

import os
import re
from dataclasses import dataclass
from datetime import date
from importlib.resources import as_file, files
from pathlib import Path

import yaml

from .catalog import BUILTIN_PROVIDER_NAMES, CATALOG
from .errors import LibraryError
from .models import Release, http_url
from .safety import open_regular

MAX_CATALOG_BYTES = 1024 * 1024
ENTRY_KEYS = {
    "status",
    "source_page",
    "discovery_url",
    "version",
    "architecture",
    "filename",
    "url",
    "notes",
}
UNSTABLE = re.compile(r"alpha|beta|nightly|daily|snapshot|(?:^|[-._])(?:rc|pre|dev)\d*", re.I)


class UniqueSafeLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise LibraryError("YAML aliases are not allowed in the release catalog.")
        return super().compose_node(parent, index)


def construct_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise LibraryError("Release catalog keys must be unique strings.")
        result[key] = loader.construct_object(value_node)
    return result


UniqueSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)


def optional_url(value, field: str) -> None:
    if value is not None:
        try:
            http_url(value)
        except LibraryError as exc:
            raise LibraryError(f"{field}: {exc}") from exc


def catalog_date(value) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise LibraryError("researched_at must be a quoted YYYY-MM-DD date or null.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise LibraryError("researched_at is not a valid date.") from exc


@dataclass(frozen=True)
class CatalogDocument:
    releases: dict[str, Release]
    researched_at: date | None = None
    versions: dict[str, str] | None = None
    manual_sources: dict[str, Release] | None = None


def load_catalog(path: Path) -> CatalogDocument:
    """Read a complete catalog; valid candidates provide snapshot releases."""
    try:
        if path.is_symlink() or not path.is_file():
            raise LibraryError(f"Release catalog is not a regular file: {path}")
        with os.fdopen(open_regular(path, os.O_RDONLY), "rb") as stream:
            payload = stream.read(MAX_CATALOG_BYTES + 1)
        if len(payload) > MAX_CATALOG_BYTES:
            raise LibraryError("Release catalog exceeds the 1 MiB limit.")
        data = yaml.load(payload.decode("utf-8-sig"), Loader=UniqueSafeLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise LibraryError(f"Could not read release catalog {path}: {exc}") from exc
    if not isinstance(data, dict) or set(data) != {"schema_version", "researched_at", "images"}:
        raise LibraryError("Release catalog requires schema_version, researched_at and images.")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise LibraryError("Unsupported release catalog schema version.")
    researched_at = catalog_date(data["researched_at"])
    entries = data["images"]
    expected = {entry.name for entry in CATALOG}
    if not isinstance(entries, dict) or set(entries) != expected:
        missing = expected - set(entries) if isinstance(entries, dict) else expected
        extra = set(entries) - expected if isinstance(entries, dict) else set()
        raise LibraryError(
            "Release catalog must contain every catalog ID exactly once. "
            f"Missing: {', '.join(sorted(missing)) or '-'}; "
            f"unknown: {', '.join(sorted(extra)) or '-'}."
        )
    releases = {}
    versions = {}
    manual_sources = {}
    for catalog_entry in CATALOG:
        name = catalog_entry.name
        item = entries[name]
        if not isinstance(item, dict) or set(item) - ENTRY_KEYS:
            raise LibraryError(f"Invalid fields for release catalog entry {name}.")
        status = item.get("status")
        allowed = (
            {"builtin"} if name in BUILTIN_PROVIDER_NAMES else {"manual", "candidate"}
        )
        if not isinstance(status, str) or status not in allowed:
            raise LibraryError(f"Invalid status for {name}: {status!r}.")
        if status == "builtin" and set(item) - {
            "status",
            "source_page",
            "discovery_url",
            "notes",
        }:
            raise LibraryError(f"Invalid builtin entry structure for {name}.")
        optional_url(item.get("source_page"), f"{name}.source_page")
        optional_url(item.get("discovery_url"), f"{name}.discovery_url")
        optional_url(item.get("url"), f"{name}.url")
        notes = item.get("notes")
        if not isinstance(notes, str) or not notes.strip():
            raise LibraryError(f"{name}.notes must explain the selected status.")
        if status == "builtin":
            continue
        architecture = item.get("architecture")
        if architecture is not None and architecture != catalog_entry.architecture:
            raise LibraryError(f"{name}.architecture differs from the catalog.")
        version = item.get("version")
        if version is not None:
            if not isinstance(version, str) or not version.strip():
                raise LibraryError(f"{name}.version must be a nonempty string or null.")
            versions[name] = version
        if status == "manual":
            filename = item.get("filename")
            url = item.get("url")
            if isinstance(version, str) and isinstance(filename, str) and url:
                manual_sources[name] = Release(
                    name,
                    catalog_entry.display_name,
                    version,
                    catalog_entry.category,
                    catalog_entry.architecture,
                    filename,
                    url,
                )
            continue
        filename = item.get("filename")
        if (
            not isinstance(version, str)
            or not isinstance(filename, str)
            or not version.strip()
            or not filename.strip()
            or UNSTABLE.search(version + " " + filename)
        ):
            raise LibraryError(f"{name} must name a stable release and artifact.")
        if not filename.lower().endswith((".iso", ".img")):
            raise LibraryError(f"{name} must name an uncompressed ISO or IMG artifact.")
        releases[name] = Release(
            name,
            catalog_entry.display_name,
            version,
            catalog_entry.category,
            catalog_entry.architecture,
            filename,
            item.get("url"),
        )
    return CatalogDocument(releases, researched_at, versions, manual_sources)


def load_bundled_catalog() -> CatalogDocument:
    """Load the YAML included in the installed ventoy_library package."""
    with as_file(files("ventoy_library").joinpath("releases.yaml")) as path:
        return load_catalog(path)
