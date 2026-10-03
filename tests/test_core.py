import hashlib
import json
from dataclasses import replace

import pytest

from ventoy_library import config
from ventoy_library.errors import LibraryError, SafetyError, StateError
from ventoy_library.models import Action, Plan, PlannedDownload, VerificationStatus
from ventoy_library.planner import build_plan
from ventoy_library.progress import Progress, format_bytes
from ventoy_library.providers import Registry, default_registry
from ventoy_library.safety import component, contained, destination
from ventoy_library.state import StateStore
from ventoy_library.storage import StorageReport, inspect
from ventoy_library.verification import verify


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "UNKNOWN"),
        (0, "0.0 B"),
        (1024, "1.0 KiB"),
        (1024**2, "1.0 MiB"),
        (1024**3, "1.0 GiB"),
        (-1024, "-1.0 KiB"),
    ],
)
def test_format(value, expected):
    assert format_bytes(value) == expected


def test_progress():
    p = Progress({"a": 10, "b": 30})
    p.update("a", 10)
    p.update("b", 10)
    assert p.percentage == 50
    p.update("b", 0)
    assert p.downloaded == 10
    assert "25.0%" in p.render("a")
    with pytest.raises(ValueError):
        p.update("a", 11)


def test_unknown_progress():
    p = Progress({"a": None, "b": 3})
    p.update("a", 100)
    assert p.total is None and p.percentage is None
    assert "1 files have unknown sizes" in p.render("a")
    assert "%" not in p.render("a")
    assert Progress({}).percentage == 100


@pytest.mark.parametrize("free,margin,shortfall", [(20, 5, 0), (14, 5, 1), (9, 0, 1)])
def test_storage(free, margin, shortfall):
    report = StorageReport(100, 100 - free, free, 20, 10, margin)
    assert report.required_free == 10 + margin
    assert report.shortfall == shortfall
    assert report.projected_free == free - 10
    if shortfall:
        with pytest.raises(SafetyError):
            report.require_safe()
    else:
        report.require_safe()


def test_unknown_storage():
    with pytest.raises(SafetyError, match="Unknown"):
        StorageReport(100, 0, 100, 0, None, 0).require_safe()


def test_inspect(root, monkeypatch):
    from collections import namedtuple

    usage = namedtuple("Usage", "total used free")(100, 10, 90)
    monkeypatch.setattr("ventoy_library.storage.shutil.disk_usage", lambda path: usage)
    assert inspect(root, Plan(()), 20).required_free == 20
    with pytest.raises(SafetyError):
        inspect(root, Plan(()), -1)


def test_registry(provider):
    registry = Registry()
    registry.register(provider)
    assert registry.select() == [provider]
    assert registry.select(["example", "example"]) == [provider]
    with pytest.raises(LibraryError):
        registry.register(provider)
    with pytest.raises(LibraryError):
        registry.select(["typo"])
    assert len(default_registry().select()) == 24


def test_plan(root, provider, record):
    plan = build_plan([provider], root, [])
    assert plan.total_bytes == 3 and len(plan.downloads) == 1
    assert plan.items[0].action == Action.DOWNLOAD
    plan = build_plan([provider], root, [replace(record, version="0.9")])
    assert plan.items[0].action == Action.UPDATE
    target = contained(root, record.relative_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"abc")
    assert build_plan([provider], root, [record]).items[0].action == Action.RELOCATE
    # An untracked nested file is never taken over or deleted automatically.
    assert build_plan([provider], root, []).items[0].action == Action.DOWNLOAD


def test_flat_existing_image_is_adopted_only_with_checksum(root, provider, release):
    target = root / "ISO" / release.filename
    target.parent.mkdir()
    target.write_bytes(b"abc")
    assert build_plan([provider], root, []).items[0].action == Action.ADOPT
    provider.get_latest_release = lambda: replace(release, checksum=None, checksum_algorithm=None)
    assert build_plan([provider], root, []).items[0].action == Action.ERROR


def test_flat_managed_image_is_current(root, provider, record):
    flat = replace(record, relative_path=f"ISO/{record.filename}")
    path = root / flat.relative_path
    path.parent.mkdir()
    path.write_bytes(b"abc")
    StateStore(root).save([flat])
    assert build_plan([provider], root, [flat]).items[0].action == Action.CURRENT


def test_flat_filename_collision_is_rejected_case_insensitively(root, provider, release):
    class Second:
        name = "second"
        category = release.category
        architecture = release.architecture

        def get_latest_release(self):
            return replace(release, provider="second", filename=release.filename.upper())

    plan = build_plan([provider, Second()], root, [])
    assert [item.action for item in plan.items] == [Action.DOWNLOAD, Action.ERROR]


def test_plan_unknown_and_probe(root, provider, release):
    provider.get_latest_release = lambda: replace(release, size=None)
    assert build_plan([provider], root, []).total_bytes is None
    plan = build_plan([provider], root, [], size_probe=lambda url: 100)
    assert plan.total_bytes == 100


def test_plan_manual_and_alternate(root, provider, release):
    path = root / "local.iso"
    path.write_bytes(b"abc")
    plan = build_plan([provider], root, [], {"example": str(path)})
    assert plan.items[0].acquisition_method == "local-file"
    plan = build_plan([provider], root, [], {"example": "https://example.invalid/alternate"})
    assert plan.items[0].acquisition_method == "alternate-url"
    assert plan.items[0].release.checksum == release.checksum
    provider.get_latest_release = lambda: replace(release, url=None)
    assert build_plan([provider], root, []).items[0].action == Action.MANUAL
    with pytest.raises(LibraryError):
        build_plan([provider], root, [], {"wrong": str(path)})


def test_discovery_error_does_not_stop_other_providers(root, provider, release):
    class Broken:
        name = "broken"

        def get_latest_release(self):
            raise LibraryError("upstream unavailable")

    plan = build_plan([Broken(), provider], root, [])
    assert [i.action for i in plan.items] == [Action.ERROR, Action.DOWNLOAD]


def test_unknown_plan_ignores_current(root, release):
    release = replace(release, size=None)
    plan = Plan((PlannedDownload("example", release, root / "x", Action.CURRENT),))
    assert plan.total_bytes == 0 and plan.unknown_sizes == 0


@pytest.mark.parametrize(
    "name",
    ["", "..", "../x", "/x", "x/y", "x\\y", ".hidden", "CON", "COM1.iso", "x\n.iso", "x.", "a:b"],
)
def test_unsafe_names(name):
    with pytest.raises(SafetyError):
        component(name)


def test_containment(root):
    with pytest.raises(SafetyError):
        contained(root, "../outside")
    with pytest.raises(SafetyError):
        contained(root, "/etc/passwd")
    with pytest.raises(SafetyError):
        destination("/")
    with pytest.raises(SafetyError):
        destination("")
    with pytest.raises(SafetyError):
        destination(root / "missing")
    (root / "link").symlink_to(root, target_is_directory=True)
    with pytest.raises(SafetyError):
        contained(root, "link/a.iso")
    with pytest.raises(SafetyError):
        destination(root / "link")


@pytest.mark.parametrize("algorithm", ["sha256", "sha512"])
def test_checksum(root, algorithm):
    path = root / "image"
    path.write_bytes(b"abc")
    digest = hashlib.new(algorithm, b"abc").hexdigest()
    assert verify(path, algorithm, digest, 3) == VerificationStatus.VERIFIED
    with pytest.raises(LibraryError, match="Checksum mismatch"):
        verify(path, algorithm, "0" * len(digest))
    assert verify(path, None, None) == VerificationStatus.UNVERIFIED
    with pytest.raises(LibraryError, match="size mismatch"):
        verify(path, algorithm, digest, 4)


def test_state_roundtrip_backup(root, record, new_record):
    store = StateStore(root)
    assert store.load() == []
    assert list(root.iterdir()) == []
    store.save([record])
    assert store.load() == [record]
    store.save([record, new_record])
    store._path().write_text("{corrupt")
    with pytest.warns(UserWarning, match="backup"):
        assert store.load() == [record]
    with pytest.warns(UserWarning):
        store.save([record])
    assert store.load() == [record]


def test_corrupt_state_no_backup(root):
    store = StateStore(root)
    store._path().parent.mkdir()
    store._path().write_text("null")
    with pytest.raises(StateError):
        store.load()


def test_atomic_failure_preserves_state(root, record, new_record, monkeypatch):
    store = StateStore(root)
    store.save([record])
    import ventoy_library.atomic as atomic

    original = atomic.os.replace

    def fail(src, dst):
        if dst.name == "state.json":
            raise OSError("disk failure")
        return original(src, dst)

    monkeypatch.setattr(atomic.os, "replace", fail)
    with pytest.raises(OSError):
        store.save([record, new_record])
    assert store.load() == [record]
    assert not list(store._path().parent.glob("*.tmp"))


def test_state_lock(root):
    store = StateStore(root)
    with store.lock():
        with pytest.raises(StateError, match="locked"), store.lock():
            pass
    with store.lock():
        pass


@pytest.mark.parametrize("relative", ["../outside", "/etc/passwd", "ISO/rescue/other/a.iso"])
def test_invalid_state_paths(root, record, relative):
    with pytest.raises((StateError, SafetyError)):
        StateStore(root).save([replace(record, relative_path=relative)])


def test_delete_requires_tracked_replacement(root, record, new_record):
    store = StateStore(root)
    with pytest.raises(SafetyError, match="not tracked"):
        store.remove_old(record, new_record)
    old = contained(root, record.relative_path)
    new = contained(root, new_record.relative_path)
    old.parent.mkdir(parents=True)
    old.write_bytes(b"abc")
    new.write_bytes(b"bad")
    store.save([record, new_record])
    with pytest.raises(LibraryError, match="Checksum mismatch"):
        store.remove_old(record, new_record)
    assert old.exists()
    new.write_bytes(b"abc")
    store.remove_old(record, new_record, keep_old=True)
    assert old.exists()
    store.remove_old(record, new_record)
    assert not old.exists() and new.exists()
    assert store.load() == [new_record]


def test_delete_symlink_refused(root, record, new_record):
    store = StateStore(root)
    store.save([record, new_record])
    old = contained(root, record.relative_path)
    old.parent.mkdir(parents=True)
    outside = root / "unmanaged"
    outside.write_bytes(b"abc")
    old.symlink_to(outside)
    with pytest.raises(SafetyError):
        store.remove_old(record, new_record)
    assert outside.exists()


def test_config(root):
    path = root / "config" / "config.json"
    assert config.load(path).safety_margin == 2 * 1024**3
    assert not path.exists()
    config.set_value("destination", str(root), path)
    config.set_value("safety_margin", "10", path)
    assert config.load(path).destination == str(root)
    assert config.load(path).safety_margin == 10 * 1024**3
    with pytest.raises(LibraryError):
        config.set_value("safety_margin", "-1", path)
    path.write_text(json.dumps({"safety_margin": "bad"}))
    with pytest.raises(LibraryError):
        config.load(path)


@pytest.mark.parametrize(
    "field,value", [("relative_path", None), ("source_url", 42), ("version", []), ("checksum", 123)]
)
def test_malformed_state_records_recover(root, record, field, value):
    from dataclasses import asdict

    store = StateStore(root)
    store.save([record])
    store.save([record])
    row = asdict(record)
    row[field] = value
    store._path().write_text(json.dumps({"schema_version": 1, "images": [row]}))
    with pytest.warns(UserWarning, match="backup"):
        assert store.load() == [record]


@pytest.mark.parametrize(
    "value,expected", [("2", 2 * 1024**3), ("0.5", 512 * 1024**2), ("0", 0), ("0.0000000001", 1)]
)
def test_safety_margin_gib(root, value, expected):
    path = root / "config.json"
    config.set_value("safety_margin", value, path)
    assert config.load(path).safety_margin == expected
    assert json.loads(path.read_text())["safety_margin"] == expected


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "invalid"])
def test_invalid_safety_margin_preserves_config(root, value):
    path = root / "config.json"
    config.set_value("safety_margin", "2", path)
    before = path.read_bytes()
    with pytest.raises(LibraryError, match="GiB"):
        config.set_value("safety_margin", value, path)
    assert path.read_bytes() == before
