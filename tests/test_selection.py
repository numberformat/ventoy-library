from dataclasses import replace

import httpx
import pytest

from ventoy_library import cli
from ventoy_library.catalog import CATALOG
from ventoy_library.config import Config
from ventoy_library.errors import LibraryError
from ventoy_library.models import Action
from ventoy_library.planner import build_plan
from ventoy_library.providers import Registry, default_registry
from ventoy_library.selection import prompt_selection, select_numbers, show_catalog
from ventoy_library.state import StateStore
from ventoy_library.storage import StorageReport


@pytest.fixture
def catalog():
    return default_registry().select()


@pytest.fixture(autouse=True)
def config(root, monkeypatch):
    monkeypatch.setattr(cli.config, "load", lambda: Config(str(root), 0, "directory"))


def terminal(monkeypatch, *answers):
    answers = iter(answers)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))


def test_catalog_exact_requested_projects(catalog):
    assert len(catalog) == 24
    assert [p.name for p in catalog] == [entry.name for entry in CATALOG]
    assert not {"nixos", "windows11", "proxmox"} & {p.name for p in catalog}
    assert {p.name for p in catalog if not p.manual} == {
        "arch",
        "systemrescue",
        "ubuntu-server",
        "ubuntu-desktop",
    }


@pytest.mark.parametrize(
    "choice,indices",
    [
        ("1,3,9-11", [1, 3, 9, 10, 11]),
        ("1 3 9", [1, 3, 9]),
        ("3,1,3", [1, 3]),
        ("0", list(range(1, 25))),
        ("all", list(range(1, 25))),
    ],
)
def test_numbers(catalog, choice, indices):
    assert select_numbers(choice, catalog) == [catalog[i - 1] for i in indices]


@pytest.mark.parametrize(
    "choice", ["", "-1", "30", "1,0", "0-2", "3-1", "abc", "all,1", "1,,3", "1,", "1-999999999999"]
)
def test_invalid_numbers(catalog, choice):
    with pytest.raises(LibraryError):
        select_numbers(choice, catalog)


def test_list_full_catalog_without_destination(monkeypatch, capsys):
    monkeypatch.setattr(cli.config, "load", lambda: Config())
    assert cli.main(["list"]) == 0
    text = capsys.readouterr().out
    assert "24  Ubuntu Desktop LTS" in text and "  0  All images" in text
    assert "  1  Arch Linux" in text and "  8  SystemRescue" in text
    assert "automatic" in text and "manual" in text
    assert "ventoy-library add" in text


def test_list_does_not_renumber_filtered_entries(catalog, capsys):
    show_catalog(catalog, [], names=["systemrescue"])
    assert "  8  SystemRescue" in capsys.readouterr().out


def test_list_shows_installed(root, record, capsys):
    StateStore(root).save(
        [replace(record, provider="arch", relative_path="ISO/desktop/arch/example-1.iso")]
    )
    assert cli.main(["list"]) == 0
    text = capsys.readouterr().out
    assert "1.0" in next(line for line in text.splitlines() if "Arch Linux" in line)


def test_prompt_retry_and_cancel(catalog, monkeypatch, capsys):
    terminal(monkeypatch, "30", "2,9")
    assert prompt_selection(catalog, []) == [catalog[1], catalog[8]]
    assert "Please try again" in capsys.readouterr().out
    terminal(monkeypatch, "q")
    assert prompt_selection(catalog, []) == []


def test_manual_selection_local_and_skip(root, catalog, monkeypatch):
    source = root / "alpine.iso"
    source.write_bytes(b"abc")
    terminal(monkeypatch, "1", str(source), "3")
    active, sources, skipped = cli.manual_choices([catalog[1], catalog[2]], {})
    assert active == [catalog[1]] and skipped == ["fedora"]
    plan = build_plan(active, root, [], sources)
    assert plan.total_bytes == 3
    assert plan.items[0].release.checksum is None
    assert plan.items[0].release.version == "user-supplied"


def test_manual_direct_url(root, catalog):
    plan = build_plan(
        [catalog[1]],
        root,
        [],
        {"alpine": "https://example.invalid/alpine.iso"},
        size_probe=lambda url: 42,
    )
    assert plan.total_bytes == 42
    assert plan.items[0].acquisition_method == "alternate-url"


def test_manual_without_source_is_honest(root, catalog):
    plan = build_plan([catalog[1]], root, [])
    assert plan.items[0].action == Action.MANUAL
    assert plan.items[0].release is None
    assert plan.downloads == ()


def test_interactive_add_cancellation_has_no_writes(root, monkeypatch):
    terminal(monkeypatch, "q")
    assert cli.main(["add"]) == 0
    assert list(root.iterdir()) == []


def test_noninteractive_requires_selection(root, capsys):
    assert cli.main(["add", "--no-interactive"]) == 1
    assert "Choose images" in capsys.readouterr().err
    assert list(root.iterdir()) == []


def test_selected_manual_image_imports_by_number(root, monkeypatch, capsys):
    source = root / "alpine.iso"
    source.write_bytes(b"abc")
    terminal(monkeypatch, "2", "1", str(source), "y")
    assert cli.main(["add"]) == 0
    assert (root / "ISO/desktop/alpine/alpine.iso").read_bytes() == b"abc"
    assert StateStore(root).load()[0].verification_status == "unverified"
    assert "UNVERIFIED" in capsys.readouterr().out


def test_numbered_local_noninteractive(root):
    source = root / "alpine.iso"
    source.write_bytes(b"abc")
    assert cli.main(["add", "--select", "2", "--local", f"2={source}", "--no-interactive"]) == 0
    assert (root / "ISO/desktop/alpine/alpine.iso").exists()


def test_numbered_dry_run_never_writes(root, capsys):
    source = root / "alpine.iso"
    source.write_bytes(b"abc")
    before = list(root.iterdir())
    assert cli.main(["add", "--select", "2", "--local", f"2={source}", "--dry-run"]) == 0
    assert list(root.iterdir()) == before
    assert "3.0 B" in capsys.readouterr().out


def test_all_selects_every_entry_before_download(root, monkeypatch):
    providers = default_registry().select()
    calls = []
    for p in providers:
        name = p.name

        def discover(name=name):
            calls.append(name)
            raise LibraryError("fixture: source unavailable")

        p.get_latest_release = discover
    registry = Registry()
    for p in providers:
        registry.register(p)
    monkeypatch.setattr(cli, "default_registry", lambda: registry)
    assert cli.main(["add", "--all", "--dry-run"]) == 1
    assert calls == [entry.name for entry in CATALOG]
    assert list(root.iterdir()) == []


def test_space_failure_prevents_all_downloads(root, provider, monkeypatch):
    registry = Registry()
    registry.register(provider)
    monkeypatch.setattr(cli, "default_registry", lambda: registry)
    monkeypatch.setattr(cli, "inspect", lambda *a: StorageReport(100, 99, 1, 0, 3, 2))
    monkeypatch.setattr(cli, "execute", lambda *a, **kw: pytest.fail("must not execute"))
    assert cli.main(["add", "--select", "1", "--no-interactive"]) == 1
    assert list(root.iterdir()) == []


def test_full_selection_plan_precedes_transfers(root, provider, release, monkeypatch):
    events = []
    registry = Registry()
    provider.get_latest_release = lambda: events.append("discover-one") or release

    class Second:
        name = "second"
        display_name = "Second"
        category = "rescue"
        architecture = "x86_64"

        def get_latest_release(self):
            events.append("discover-two")
            return replace(
                release,
                provider="second",
                filename="second.iso",
                url="https://example.invalid/second.iso",
            )

    registry.register(provider)
    registry.register(Second())
    monkeypatch.setattr(cli, "default_registry", lambda: registry)

    def handler(request):
        assert events[:2] == ["discover-one", "discover-two"]
        events.append("download")
        return httpx.Response(200, stream=httpx.ByteStream(b"abc"))

    monkeypatch.setattr(
        cli, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    terminal(monkeypatch, "0", "y")
    assert cli.main(["add"]) == 0
    assert events == ["discover-one", "discover-two", "download", "download"]
    assert len(StateStore(root).load()) == 2


def test_unknown_size_prevents_transfer(root, provider, release, monkeypatch):
    provider.get_latest_release = lambda: replace(release, size=None)
    registry = Registry()
    registry.register(provider)
    monkeypatch.setattr(cli, "default_registry", lambda: registry)

    def handler(request):
        assert request.method == "HEAD"
        return httpx.Response(200)

    monkeypatch.setattr(
        cli, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert cli.main(["add", "--select", "1", "--no-interactive"]) == 1
    assert list(root.iterdir()) == []


def test_documented_catalog_matches_registry(catalog):
    from pathlib import Path

    readme = (Path(__file__).parent.parent / "README.md").read_text()
    for number, provider in enumerate(catalog, 1):
        expected = (
            f"| {number} | {provider.display_name} | {provider.category} | "
            f"{provider.architecture} | {'No' if provider.manual else 'Yes'} |"
        )
        assert expected in readme
