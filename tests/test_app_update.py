import json
import subprocess
from pathlib import Path

import httpx
import pytest
from packaging.version import Version

from ventoy_library import app_update
from ventoy_library.errors import LibraryError
from ventoy_library.metadata import GIT_SOURCE, PROJECT_NAME


def test_latest_release_fixture():
    rows = json.loads((Path(__file__).parent / "fixtures" / "releases.json").read_text())
    with httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=rows))
    ) as c:
        latest = app_update.latest_release(c)
    assert latest.tag == "v0.10.0"
    assert latest.version > Version("0.9.0")


@pytest.mark.parametrize(
    "tag",
    ["v1.0.0rc1", "v1.0.0-beta", "v1.0.0.dev1", "", "main", "v01.2.3", "v1.0.0; echo bad", "1.0"],
)
def test_invalid_or_prerelease_tags(tag):
    assert app_update.stable_tag(tag) is None


def test_tags_fallback_and_no_releases():
    def handler(req):
        rows = [] if req.url.path.endswith("releases") else [{"name": "v1.0.0"}]
        return httpx.Response(200, json=rows)

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        assert app_update.latest_release(c).version == Version("1.0.0")
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=[]))) as c:
        assert app_update.latest_release(c) is None


def test_prereleases_do_not_fall_back_to_tags():
    def handler(req):
        assert req.url.path.endswith("releases")
        return httpx.Response(
            200, json=[{"tag_name": "v1.0.0", "prerelease": True, "draft": False}]
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        assert app_update.latest_release(c) is None


@pytest.mark.parametrize("status", [403, 404, 429, 500])
def test_api_errors(status):
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status))) as c:
        with pytest.raises(LibraryError):
            app_update.latest_release(c)


@pytest.mark.parametrize("data", [None, {}, [None], [{"tag_name": "v1.0.0"}]])
def test_malformed_api(data):
    with httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=data))
    ) as c:
        with pytest.raises(LibraryError):
            app_update.latest_release(c)


def test_no_network():
    def handler(req):
        raise httpx.ConnectError("offline")

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(LibraryError, match="network"):
            app_update.latest_release(c)


def test_pagination():
    def handler(req):
        page = req.url.params["page"]
        row = {"tag_name": "v1.0.0", "draft": False, "prerelease": False}
        return httpx.Response(
            200,
            json=[row] * 100
            if page == "1"
            else [{"tag_name": "v2.0.0", "draft": False, "prerelease": False}],
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        assert app_update.latest_release(c).tag == "v2.0.0"


def test_installation_detection(root):
    assert app_update.installation_kind(root, {"dir_info": {"editable": True}}) == "development"
    assert app_update.installation_kind(root, {}) == "unsupported"
    metadata = {"main_package": {"package": PROJECT_NAME, "package_or_url": GIT_SOURCE}}
    (root / "pipx_metadata.json").write_text(json.dumps(metadata))
    assert app_update.installation_kind(root, {}) == "pipx"
    wheel_name = "ventoy_library-0.1.0-py3-none-any.whl"
    metadata["main_package"]["package_or_url"] = str(root / wheel_name)
    (root / "pipx_metadata.json").write_text(json.dumps(metadata))
    assert app_update.installation_kind(root, {"url": (root / wheel_name).as_uri()}) == "pipx"
    metadata["main_package"]["suffix"] = "-test"
    (root / "pipx_metadata.json").write_text(json.dumps(metadata))
    assert app_update.installation_kind(root, {}) == "unsupported"
    assert app_update.installation_kind(root, {"url": "file:///checkout"}) == "unsupported"


def test_update_command_and_run(root, monkeypatch):
    prefix = root / PROJECT_NAME
    monkeypatch.setattr(app_update, "installation_kind", lambda: "pipx")
    monkeypatch.setattr(app_update.shutil, "which", lambda name: "/bin/pipx")
    monkeypatch.setattr(app_update.sys, "prefix", str(prefix))
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=str(root) + "\n")

    monkeypatch.setattr(app_update.subprocess, "run", run)
    release = app_update.AppRelease(
        "v0.2.0",
        Version("0.2.0"),
        "ventoy_library-0.2.0-py3-none-any.whl",
        "https://github.com/numberformat/ventoy-library/releases/download/v0.2.0/ventoy_library-0.2.0-py3-none-any.whl",
        100,
        "sha256:" + "a" * 64,
    )
    executable = app_update.update_executable(release)
    command = app_update.update_command(executable, root / release.wheel_name)
    assert command == ["/bin/pipx", "install", "--force", str(root / release.wheel_name)]
    assert len(calls) == 1  # Detection is read-only.
    assert app_update.run_update(command) == 0
    assert calls[-1] == command


@pytest.mark.parametrize("kind", ["development", "unsupported"])
def test_unsupported_update(kind, monkeypatch):
    monkeypatch.setattr(app_update, "installation_kind", lambda: kind)
    release = app_update.AppRelease(
        "v1.0.0",
        Version("1.0.0"),
        "ventoy_library-1.0.0-py3-none-any.whl",
        "https://github.com/numberformat/ventoy-library/releases/download/v1.0.0/ventoy_library-1.0.0-py3-none-any.whl",
        100,
        "sha256:" + "a" * 64,
    )
    with pytest.raises(LibraryError):
        app_update.update_executable(release)


def test_mismatched_pipx_environment(root, monkeypatch):
    monkeypatch.setattr(app_update, "installation_kind", lambda: "pipx")
    monkeypatch.setattr(app_update.shutil, "which", lambda name: "/bin/pipx")
    monkeypatch.setattr(
        app_update.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a, 0, stdout=str(root)),
    )
    release = app_update.AppRelease(
        "v1.0.0",
        Version("1.0.0"),
        "ventoy_library-1.0.0-py3-none-any.whl",
        "https://github.com/numberformat/ventoy-library/releases/download/v1.0.0/ventoy_library-1.0.0-py3-none-any.whl",
        100,
        "sha256:" + "a" * 64,
    )
    with pytest.raises(LibraryError, match="does not manage"):
        app_update.update_executable(release)


@pytest.mark.parametrize("data", [{"dir_info": None}, {"url": 42}, []])
def test_malformed_install_metadata(root, data):
    assert app_update.installation_kind(root, data) == "unsupported"


@pytest.mark.parametrize(
    "package",
    [
        None,
        [],
        {"package_or_url": None},
        {"package": PROJECT_NAME, "package_or_url": GIT_SOURCE + ".untrusted"},
    ],
)
def test_malformed_pipx_metadata(root, package):
    (root / "pipx_metadata.json").write_text(json.dumps({"main_package": package}))
    assert app_update.installation_kind(root, {}) == "unsupported"
