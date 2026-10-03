from dataclasses import replace

import pytest

from ventoy_library import cli, destinations, volumes
from ventoy_library.config import Config
from ventoy_library.errors import SafetyError
from ventoy_library.models import Action, Plan, PlannedDownload
from ventoy_library.providers import Registry
from ventoy_library.volumes import Inventory, Volume


@pytest.fixture
def drive(root, monkeypatch):
    data = Volume("disk9s1", "disk9", 1, "My images", "exfat", root)
    boot = Volume("disk9s2", "disk9", 2, "VTOYEFI", "msdos", None)
    inventory = Inventory((data, boot))
    monkeypatch.setattr(destinations, "scan_volumes", lambda: inventory)
    monkeypatch.setattr(destinations.os.path, "ismount", lambda path: path == root)
    return inventory


def answers(monkeypatch, *values):
    iterator = iter(values)
    monkeypatch.setattr("builtins.input", lambda prompt: next(iterator))


def test_detect_data_without_ventoy_label(drive, root):
    target = destinations.resolve_target(None)
    assert target.root == root and target.ventoy
    assert drive.detected == (drive.volumes[0],)


@pytest.mark.parametrize(
    "changes",
    [
        {"number": 3},
        {"mountpoint": None},
        {"readonly": True},
        {"filesystem": "apfs"},
        {"disk": "other"},
        {"label": "VTOYEFI"},
    ],
)
def test_ineligible_data(drive, changes):
    assert not Inventory((replace(drive.volumes[0], **changes), drive.volumes[1])).detected


def test_label_alone_is_not_detection(drive):
    assert not Inventory((replace(drive.volumes[0], label="Ventoy"),)).detected


def test_multiple_drives_prompt(drive, root, monkeypatch):
    second = root / "second"
    second.mkdir()
    data, boot = drive.volumes
    inventory = Inventory(
        (
            *drive.volumes,
            replace(data, disk="other", mountpoint=second),
            replace(boot, disk="other"),
        )
    )
    monkeypatch.setattr(destinations, "scan_volumes", lambda: inventory)
    monkeypatch.setattr(destinations.os.path, "ismount", lambda p: p in {root, second})
    with pytest.raises(SafetyError, match="Multiple"):
        destinations.resolve_target(None)
    answers(monkeypatch, "2")
    assert destinations.resolve_target(None, interactive=True).root == second


def test_missing_drive_prompts_and_requires_confirmation(root, monkeypatch):
    monkeypatch.setattr(destinations.os.path, "ismount", lambda p: p == root)
    answers(monkeypatch, str(root), "2", str(root), "1")
    assert destinations.resolve_target(None, interactive=True).root == root


def test_ordinary_folder_rejected_and_cancel(root, monkeypatch, capsys):
    with pytest.raises(SafetyError, match="not on a detected"):
        destinations.resolve_target(root)
    answers(monkeypatch, str(root), "q")
    assert destinations.resolve_target(None, interactive=True) is None
    assert "not an ordinary folder" in capsys.readouterr().out
    assert destinations.resolve_target(root, mode="directory").ventoy is False
    assert list(root.iterdir()) == []


def test_stale_config_can_select_detected_drive(drive, root, monkeypatch):
    answers(monkeypatch, "1")
    assert destinations.resolve_target(root / "missing", interactive=True).root == root


def test_boot_partition_never_destination(drive, root, monkeypatch):
    boot_mount = root / "boot"
    boot_mount.mkdir()
    inventory = Inventory((drive.volumes[0], replace(drive.volumes[1], mountpoint=boot_mount)))
    monkeypatch.setattr(destinations, "scan_volumes", lambda: inventory)
    for mode in ("ventoy", "directory"):
        with pytest.raises(SafetyError, match="boot partition"):
            destinations.resolve_target(boot_mount, mode=mode)


def test_unplug_and_changed_device(drive, monkeypatch):
    target = destinations.resolve_target(None)
    with pytest.raises(SafetyError, match="changed"):
        replace(target, device_id=target.device_id + 1).check_mount()
    monkeypatch.setattr(destinations.os.path, "ismount", lambda p: False)
    with pytest.raises(SafetyError, match="no longer mounted"):
        target.check_mount()


def test_plan_rejects_nested_mount_and_fat_limit(drive, root, release, monkeypatch):
    target = destinations.resolve_target(None)
    folder = root / "ISO"
    folder.mkdir()
    item = PlannedDownload("example", release, folder / release.filename, Action.DOWNLOAD)
    target.validate_plan(Plan((item,)))
    large = replace(item, release=replace(release, size=4 * 1024**3))
    with pytest.raises(SafetyError, match="4 GiB"):
        replace(target, filesystem="vfat").validate_plan(Plan((large,)))
    monkeypatch.setattr(destinations.os.path, "ismount", lambda p: p in {root, folder})
    with pytest.raises(SafetyError, match="nested mount"):
        target.validate_plan(Plan((item,)))


def test_cli_refuses_hidden_plan_before_writes(drive, root, provider, monkeypatch, capsys):
    registry = Registry()
    registry.register(provider)
    monkeypatch.setattr(cli, "default_registry", lambda: registry)
    monkeypatch.setattr(cli.config, "load", Config)
    (root / ".ventoyignore").touch()
    assert cli.main(["update-images", "--only", "example", "--no-interactive"]) == 1
    assert ".ventoyignore" in capsys.readouterr().err
    assert sorted(p.name for p in root.iterdir()) == [".ventoyignore"]


def test_visibility_rechecked_after_confirmation(drive, root, provider, monkeypatch):
    registry = Registry()
    registry.register(provider)
    monkeypatch.setattr(cli, "default_registry", lambda: registry)
    monkeypatch.setattr(cli.config, "load", Config)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)

    def confirm(prompt):
        (root / ".ventoyignore").touch()
        return "y"

    monkeypatch.setattr("builtins.input", confirm)
    assert cli.main(["update-images", "--only", "example"]) == 1
    assert not (root / ".ventoy-library").exists()
    assert not (root / "ISO").exists()


def test_macos_inventory(root):
    listing = {
        "AllDisksAndPartitions": [
            {
                "DeviceIdentifier": "disk9",
                "Partitions": [{"DeviceIdentifier": "disk9s1"}, {"DeviceIdentifier": "disk9s2"}],
            }
        ]
    }
    details = {
        "disk9s1": {"FilesystemType": "ExFAT", "MountPoint": str(root), "VolumeName": "USB"},
        "disk9s2": {"FilesystemType": "msdos", "VolumeName": "VTOYEFI"},
    }
    inventory = volumes.macos_inventory(listing, details.__getitem__)
    assert inventory.detected[0].mountpoint == root
    assert inventory.volumes[1].mountpoint is None


def test_windows_inventory(root):
    inventory = volumes.windows_inventory(
        [
            dict(
                device="1:1",
                disk="1",
                number=1,
                label="USB",
                filesystem="ExFAT",
                mountpoint=str(root),
            ),
            dict(device="1:2", disk="1", number=2, label="VTOYEFI", filesystem="FAT32"),
        ]
    )
    assert inventory.detected[0].mountpoint == root


def test_linux_inventory_unmounted_boot_and_escaped_mount(root):
    sysfs, udev = root / "sys", root / "udev"
    sysfs.mkdir()
    udev.mkdir()
    for number, label, fs in [(1, "USB", "exfat"), (2, "VTOYEFI", "vfat")]:
        node = root / "devices" / "sdb" / f"sdb{number}"
        node.mkdir(parents=True)
        (node / "partition").write_text(str(number))
        (node / "dev").write_text(f"8:{number}")
        (sysfs / node.name).symlink_to(node, target_is_directory=True)
        (udev / f"b8:{number}").write_text(f"E:ID_FS_LABEL={label}\nE:ID_FS_TYPE={fs}\n")
    mountinfo = root / "mountinfo"
    mountinfo.write_text("10 1 8:1 / /media/My\\040USB rw - exfat /dev/sdb1 rw\n")
    inventory = volumes.linux_inventory(sysfs, udev, mountinfo)
    assert inventory.detected[0].mountpoint.as_posix() == "/media/My USB"
    mountinfo.write_text("10 1 8:1 /subtree /media/USB rw - exfat /dev/sdb1 rw\n")
    assert not volumes.linux_inventory(sysfs, udev, mountinfo).detected


def test_metadata_failure_is_graceful(monkeypatch):
    monkeypatch.setattr(volumes.sys, "platform", "darwin")
    monkeypatch.setattr(volumes, "command_output", lambda args: b"not plist")
    inventory = volumes.scan_volumes()
    assert not inventory.detected and inventory.warning


def test_detected_drive_imports_with_default_buffer(drive, root, provider, monkeypatch, capsys):
    registry = Registry()
    registry.register(provider)
    monkeypatch.setattr(cli, "default_registry", lambda: registry)
    monkeypatch.setattr(cli.config, "load", Config)
    source = root / "source.iso"
    source.write_bytes(b"abc")
    assert cli.main(["add", "--local", f"example={source}", "--no-interactive"]) == 0
    assert (root / "ISO/example-1.iso").read_bytes() == b"abc"
    output = capsys.readouterr().out
    assert "2.0 GiB" in output
    assert "Ventoy image visibility: OK" in output


def test_unplug_during_transfer_never_installs(drive, root, provider, monkeypatch):
    from ventoy_library.library import execute
    from ventoy_library.planner import build_plan
    from ventoy_library.state import StateStore

    target = destinations.resolve_target(None)
    plan = build_plan([provider], root, [], {}, lambda url: 3)

    class Interrupted:
        def fetch(self, release, source, root, part, update):
            part.parent.mkdir(parents=True)
            part.write_bytes(b"abc")
            monkeypatch.setattr(destinations.os.path, "ismount", lambda p: False)
            update(3)

    with pytest.raises(SafetyError, match="no longer mounted"):
        execute(plan, root, StateStore(root), Interrupted(), 0, target_guard=target)
    assert not (root / "ISO/example-1.iso").exists()
    assert not (root / ".ventoy-library/state.json").exists()


def test_destination_mode_saved_and_validated(root):
    from ventoy_library.config import load, set_value
    from ventoy_library.errors import LibraryError

    path = root / "config.json"
    assert set_value("destination_mode", "directory", path).destination_mode == "directory"
    assert load(path).safety_margin == 2 * 1024**3
    with pytest.raises(LibraryError, match="Destination mode"):
        set_value("destination_mode", "typo", path)
    assert load(path).destination_mode == "directory"
