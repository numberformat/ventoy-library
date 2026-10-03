"""Read-only mounted-volume inventory. No raw device opens, mounts or disk writes."""

import json
import os
import plistlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .errors import LibraryError

SUPPORTED_FILESYSTEMS = {
    "exfat",
    "ntfs",
    "ntfs3",
    "vfat",
    "msdos",
    "fat",
    "fat16",
    "fat32",
    "ext2",
    "ext3",
    "ext4",
    "xfs",
    "udf",
}
FAT_FILESYSTEMS = {"vfat", "msdos", "fat", "fat16", "fat32"}


@dataclass(frozen=True)
class Volume:
    device: str
    disk: str
    number: int
    label: str
    filesystem: str
    mountpoint: Path | None
    readonly: bool = False
    partition_type: str = ""
    partition_scheme: str = ""
    size: int | None = None
    external: bool = False


def ventoy_boot_partition(volume: Volume) -> bool:
    """Recognize the labelled EFI partition or macOS's unlabeled MBR view of it."""
    if volume.number != 2:
        return False
    if volume.label.upper() == "VTOYEFI" and volume.filesystem in FAT_FILESYSTEMS:
        return True
    return (
        volume.partition_scheme == "FDisk_partition_scheme"
        and volume.partition_type.upper() == "0XEF"
        and volume.size == 32 * 1024**2
        and volume.external
    )


@dataclass(frozen=True)
class Inventory:
    volumes: tuple[Volume, ...] = ()
    warning: str | None = None

    @property
    def detected(self) -> tuple[Volume, ...]:
        boot_disks = {v.disk for v in self.volumes if ventoy_boot_partition(v)}
        return tuple(
            v
            for v in self.volumes
            if v.disk in boot_disks
            and v.number == 1
            and v.mountpoint is not None
            and not v.readonly
            and v.filesystem in SUPPORTED_FILESYSTEMS
            and v.label.upper() != "VTOYEFI"
        )


def command_output(command: list[str]) -> bytes:
    try:
        result = subprocess.run(command, check=True, capture_output=True, timeout=15)
        return result.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise LibraryError(
            "Mounted-volume metadata is unavailable from the operating system."
        ) from exc


def macos_inventory(data: dict, info) -> Inventory:
    volumes = []
    for disk in data["AllDisksAndPartitions"]:
        disk_id = disk["DeviceIdentifier"]
        for partition in disk.get("Partitions", []):
            device = partition["DeviceIdentifier"]
            match = re.fullmatch(re.escape(disk_id) + r"s(\d+)", device)
            if not match:
                continue
            details = info(device)
            mount = details.get("MountPoint") or partition.get("MountPoint")
            fs = details.get("FilesystemType", "").lower()
            volumes.append(
                Volume(
                    device,
                    disk_id,
                    int(match[1]),
                    details.get("VolumeName", partition.get("VolumeName", "")),
                    fs,
                    Path(mount) if mount else None,
                    bool(
                        details.get("ReadOnlyVolume", False) or details.get("ReadOnlyMedia", False)
                    ),
                    details.get("Content", partition.get("Content", "")),
                    disk.get("Content", ""),
                    details.get("Size", partition.get("Size")),
                    bool(details.get("RemovableMediaOrExternalDevice", False)),
                )
            )
    return Inventory(tuple(volumes))


def _unescape_mount(value: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), value)


def linux_inventory(
    sysfs: Path = Path("/sys/class/block"),
    udev: Path = Path("/run/udev/data"),
    mountinfo: Path = Path("/proc/self/mountinfo"),
) -> Inventory:
    mounts = {}
    for line in mountinfo.read_text().splitlines():
        fields = line.split()
        separator = fields.index("-")
        # Only a mount of the full filesystem, not a bind-mounted subtree.
        if fields[3] == "/":
            mounts.setdefault(fields[2], []).append(
                (
                    Path(_unescape_mount(fields[4])),
                    fields[separator + 1],
                    "ro" in fields[5].split(","),
                )
            )
    volumes = []
    for node in sorted(sysfs.iterdir()):
        if not (node / "partition").is_file():
            continue
        number = int((node / "partition").read_text().strip())
        major_minor = (node / "dev").read_text().strip()
        metadata = {}
        try:
            for line in (udev / f"b{major_minor}").read_text().splitlines():
                if line.startswith("E:") and "=" in line:
                    key, value = line[2:].split("=", 1)
                    metadata[key] = value
        except FileNotFoundError:
            pass
        fs = metadata.get("ID_FS_TYPE", "").lower()
        mounted = mounts.get(major_minor, [(None, fs, False)])
        for mount, mounted_fs, readonly in mounted:
            volumes.append(
                Volume(
                    str(node),
                    str(node.resolve().parent),
                    number,
                    metadata.get("ID_FS_LABEL", ""),
                    fs or mounted_fs,
                    mount,
                    readonly,
                )
            )
    return Inventory(tuple(volumes))


WINDOWS_QUERY = r"""
$ErrorActionPreference = 'Stop'
$rows = @(Get-Partition | ForEach-Object {
    $p = $_
    $v = $p | Get-Volume -ErrorAction SilentlyContinue
    if ($v) {
        [PSCustomObject]@{
            device = $p.DiskNumber.ToString() + ':' + $p.PartitionNumber.ToString()
            disk = $p.DiskNumber.ToString()
            number = $p.PartitionNumber
            label = $v.FileSystemLabel
            filesystem = $v.FileSystemType.ToString().ToLower()
            mountpoint = $(if ($v.DriveLetter) { $v.DriveLetter.ToString() + ':\' } else { $null })
            readonly = $p.IsReadOnly
        }
    }
})
ConvertTo-Json -InputObject $rows -Compress
"""


def windows_inventory(rows: list[dict]) -> Inventory:
    return Inventory(
        tuple(
            Volume(
                r["device"],
                r["disk"],
                int(r["number"]),
                r.get("label") or "",
                r["filesystem"].lower(),
                Path(r["mountpoint"]) if r.get("mountpoint") else None,
                bool(r.get("readonly", False)),
            )
            for r in rows
        )
    )


def scan_volumes() -> Inventory:
    try:
        if sys.platform == "darwin":
            data = plistlib.loads(command_output(["/usr/sbin/diskutil", "list", "-plist"]))
            return macos_inventory(
                data,
                lambda device: plistlib.loads(
                    command_output(["/usr/sbin/diskutil", "info", "-plist", device])
                ),
            )
        if sys.platform.startswith("linux"):
            return linux_inventory()
        if os.name == "nt":
            rows = json.loads(
                command_output(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", WINDOWS_QUERY]
                )
            )
            return windows_inventory(rows)
        return Inventory(warning="Automatic Ventoy detection is unavailable on this platform.")
    except (LibraryError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return Inventory(warning=f"Could not inspect mounted volumes: {exc}")
