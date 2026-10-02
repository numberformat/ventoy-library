"""Streaming transfer primitives. Callers must preflight the complete plan first."""

import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import httpx

from .atomic import atomic_json
from .errors import LibraryError, SafetyError
from .metadata import USER_AGENT
from .models import Release, http_url
from .safety import contained, open_regular

CHUNK_SIZE = 1024 * 1024


def http_client() -> httpx.Client:
    return httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(30, connect=10),
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
    )


class Downloader(Protocol):
    def fetch(
        self, release: Release, source: str, root: Path, part: Path, progress: Callable[[int], None]
    ) -> Path: ...


class HTTPDownloader:
    def __init__(
        self, client: httpx.Client, retries: int = 2, sleep: Callable[[float], None] = time.sleep
    ):
        self.client = client
        self.retries = retries
        self.sleep = sleep

    def size(self, url: str) -> int | None:
        try:
            response = self.client.head(http_url(url), headers={"Accept-Encoding": "identity"})
            response.raise_for_status()
            if response.headers.get("Content-Encoding", "identity") != "identity":
                return None
            value = int(response.headers["Content-Length"])
            return value if value >= 0 else None
        except (httpx.HTTPError, KeyError, ValueError):
            return None

    def fetch(
        self, release: Release, source: str, root: Path, part: Path, progress: Callable[[int], None]
    ) -> Path:
        http_url(source)
        if release.size is None:
            raise SafetyError("Download requires a known size after preflight.")
        part = contained(root, part.relative_to(root))
        marker = contained(root, str(part.relative_to(root)) + ".json")
        identity = {
            "url": source,
            "size": release.size,
            "checksum": release.checksum,
            "algorithm": release.checksum_algorithm,
            "version": release.version,
        }
        part.parent.mkdir(parents=True, exist_ok=True)
        if part.exists() or marker.exists():
            try:
                matches = json.loads(marker.read_text(encoding="utf-8")) == identity
            except (OSError, ValueError):
                matches = False
            if not matches:
                raise SafetyError("Unrecognized partial download; refusing to overwrite it.")
        else:
            atomic_json(marker, identity)
        for attempt in range(self.retries + 1):
            offset = part.stat().st_size if part.exists() else 0
            # A trusted checksum permits safe eventual validation of a resumed artifact.
            if not release.checksum or offset > release.size:
                offset = 0
            if offset == release.size and part.exists() and release.checksum:
                progress(offset)
                return part
            headers = {"Accept-Encoding": "identity"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            try:
                with self.client.stream("GET", source, headers=headers) as response:
                    response.raise_for_status()
                    if response.headers.get("Content-Encoding", "identity") != "identity":
                        raise LibraryError("Encoded HTTP response cannot be safely resumed.")
                    if response.status_code == 206:
                        match = re.fullmatch(
                            r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", "")
                        )
                        if (
                            not match
                            or int(match[1]) != offset
                            or int(match[3]) != release.size
                            or int(match[2]) != release.size - 1
                        ):
                            raise LibraryError(
                                "Invalid HTTP Content-Range; partial file preserved."
                            )
                    elif response.status_code == 200:
                        offset = 0  # Upstream ignored Range: restart, never append.
                    else:
                        raise LibraryError(
                            f"Unexpected HTTP download status: {response.status_code}"
                        )
                    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if offset else os.O_TRUNC)
                    with os.fdopen(open_regular(part, flags), "wb") as output:
                        progress(offset)
                        for chunk in response.iter_raw(CHUNK_SIZE):
                            if offset + len(chunk) > release.size:
                                raise LibraryError(
                                    "Response exceeds planned size; download stopped."
                                )
                            output.write(chunk)
                            offset += len(chunk)
                            progress(offset)
                        output.flush()
                        os.fsync(output.fileno())
                    if offset != release.size:
                        raise httpx.ReadError("Response ended before expected image size.")
                return part
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                transient = not isinstance(
                    exc, httpx.HTTPStatusError
                ) or exc.response.status_code in {408, 429, 500, 502, 503, 504}
                if attempt == self.retries or not transient:
                    raise LibraryError(
                        "Download failed; a recognized .part file may be resumed."
                    ) from exc
                self.sleep(min(2**attempt, 8))
        raise AssertionError("unreachable")


def import_local(
    source: Path, root: Path, part: Path, expected_size: int, progress: Callable[[int], None]
) -> Path:
    source = source.expanduser()
    if source.is_symlink() or not source.is_file():
        raise SafetyError("Local source must be a regular file.")
    part = contained(root, part.relative_to(root))
    part.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite a user's file or a recognized HTTP partial with a local copy.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    with os.fdopen(open_regular(source, os.O_RDONLY), "rb") as incoming:
        with os.fdopen(open_regular(part, flags), "wb") as outgoing:
            offset = 0
            try:
                while chunk := incoming.read(CHUNK_SIZE):
                    if offset + len(chunk) > expected_size:
                        raise LibraryError("Local source exceeds planned size.")
                    outgoing.write(chunk)
                    offset += len(chunk)
                    progress(offset)
                if offset != expected_size:
                    raise LibraryError("Local source changed after planning.")
                outgoing.flush()
                os.fsync(outgoing.fileno())
            except BaseException:
                # This function created the partial exclusively, so it owns this exact file.
                outgoing.close()
                part.unlink()
                raise
    return part
