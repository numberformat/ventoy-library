"""Stable GitHub release checks and explicit pipx-managed application replacement."""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from packaging.version import InvalidVersion, Version

from .errors import LibraryError
from .metadata import GIT_SOURCE, PROJECT_NAME, REPOSITORY, REPOSITORY_URL, __version__


@dataclass(frozen=True)
class AppRelease:
    tag: str
    version: Version
    wheel_name: str | None = None
    wheel_url: str | None = None
    wheel_size: int | None = None
    wheel_digest: str | None = None


def installed_version() -> Version:
    try:
        return Version(metadata.version(PROJECT_NAME))
    except metadata.PackageNotFoundError:
        return Version(__version__)


def stable_tag(tag: str) -> AppRelease | None:
    if not isinstance(tag, str) or not re.fullmatch(
        r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag
    ):
        return None
    try:
        version = Version(tag)
    except InvalidVersion:
        return None
    return None if version.is_prerelease or version.is_devrelease else AppRelease(tag, version)


def latest_release(client: httpx.Client) -> AppRelease | None:
    def pages(endpoint):
        rows = []
        for page in range(1, 11):
            response = client.get(
                f"https://api.github.com/repos/{REPOSITORY}/{endpoint}",
                params={"per_page": 100, "page": page},
                headers={"Accept": "application/vnd.github+json"},
            )
            if response.status_code in {403, 429}:
                raise LibraryError("GitHub API access denied or rate limited; try again later.")
            if response.status_code == 404:
                raise LibraryError("GitHub repository unavailable or not public yet.")
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
                raise LibraryError("Malformed GitHub response.")
            rows.extend(data)
            if len(data) < 100:
                return rows
        raise LibraryError("GitHub pagination limit reached; cannot establish latest release.")

    try:
        releases = pages("releases")
        candidates = []
        for row in releases:
            if (
                not isinstance(row.get("tag_name"), str)
                or type(row.get("draft")) is not bool
                or type(row.get("prerelease")) is not bool
            ):
                raise LibraryError("Malformed GitHub release metadata.")
            if not row["draft"] and not row["prerelease"]:
                if candidate := stable_tag(row["tag_name"]):
                    assets = row.get("assets", [])
                    if not isinstance(assets, list):
                        raise LibraryError("Malformed GitHub release assets.")
                    wheels = [
                        asset
                        for asset in assets
                        if isinstance(asset, dict)
                        and isinstance(asset.get("name"), str)
                        and asset["name"].endswith(".whl")
                    ]
                    if len(wheels) == 1:
                        asset = wheels[0]
                        candidates.append(
                            AppRelease(
                                candidate.tag,
                                candidate.version,
                                asset.get("name"),
                                asset.get("browser_download_url"),
                                asset.get("size"),
                                asset.get("digest"),
                            )
                        )
                    else:
                        candidates.append(candidate)
        # Tags are a fallback only when the repository has no published releases.
        if not releases:
            for row in pages("tags"):
                if not isinstance(row.get("name"), str):
                    raise LibraryError("Malformed GitHub tag metadata.")
                if candidate := stable_tag(row["name"]):
                    candidates.append(candidate)
        return max(candidates, key=lambda r: r.version, default=None)
    except (httpx.HTTPError, ValueError) as exc:
        raise LibraryError(
            "Cannot check application updates: network/API response failure."
        ) from exc


def installation_kind(prefix: Path | None = None, direct_url: dict | None = None) -> str:
    prefix = prefix or Path(sys.prefix)
    if direct_url is None:
        try:
            dist = metadata.distribution(PROJECT_NAME)
            direct_url = json.loads(dist.read_text("direct_url.json") or "{}")
        except metadata.PackageNotFoundError:
            return "development"
        except (ValueError, TypeError):
            return "unsupported"
    if not isinstance(direct_url, dict):
        return "unsupported"
    dir_info = direct_url.get("dir_info", {})
    url = direct_url.get("url", "")
    if not isinstance(dir_info, dict) or not isinstance(url, str):
        return "unsupported"
    if dir_info.get("editable"):
        return "development"
    try:
        data = json.loads((prefix / "pipx_metadata.json").read_text(encoding="utf-8"))
        package = data["main_package"]
        if not isinstance(package, dict):
            return "unsupported"
        source = package.get("package_or_url")
        if not isinstance(source, str):
            return "unsupported"
        source_is_git = source == GIT_SOURCE or source.startswith(GIT_SOURCE + "@")
        source_name = Path(unquote(urlparse(source).path)).name
        wheel_pattern = r"ventoy_library-\d+\.\d+\.\d+-py3-none-any\.whl"
        source_is_wheel = re.fullmatch(wheel_pattern, source_name) is not None
        direct_name = Path(unquote(urlparse(url).path)).name
        if url.startswith("file:") and (not source_is_wheel or direct_name != source_name):
            return "unsupported"
        if (
            package["package"] == PROJECT_NAME
            and not package.get("suffix")
            and not package.get("pinned")
            and not package.get("lock_file")
            and "--editable" not in package.get("pip_args", [])
            and (source_is_git or source_is_wheel)
        ):
            return "pipx"
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return "unsupported"


def update_executable(release: AppRelease) -> str:
    stable = stable_tag(release.tag)
    if stable is None or stable.version != release.version:
        raise LibraryError("Invalid stable application release.")
    expected_name = f"ventoy_library-{release.version}-py3-none-any.whl"
    expected_url = f"{REPOSITORY_URL}/releases/download/{release.tag}/{expected_name}"
    if release.wheel_name != expected_name or release.wheel_url != expected_url:
        raise LibraryError("The latest GitHub Release has no matching application wheel.")
    if type(release.wheel_size) is not int or not 0 < release.wheel_size <= 100 * 1024 * 1024:
        raise LibraryError("The GitHub Release wheel has an invalid size.")
    if not isinstance(release.wheel_digest, str) or not re.fullmatch(
        r"sha256:[0-9a-fA-F]{64}", release.wheel_digest
    ):
        raise LibraryError("The GitHub Release wheel has no valid SHA-256 digest.")
    kind = installation_kind()
    if kind == "development":
        raise LibraryError(
            "This appears to be an editable/development installation. Automatic "
            "application updates are disabled. Update this checkout using Git instead."
        )
    if kind != "pipx":
        raise LibraryError("Automatic --update requires an unsuffixed, unpinned pipx installation.")
    executable = shutil.which("pipx")
    if not executable:
        raise LibraryError("pipx is unavailable on PATH; update pipx and retry.")
    # Prove the pipx on PATH manages this interpreter's environment before mutation.
    try:
        result = subprocess.run(
            [executable, "environment", "--value", "PIPX_LOCAL_VENVS"],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LibraryError("Cannot identify pipx's environment directory.") from exc
    expected = Path(result.stdout.strip()) / PROJECT_NAME
    if expected.resolve() != Path(sys.prefix).resolve():
        raise LibraryError("pipx on PATH does not manage the running application environment.")
    return executable


def download_release_wheel(client: httpx.Client, release: AppRelease, directory: Path) -> Path:
    """Stream the published wheel and verify its GitHub asset digest before pipx runs."""
    wheel = directory / release.wheel_name
    digest = hashlib.sha256()
    received = 0
    try:
        with client.stream("GET", release.wheel_url) as response:
            response.raise_for_status()
            with wheel.open("wb") as output:
                for chunk in response.iter_bytes():
                    received += len(chunk)
                    if received > release.wheel_size:
                        raise LibraryError("Release wheel exceeds its published size.")
                    digest.update(chunk)
                    output.write(chunk)
    except httpx.HTTPError as exc:
        raise LibraryError("Could not download the application release wheel.") from exc
    except OSError as exc:
        raise LibraryError("Could not save the application release wheel.") from exc
    if (
        received != release.wheel_size
        or digest.hexdigest().lower() != release.wheel_digest[7:].lower()
    ):
        raise LibraryError("Release wheel size or SHA-256 digest does not match GitHub metadata.")
    return wheel


def update_command(executable: str, wheel: Path) -> list[str]:
    return [executable, "install", "--force", str(wheel)]


def run_update(command: list[str]) -> int:
    # No in-process file edits or Git operations. The CLI exits immediately on return.
    try:
        return subprocess.run(command, check=False).returncode
    except OSError as exc:
        raise LibraryError("Could not start pipx.") from exc
