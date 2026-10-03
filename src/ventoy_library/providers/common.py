"""Small, bounded metadata readers shared by upstream adapters."""

import re
from contextlib import nullcontext
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
from packaging.version import Version

from ..downloader import http_client
from ..errors import LibraryError


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def links(html: str, base: str) -> list[str]:
    parser = Links()
    parser.feed(html)
    return list(dict.fromkeys(urljoin(base, h) for h in parser.hrefs))


def read_text(client: httpx.Client, url: str, allowed_hosts: set[str] | None = None) -> str:
    # A changed link must not accidentally load an ISO into memory during discovery.
    with client.stream("GET", url) as response:
        response.raise_for_status()
        if allowed_hosts is not None and (
            response.url.scheme != "https" or response.url.host not in allowed_hosts
        ):
            raise LibraryError("Upstream metadata redirected to an unexpected host.")
        content = bytearray()
        for chunk in response.iter_bytes(64 * 1024):
            content.extend(chunk)
            if len(content) > 2 * 1024**2:
                raise LibraryError("Upstream metadata exceeds the 2 MiB safety limit.")
        return content.decode("utf-8")


def checksum(text: str, filename: str) -> str:
    import re

    for line in text.splitlines():
        match = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?(.+)", line.strip())
        if match and match[2] == filename:
            return match[1].lower()
    raise LibraryError(f"No authoritative SHA256 checksum found for {filename}.")


def index_artifact(html: str, index_url: str, pattern: str) -> tuple[str, str, str]:
    """Select the newest matching file linked directly by a trusted directory index."""
    base = urlsplit(index_url)
    candidates = []
    for url in links(html, index_url):
        parsed = urlsplit(url)
        if (
            (parsed.scheme, parsed.netloc, parsed.path.rpartition("/")[0] + "/")
            != ("https", base.netloc, base.path)
            or parsed.query
            or parsed.fragment
        ):
            continue
        filename = parsed.path.rpartition("/")[2]
        match = re.fullmatch(pattern, filename)
        if match:
            candidates.append((Version(match[1]), match[1], filename, url))
    if not candidates:
        raise LibraryError(f"No stable matching ISO found in {index_url}.")
    _, version, filename, url = max(candidates)
    return version, filename, url


def exact_link(html: str, index_url: str, filename: str) -> str:
    expected = index_url + filename
    if expected not in links(html, index_url):
        raise LibraryError(f"Official index does not link {filename}.")
    return expected


class HTTPProvider:
    manual = False

    def __init__(self, client: httpx.Client | None = None):
        self.client = client

    def connection(self):
        return nullcontext(self.client) if self.client is not None else http_client()
