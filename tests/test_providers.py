import json
from pathlib import Path

import httpx
import pytest

from ventoy_library.errors import LibraryError
from ventoy_library.providers.arch import ArchProvider
from ventoy_library.providers.common import read_text
from ventoy_library.providers.systemrescue import SystemRescueProvider
from ventoy_library.providers.ubuntu import UbuntuServerProvider

FIXTURES = Path(__file__).parent / "fixtures" / "providers"


def test_arch_recorded_metadata():
    data = json.loads((FIXTURES / "arch.json").read_text())
    release = ArchProvider().parse(data)
    assert release.version == "2026.09.01"
    assert release.size == 1608286208
    assert (
        release.url
        == "https://fastly.mirror.pkgbuild.com/iso/2026.09.01/archlinux-2026.09.01-x86_64.iso"
    )
    assert release.checksum == data["releases"][0]["sha256_sum"]
    data["releases"][0]["available"] = False
    assert ArchProvider().parse(data).version == "2026.08.01"


@pytest.mark.parametrize("data", [{}, {"releases": []}, {"releases": [None]}])
def test_arch_malformed(data):
    with pytest.raises(LibraryError):
        ArchProvider().parse(data)


def test_arch_rejects_wrong_arch_and_url():
    data = json.loads((FIXTURES / "arch.json").read_text())
    data["releases"] = data["releases"][:1]
    data["releases"][0]["iso_url"] = "https://untrusted.invalid/image.iso"
    with pytest.raises(LibraryError, match="URL"):
        ArchProvider().parse(data)
    data["releases"][0]["torrent"]["file_name"] = "archlinux-aarch64.iso"
    with pytest.raises(LibraryError, match="No available"):
        ArchProvider().parse(data)


def test_systemrescue_official_page_fixture():
    version, filename, url, sums = SystemRescueProvider().parse(
        (FIXTURES / "systemrescue.html").read_text()
    )
    assert version == "13.02" and filename == "systemrescue-13.02-amd64.iso"
    assert url.startswith("https://fastly-cdn.system-rescue.org/")
    assert (
        sums == "https://www.system-rescue.org/releases/13.02/systemrescue-13.02-amd64.iso.sha256"
    )


def test_systemrescue_discovery():
    def handler(request):
        if request.method == "HEAD":
            return httpx.Response(200, headers={"Content-Length": "1381629952"})
        name = (
            "systemrescue.sha256" if request.url.path.endswith(".sha256") else "systemrescue.html"
        )
        return httpx.Response(200, text=(FIXTURES / name).read_text())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        release = SystemRescueProvider(client).get_latest_release()
    assert release.size == 1381629952
    assert release.checksum_algorithm == "sha256"


@pytest.mark.parametrize(
    "html",
    [
        "",
        '<a href="https://other.invalid/systemrescue-13.02-amd64.iso">ISO</a>',
        '<a href="https://fastly-cdn.system-rescue.org/systemrescue-14.00-beta-amd64.iso">beta</a>',
    ],
)
def test_systemrescue_no_stable_link(html):
    with pytest.raises(LibraryError):
        SystemRescueProvider().parse(html)


def test_ubuntu_discovery_recorded_metadata():
    def handler(request):
        if request.method == "HEAD":
            return httpx.Response(200, headers={"Content-Length": "2927861760"})
        filename = {
            "/meta-release-lts": "ubuntu-lts.txt",
            "/": "ubuntu-index.html",
            "/26.04/": "ubuntu-release.html",
            "/26.04/SHA256SUMS": "ubuntu-SHA256SUMS",
        }[request.url.path]
        return httpx.Response(200, text=(FIXTURES / filename).read_text())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        release = UbuntuServerProvider(client).get_latest_release()
    assert release.version == "26.04.1"
    assert release.filename == "ubuntu-26.04.1-live-server-amd64.iso"
    assert release.size == 2927861760
    assert release.checksum == "cc8a95cde20f6ced61a322420de00f10cc3c90ced545daa46cb9c1a117f1d927"


def test_ubuntu_lts_only():
    text = """Version: 24.04.5 LTS
Supported: 1

Version: 26.04 LTS
Supported: 0

Version: 26.10
Supported: 1

Version: 28.04-beta LTS
Supported: 1
"""
    assert UbuntuServerProvider.latest_lts(text) == "24.04.5"
    with pytest.raises(LibraryError):
        UbuntuServerProvider.latest_lts("Version: 26.10\nSupported: 1")


def test_metadata_size_limit():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=b"x" * (2 * 1024**2 + 1))
        )
    ) as client:
        with pytest.raises(LibraryError, match="safety limit"):
            read_text(client, "https://example.invalid/metadata")


def test_ubuntu_desktop_and_server_are_separate_artifacts():
    from ventoy_library.providers.ubuntu_desktop import UbuntuDesktopProvider

    def handler(request):
        if request.method == "HEAD":
            return httpx.Response(200, headers={"Content-Length": "6553600000"})
        filename = {
            "/meta-release-lts": "ubuntu-lts.txt",
            "/": "ubuntu-index.html",
            "/26.04/": "ubuntu-release.html",
            "/26.04/SHA256SUMS": "ubuntu-SHA256SUMS",
        }[request.url.path]
        return httpx.Response(200, text=(FIXTURES / filename).read_text())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        desktop = UbuntuDesktopProvider(client).get_latest_release()
        server = UbuntuServerProvider(client).get_latest_release()
    assert desktop.provider == "ubuntu-desktop" and desktop.category == "desktop"
    assert desktop.filename == "ubuntu-26.04.1-desktop-amd64.iso"
    assert desktop.checksum == "601e30fbf5d97759367c632e2c33630665039b7e2158fd068403da3ccf1bda1f"
    assert desktop.filename != server.filename
    assert desktop.checksum != server.checksum
