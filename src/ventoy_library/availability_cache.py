"""Short-lived, per-user cache of metadata-only download checks."""

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from .atomic import atomic_json
from .availability import check_download
from .downloader import http_client
from .errors import LibraryError
from .release_catalog import CatalogDocument

CACHE_DAYS = 3
MAX_CACHE_BYTES = 1024 * 1024


def cache_path() -> Path:
    """Use the user's profile directory on Unix, macOS and Windows."""
    return Path.home() / ".noami.us" / "ventoy-library" / "availability.json"


def _signature(provider, document: CatalogDocument) -> str:
    release = document.releases.get(provider.name) or (document.manual_sources or {}).get(
        provider.name
    )
    if release is None:
        return "builtin" if not provider.manual else "manual-without-url"
    return "\0".join((release.version, release.filename, release.url or ""))


def _load(path: Path) -> dict:
    try:
        if path.is_symlink() or path.stat().st_size > MAX_CACHE_BYTES:
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") == 1 and isinstance(data.get("entries"), dict):
            return data["entries"]
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {}


def _fresh(entry: object, signature: str, now: datetime) -> bool:
    if not isinstance(entry, dict) or type(entry.get("available")) is not bool:
        return False
    if entry.get("signature") != signature:
        return False
    try:
        checked = datetime.fromisoformat(entry["checked_at"])
        return checked.tzinfo is not None and checked <= now < checked + timedelta(days=CACHE_DAYS)
    except (KeyError, TypeError, ValueError):
        return False


def _save(path: Path, entries: dict) -> None:
    base = path.parent.parent
    if base.is_symlink() or path.parent.is_symlink() or path.is_symlink():
        raise OSError("Availability cache path contains a symbolic link.")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "nt":
        # A leading dot is not a hidden-file attribute on Windows.
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.GetFileAttributesW.restype = ctypes.c_uint32
        attributes = kernel32.GetFileAttributesW(str(base))
        if attributes == 0xFFFFFFFF or not kernel32.SetFileAttributesW(
            str(base), attributes | 0x2
        ):
            raise OSError("Could not hide the availability cache directory.")
    atomic_json(path, {"schema_version": 1, "entries": entries})


def available_names(
    providers: list,
    document: CatalogDocument,
    *,
    refresh: bool = False,
    path: Path | None = None,
) -> set[str]:
    """Return only sources whose HEAD check succeeded within the last three days."""
    path = path or cache_path()
    entries = _load(path)
    now = datetime.now(UTC)
    pending = [
        provider
        for provider in providers
        if refresh or not _fresh(entries.get(provider.name), _signature(provider, document), now)
    ]
    if pending:
        print(
            f"Checking {len(pending)} image links (HEAD only); "
            f"results are cached for {CACHE_DAYS} days..."
        )
        with http_client() as client:
            for provider in pending:
                available = False
                version = None
                try:
                    if provider.manual:
                        release = (document.manual_sources or {}).get(provider.name)
                    else:
                        release = provider.get_latest_release()
                    if release is not None:
                        if (
                            release.provider != provider.name
                            or release.category != provider.category
                            or release.architecture != provider.architecture
                        ):
                            raise LibraryError("Provider returned mismatched release identity.")
                        available = check_download(client, release).available
                        if available:
                            version = release.version
                except (LibraryError, httpx.HTTPError, OSError, ValueError) as exc:
                    logging.debug("Availability check failed for %s: %s", provider.name, exc)
                entries[provider.name] = {
                    "checked_at": now.isoformat(),
                    "signature": _signature(provider, document),
                    "available": available,
                    "version": version,
                }
        try:
            _save(path, entries)
        except OSError as exc:
            logging.warning("Could not save availability cache: %s", exc)
    visible = set()
    for provider in providers:
        entry = entries.get(provider.name, {})
        if entry.get("available") is True:
            visible.add(provider.name)
            if isinstance(entry.get("version"), str):
                provider.catalog_version = entry["version"]
    return visible
