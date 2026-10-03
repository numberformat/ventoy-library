"""Offline upstream samples and adversarial metadata for runtime providers."""

import httpx
import pytest

from ventoy_library.errors import LibraryError
from ventoy_library.providers.alpine import AlpineProvider
from ventoy_library.providers.clonezilla import ClonezillaProvider
from ventoy_library.providers.debian import DebianProvider
from ventoy_library.providers.freebsd import FreeBSDProvider
from ventoy_library.providers.gparted import GPartedProvider
from ventoy_library.providers.kali import KaliProvider
from ventoy_library.providers.rescuezilla import RescuezillaProvider
from ventoy_library.providers.tails import TailsProvider

DIGEST = "a" * 64


def anchors(*hrefs):
    return "".join(f'<a href="{href}">file</a>' for href in hrefs)


@pytest.mark.parametrize(
    "provider,old,new,ignored,manifest",
    [
        (
            AlpineProvider,
            "alpine-standard-3.24.1-x86_64.iso",
            "alpine-standard-3.24.2-x86_64.iso",
            "alpine-virt-9.0.0-x86_64.iso",
            ".sha256",
        ),
        (
            DebianProvider,
            "debian-13.6.0-amd64-netinst.iso",
            "debian-13.7.0-amd64-netinst.iso",
            "debian-99.0.0-arm64-netinst.iso",
            "SHA256SUMS",
        ),
        (
            KaliProvider,
            "kali-linux-2026.1-live-amd64.iso",
            "kali-linux-2026.2-live-amd64.iso",
            "kali-linux-2099.1-installer-amd64.iso",
            "SHA256SUMS",
        ),
    ],
)
def test_index_providers_select_stable_artifact_and_checksum(provider, old, new, ignored, manifest):
    p = provider()
    sidecar = new + manifest if manifest.startswith(".") else manifest
    html = anchors(old, new, ignored, new + ".torrent", sidecar)
    assert p.parse(html) == (
        new.split("-")[2]
        if provider is AlpineProvider
        else new.split("-")[1]
        if provider is DebianProvider
        else new.split("-")[2],
        new,
        p.metadata_url + new,
        p.metadata_url + sidecar,
    )

    def handler(request):
        if request.method == "HEAD":
            return httpx.Response(200, headers={"Content-Length": "123456"})
        if request.url.path.endswith(sidecar):
            return httpx.Response(200, text=f"{DIGEST}  {new}\n")
        return httpx.Response(200, text=html)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        release = provider(client).get_latest_release()
    assert release.filename == new and release.size == 123456
    assert release.checksum == DIGEST and release.architecture == "x86_64"


@pytest.mark.parametrize(
    "provider,bad",
    [
        (AlpineProvider, "alpine-standard-9.0.0-aarch64.iso"),
        (DebianProvider, "debian-99.0.0-arm64-netinst.iso"),
        (KaliProvider, "kali-linux-2099.1-live-arm64.iso"),
    ],
)
def test_index_providers_reject_wrong_arch_and_malformed_metadata(provider, bad):
    p = provider()
    with pytest.raises(LibraryError):
        p.parse(anchors(bad, "https://evil.invalid/" + bad))
    with pytest.raises(LibraryError):
        p.parse(anchors("../" + bad, "not-an-iso"))


def test_index_providers_ignore_prereleases_and_wrong_host():
    for provider, bad in [
        (AlpineProvider, "alpine-standard-9.0.0_rc1-x86_64.iso"),
        (DebianProvider, "debian-99.0.0-rc1-amd64-netinst.iso"),
        (KaliProvider, "kali-linux-2099.1-weekly-live-amd64.iso"),
    ]:
        p = provider()
        with pytest.raises(LibraryError):
            p.parse(anchors(bad, "https://evil.invalid/" + bad))


def tails_row(version, *, kind="iso", arch="amd64"):
    filename = f"tails-{arch}-{version}.{kind}"
    return {
        "version": version,
        "installation-paths": [
            {
                "type": kind,
                "target-files": [
                    {
                        "url": f"https://download.tails.net/tails/stable/tails-{arch}-{version}/{filename}",
                        "size": 100,
                        "sha256": DIGEST,
                    }
                ],
            }
        ],
    }


def test_tails_selects_latest_iso_and_rejects_wrong_metadata():
    p = TailsProvider()
    data = {
        "build_target": "amd64",
        "channel": "stable",
        "product-name": "Tails",
        "installations": [
            tails_row("7.1"),
            tails_row("7.14"),
            tails_row("99.0", kind="img"),
            tails_row("100.0rc1"),
        ],
    }
    assert p.parse(data).version == "7.14"
    assert p.parse(data).checksum == DIGEST
    for change in (
        {"build_target": "arm64"},
        {"channel": "testing"},
        {"installations": [tails_row("7.14", arch="arm64")]},
        {"installations": [{}]},
    ):
        with pytest.raises(LibraryError):
            p.parse(data | change)


def rescue_row(version, *, primary=True, prerelease=False):
    name = f"rescuezilla-{version}-64bit.resolute.iso"
    prefix = f"https://github.com/rescuezilla/rescuezilla/releases/download/{version}/"
    body = (
        f"**Download the 64-bit version: [{name}]({prefix}{name})**" if primary else "Other builds"
    )
    return {
        "tag_name": version,
        "draft": False,
        "prerelease": prerelease,
        "body": body,
        "assets": [
            {"name": name, "browser_download_url": prefix + name, "size": 100},
            {
                "name": f"rescuezilla-{version}-64bit.noble.iso",
                "browser_download_url": prefix + f"rescuezilla-{version}-64bit.noble.iso",
                "size": 90,
            },
        ],
    }


def test_rescuezilla_primary_stable_selection_and_rejections():
    p = RescuezillaProvider()
    release, sums = p.parse(
        [rescue_row("2.5"), rescue_row("2.6.2"), rescue_row("99.0", prerelease=True)]
    )
    assert release.version == "2.6.2" and release.filename.endswith("resolute.iso")
    assert release.size == 100 and sums is None
    for bad in (
        [rescue_row("3.0", primary=False)],
        [rescue_row("3.0") | {"assets": []}],
        [
            rescue_row("3.0")
            | {
                "assets": [
                    {"name": "bad", "size": 1, "browser_download_url": "https://evil.invalid/bad"}
                ]
            }
        ],
        [{}],
        [rescue_row("3.0", prerelease=True)],
    ):
        with pytest.raises(LibraryError):
            p.parse(bad)


def test_freebsd_production_disc1_and_manifest():
    p = FreeBSDProvider()
    versions = p.parse_versions(anchors("14.5/", "15.1/", "16.0-BETA/", "../"))
    assert versions[0][0] == "15.1"
    directory = p.metadata_url + "15.1/"
    filename = "FreeBSD-15.1-RELEASE-amd64-disc1.iso"
    html = anchors(
        filename,
        "FreeBSD-15.1-RC1-amd64-disc1.iso",
        "FreeBSD-15.1-RELEASE-arm64-disc1.iso",
        "CHECKSUM.SHA256-FreeBSD-15.1-RELEASE-amd64",
    )
    assert p.parse_release(html, "15.1", directory)[0] == filename
    assert p.parse_checksum(f"SHA256 ({filename}) = {DIGEST}\n", filename) == DIGEST
    with pytest.raises(LibraryError):
        p.parse_release(anchors("FreeBSD-15.1-RELEASE-amd64-dvd1.iso"), "15.1", directory)
    with pytest.raises(LibraryError):
        p.parse_checksum("bad", filename)


def test_gparted_official_stable_link_and_rejections():
    p = GPartedProvider()
    old = "gparted-live-1.8.1-5-amd64.iso"
    new = "gparted-live-1.8.1-6-amd64.iso"
    html = (
        "Stable Releases"
        + anchors(
            f"https://downloads.sourceforge.net/gparted/{old}",
            f"https://downloads.sourceforge.net/gparted/{new}",
            "https://downloads.sourceforge.net/gparted/gparted-live-99.0.0-1-i686.iso",
            p.checksum_url,
        )
        + "Testing Releases"
        + anchors("https://downloads.sourceforge.net/gparted/gparted-live-99.0.0-1-amd64.iso")
    )
    assert p.parse(html) == ("1.8.1-6", new, f"https://downloads.sourceforge.net/gparted/{new}")
    for bad in (
        "https://evil.invalid/gparted-live-99.0.0-1-amd64.iso",
        "https://downloads.sourceforge.net/gparted/gparted-live-99.0.0-1-arm64.iso",
        "https://downloads.sourceforge.net/gparted/gparted-live-99.0.0-1-amd64.iso.torrent",
    ):
        with pytest.raises(LibraryError):
            p.parse("Stable Releases" + anchors(bad, p.checksum_url) + "Testing Releases")


def test_clonezilla_stable_directory_and_iso_validation():
    p = ClonezillaProvider()
    versions = p.parse_versions(
        anchors("3.3.3-15/", "3.3.3-37/", "3.4.0-rc1/", "https://evil.invalid/99.0.0-1/")
    )
    assert versions[0][0] == "3.3.3-37"
    directory = p.metadata_url + "3.3.3-37/"
    filename = "clonezilla-live-3.3.3-37-amd64.iso"
    assert p.parse_release(
        anchors(filename + "/download", filename.replace("amd64", "arm64") + "/download"),
        "3.3.3-37",
        directory,
    ) == (filename, directory + filename + "/download")
    with pytest.raises(LibraryError):
        p.parse_release(anchors(filename + ".zip/download"), "3.3.3-37", directory)
    with pytest.raises(LibraryError):
        p.parse_versions(anchors("3.3.3-37-testing/", "../"))


def test_tails_mocked_runtime_json():
    import json

    data = {
        "build_target": "amd64",
        "channel": "stable",
        "product-name": "Tails",
        "installations": [tails_row("7.14")],
    }
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=json.dumps(data)))
    ) as client:
        release = TailsProvider(client).get_latest_release()
    assert release.filename == "tails-amd64-7.14.iso" and release.size == 100


def test_rescuezilla_mocked_runtime_api_and_manifest():
    row = rescue_row("2.6.2")
    prefix = "https://github.com/rescuezilla/rescuezilla/releases/download/2.6.2/"
    row["assets"].append({"name": "SHA256SUM", "browser_download_url": prefix + "SHA256SUM"})

    def handler(request):
        if request.url.host == "api.github.com":
            return httpx.Response(200, json=[row])
        return httpx.Response(200, text=f"{DIGEST}  rescuezilla-2.6.2-64bit.resolute.iso\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        release = RescuezillaProvider(client).get_latest_release()
    assert release.checksum == DIGEST and release.size == 100
    assert release.url == prefix + release.filename
    with pytest.raises(LibraryError):
        RescuezillaProvider().parse([rescue_row("2.5"), rescue_row("3.0", primary=False)])


def test_freebsd_mocked_runtime_release_and_size():
    p = FreeBSDProvider()
    version = "15.1"
    directory = p.metadata_url + version + "/"
    filename = f"FreeBSD-{version}-RELEASE-amd64-disc1.iso"
    manifest = f"CHECKSUM.SHA256-FreeBSD-{version}-RELEASE-amd64"

    def handler(request):
        if request.method == "HEAD":
            return httpx.Response(200, headers={"Content-Length": "123"})
        if request.url.path.endswith("ISO-IMAGES/"):
            return httpx.Response(200, text=anchors("15.1/", "16.0/"))
        if request.url.path.endswith("16.0/"):
            return httpx.Response(200, text=anchors("FreeBSD-16.0-BETA1-amd64-disc1.iso"))
        if request.url.path.endswith(manifest):
            return httpx.Response(200, text=f"SHA256 ({filename}) = {DIGEST}\n")
        return httpx.Response(200, text=anchors(filename, manifest))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        release = FreeBSDProvider(client).get_latest_release()
    assert release.url == directory + filename and release.checksum == DIGEST
    assert release.size == 123


def test_gparted_mocked_runtime_page_manifest_and_size():
    p = GPartedProvider()
    filename = "gparted-live-1.8.1-6-amd64.iso"
    url = "https://downloads.sourceforge.net/gparted/" + filename
    page = "Stable Releases" + anchors(url, p.checksum_url) + "Testing Releases"

    def handler(request):
        if request.method == "HEAD":
            return httpx.Response(200, headers={"Content-Length": "123"})
        if request.url.path.endswith("CHECKSUMS.TXT"):
            return httpx.Response(200, text=f"### SHA256SUMS:\n{DIGEST}  {filename}\n")
        return httpx.Response(200, text=page)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        release = GPartedProvider(client).get_latest_release()
    assert release.url == url and release.checksum == DIGEST and release.size == 123


def test_clonezilla_mocked_runtime_stable_directory_and_size():
    p = ClonezillaProvider()
    version = "3.3.3-37"
    directory = p.metadata_url + version + "/"
    filename = f"clonezilla-live-{version}-amd64.iso"

    def handler(request):
        if request.method == "HEAD":
            return httpx.Response(200, headers={"Content-Length": "123"})
        if request.url.path.endswith("clonezilla_live_stable/"):
            return httpx.Response(200, text=anchors("3.3.3-15/", "3.3.3-37/"))
        return httpx.Response(200, text=anchors(filename + "/download", filename + ".zip/download"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        release = ClonezillaProvider(client).get_latest_release()
    assert release.url == directory + filename + "/download"
    assert release.size == 123 and release.checksum is None
