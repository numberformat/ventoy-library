"""Small, bounded metadata readers shared by upstream adapters."""

from contextlib import nullcontext
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

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


def read_text(client: httpx.Client, url: str) -> str:
    # A changed link must not accidentally load an ISO into memory during discovery.
    with client.stream("GET", url) as response:
        response.raise_for_status()
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


class HTTPProvider:
    manual = False

    def __init__(self, client: httpx.Client | None = None):
        self.client = client

    def connection(self):
        return nullcontext(self.client) if self.client is not None else http_client()
