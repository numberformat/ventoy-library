"""Metadata-only checks of advertised image download URLs."""

from dataclasses import dataclass

import httpx

from .models import Release, http_url


@dataclass(frozen=True)
class Availability:
    available: bool
    detail: str
    size: int | None = None


def check_download(client: httpx.Client, release: Release) -> Availability:
    """Use HEAD only; never request or read an image body."""
    if release.url is None:
        return Availability(False, "no direct download URL")
    with client.stream(
        "HEAD", http_url(release.url), headers={"Accept-Encoding": "identity"}
    ) as response:
        if response.status_code in {405, 501}:
            return Availability(False, f"HEAD unsupported (HTTP {response.status_code})")
        if not 200 <= response.status_code < 300:
            return Availability(False, f"HTTP {response.status_code}")
        if response.headers.get("Content-Type", "").lower().startswith("text/html"):
            return Availability(False, "server returned an HTML page")
        raw_size = response.headers.get("Content-Length")
        size = int(raw_size) if raw_size and raw_size.isdecimal() else None
        if size == 0:
            return Availability(False, "server reports an empty file", size)
        if release.size is not None and size is not None and release.size != size:
            return Availability(False, "size differs from release metadata", size)
        return Availability(True, "HEAD succeeded", size or release.size)
