import json
import tomllib
from pathlib import Path

import pytest

from ventoy_library import cli
from ventoy_library.config import Config
from ventoy_library.metadata import PROJECT_NAME, REPOSITORY_URL
from ventoy_library.providers import Registry


@pytest.fixture(autouse=True)
def isolate_config(root, monkeypatch):
    monkeypatch.setattr("ventoy_library.config.config_path", lambda: root / "config.json")
    monkeypatch.setattr(cli, "default_registry", Registry)


@pytest.mark.parametrize("flag", ["--help", "--version"])
def test_help_version(flag, capsys):
    with pytest.raises(SystemExit) as result:
        cli.main([flag])
    assert result.value.code == 0
    assert PROJECT_NAME in capsys.readouterr().out


def test_no_command():
    assert cli.main([]) == 0


def test_config_commands(root, capsys):
    assert cli.main(["config", "show"]) == 0
    assert json.loads(capsys.readouterr().out)["destination"] is None
    assert list(root.iterdir()) == []
    assert cli.main(["config", "set", "destination", str(root)]) == 0
    assert json.loads((root / "config.json").read_text())["destination"] == str(root)


def test_missing_destination(capsys):
    assert cli.main(["check"]) == 1
    assert "No mounted Ventoy detected" in capsys.readouterr().err
    assert cli.main(["list"]) == 0


@pytest.mark.parametrize("args", [["list"], ["check"], ["status"], ["update-images", "--dry-run"]])
def test_empty_registry_commands(root, args, capsys):
    assert cli.main([*args, "--directory", "--destination", str(root)]) == 0
    assert list(root.iterdir()) == []
    assert "Destination:" in capsys.readouterr().out


def test_unknown_provider(root, capsys):
    assert cli.main(["check", "--directory", "--destination", str(root), "--only", "typo"]) == 1
    assert "Unknown provider" in capsys.readouterr().err


def test_dry_run_no_mutation(root, provider, monkeypatch, capsys):
    registry = Registry()
    registry.register(provider)
    monkeypatch.setattr(cli, "default_registry", lambda: registry)
    monkeypatch.setattr(cli.config, "load", lambda: Config(str(root), 0, "directory"))
    assert cli.main(["update-images", "--dry-run"]) == 0
    assert list(root.iterdir()) == []
    text = capsys.readouterr().out
    assert "example-1.iso" in text and "https://example.invalid/image.iso" in text
    assert "DOWNLOAD" in text


def test_local_cli_end_to_end(root, provider, monkeypatch):
    registry = Registry()
    registry.register(provider)
    monkeypatch.setattr(cli, "default_registry", lambda: registry)
    monkeypatch.setattr(cli.config, "load", lambda: Config(str(root), 0, "directory"))
    source = root / "local.iso"
    source.write_bytes(b"abc")
    assert cli.main(["update-images", "--no-interactive", "--local", f"example={source}"]) == 0
    assert (root / "ISO/rescue/example/example-1.iso").read_bytes() == b"abc"


def test_metadata_consistency():
    metadata = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())[
        "project"
    ]
    assert metadata["name"] == PROJECT_NAME
    assert metadata["urls"]["Repository"] == REPOSITORY_URL
    assert metadata["scripts"][PROJECT_NAME] == "ventoy_library.cli:main"


def test_application_check_is_read_only(monkeypatch, capsys):
    from packaging.version import Version

    monkeypatch.setattr(
        cli.app_update, "latest_release", lambda c: cli.app_update.stable_tag("v0.2.0")
    )
    monkeypatch.setattr(cli.app_update, "installed_version", lambda: Version("0.1.0"))
    monkeypatch.setattr(cli.app_update, "run_update", lambda c: pytest.fail("must not run"))
    assert cli.main(["--check-update"]) == 0
    assert "Application update available" in capsys.readouterr().out


def test_application_update_exits(monkeypatch):
    from packaging.version import Version

    monkeypatch.setattr(
        cli.app_update, "latest_release", lambda c: cli.app_update.stable_tag("v0.2.0")
    )
    monkeypatch.setattr(cli.app_update, "installed_version", lambda: Version("0.1.0"))
    monkeypatch.setattr(cli.app_update, "update_command", lambda r: ["pipx", "test"])
    monkeypatch.setattr(cli.app_update, "run_update", lambda c: 9)
    assert cli.main(["--update", "--yes"]) == 9


def test_update_flags_separate_from_images():
    assert cli.main(["--update", "check"]) == 1


def test_config_set_safety_margin_gib(root, capsys):
    assert cli.main(["config", "set", "safety_margin", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["safety_margin"] == 2 * 1024**3
    assert json.loads((root / "config.json").read_text())["safety_margin"] == 2 * 1024**3
