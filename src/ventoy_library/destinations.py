"""Resolve library locations and enforce mounted Ventoy boundaries before acquisition."""

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import LibraryError, SafetyError
from .models import Action, Plan
from .safety import destination
from .ventoy import read_config, validate_image
from .volumes import SUPPORTED_FILESYSTEMS, Inventory, Volume, scan_volumes, ventoy_boot_partition


def mounted_root(path: Path) -> Path:
    for parent in (path, *path.parents):
        if os.path.ismount(parent):
            return parent
    raise SafetyError("Could not locate the mounted filesystem containing the destination.")


def containing_volume(path: Path, volumes: tuple[Volume, ...]) -> Volume | None:
    matches = [v for v in volumes if v.mountpoint is not None and path.is_relative_to(v.mountpoint)]
    return max(matches, key=lambda v: len(v.mountpoint.parts), default=None)


def current_ventoy_root(inventory: Inventory | None = None) -> Path | None:
    """Return the detected Ventoy data-partition root containing the current directory."""
    inventory = inventory if inventory is not None else scan_volumes()
    try:
        current = Path.cwd().resolve(strict=True)
    except OSError:
        return None
    volume = containing_volume(current, inventory.detected)
    return volume.mountpoint if volume else None


def reject_boot_partition(path: Path, inventory: Inventory) -> None:
    volume = containing_volume(path, inventory.volumes)
    boot_disks = {v.disk for v in inventory.volumes if ventoy_boot_partition(v)}
    if (
        volume
        and (
            volume.label.upper() == "VTOYEFI" or (volume.number == 2 and volume.disk in boot_disks)
        )
    ) or any(p.name.upper() == "VTOYEFI" for p in (path, *path.parents)):
        raise SafetyError(
            "VTOYEFI is Ventoy's boot partition; images belong on its data partition."
        )


@dataclass(frozen=True)
class Target:
    root: Path
    volume_root: Path
    device_id: int
    ventoy: bool
    filesystem: str = ""

    def check_mount(self) -> None:
        destination(self.root)
        if self.root.stat().st_dev != self.device_id:
            raise SafetyError("Destination filesystem changed after selection; refusing writes.")
        if not self.ventoy:
            return
        if not os.path.ismount(self.volume_root):
            raise SafetyError("Destination volume is no longer mounted; refusing writes.")
        if self.volume_root.stat().st_dev != self.device_id:
            raise SafetyError("Destination volume changed after selection; refusing writes.")
        if mounted_root(self.root) != self.volume_root:
            raise SafetyError("Library directory crosses a nested mount boundary.")

    def validate_plan(self, plan: Plan) -> None:
        self.check_mount()
        config = read_config(self.volume_root) if self.ventoy else None
        for item in plan.items:
            if item.action not in {
                Action.DOWNLOAD, Action.UPDATE, Action.CURRENT, Action.RELOCATE, Action.ADOPT
            }:
                continue
            target = item.destination
            if not target.is_relative_to(self.root):
                raise SafetyError("Planned file escapes the library destination.")
            # Existing intermediate mounts must not redirect an image to another volume.
            parent = target.parent
            while not parent.exists():
                parent = parent.parent
            if parent.stat().st_dev != self.device_id or (
                self.ventoy and mounted_root(parent) != self.volume_root
            ):
                raise SafetyError("Planned image crosses a nested mount boundary.")
            if self.ventoy:
                validate_image(self.volume_root, target, config)
            if (
                self.filesystem in {"vfat", "msdos", "fat", "fat16", "fat32"}
                and item.release.size is not None
                and item.release.size >= 4 * 1024**3
            ):
                raise SafetyError("This FAT filesystem cannot store an image of 4 GiB or larger.")


def make_target(path: Path, volume: Volume | None, *, ventoy: bool) -> Target:
    root = destination(path)
    mount = volume.mountpoint if volume and volume.mountpoint else mounted_root(root)
    if ventoy and mount == Path(mount.anchor):
        # Windows data-drive roots are mountpoints too; the system drive remains forbidden.
        if os.name != "nt" or str(mount).lower().startswith(
            os.environ.get("SystemDrive", "C:").lower()
        ):
            raise SafetyError("The system filesystem cannot be used as a Ventoy data partition.")
    if volume and (volume.readonly or (ventoy and volume.filesystem not in SUPPORTED_FILESYSTEMS)):
        raise SafetyError("Destination filesystem is read-only or unsupported by Ventoy.")
    if not os.access(root, os.W_OK):
        raise SafetyError("Destination is not writable.")
    result = Target(root, mount, root.stat().st_dev, ventoy, volume.filesystem if volume else "")
    result.check_mount()
    return result


def resolve_target(
    chosen: str | Path | None,
    *,
    mode: str = "ventoy",
    interactive: bool = False,
    prefer_current_directory: bool = False,
) -> Target | None:
    """No persistent writes; q cancels. Only an explicit mode permits ordinary folders."""
    inventory = scan_volumes()
    if mode == "directory":
        if not chosen:
            raise LibraryError(
                "Directory mode needs --destination PATH or a configured destination."
            )
        root = destination(chosen)
        reject_boot_partition(root, inventory)
        return make_target(root, containing_volume(root, inventory.volumes), ventoy=False)
    if inventory.warning:
        print(inventory.warning)
    detected = inventory.detected
    if prefer_current_directory:
        current_root = current_ventoy_root(inventory)
        if current_root is not None:
            volume = containing_volume(current_root, detected)
            print(f"Using Ventoy data partition containing current directory: {current_root}")
            return make_target(current_root, volume, ventoy=True)
    if chosen:
        try:
            root = destination(chosen)
            reject_boot_partition(root, inventory)
            volume = containing_volume(root, detected)
            if volume:
                return make_target(root, volume, ventoy=True)
        except (LibraryError, OSError) as exc:
            if not interactive and not prefer_current_directory:
                raise
            label = "Saved" if prefer_current_directory else "Configured"
            print(f"{label} destination unavailable: {exc}")
        if prefer_current_directory and len(detected) == 1:
            volume = detected[0]
            print(f"Using detected Ventoy data partition: {volume.mountpoint}")
            return make_target(volume.mountpoint, volume, ventoy=True)
        if not interactive:
            message = (
                "Multiple Ventoy data partitions found"
                if len(detected) > 1 and prefer_current_directory
                else "Destination is not on a detected Ventoy data partition"
            )
            raise SafetyError(f"{message}. Specify --destination PATH, or run interactively.")
        print(f"Could not identify {chosen} as a Ventoy data partition.")
    elif len(detected) == 1:
        volume = detected[0]
        print(f"Detected Ventoy data partition: {volume.mountpoint}")
        return make_target(volume.mountpoint, volume, ventoy=True)
    if not interactive:
        message = (
            "Multiple Ventoy data partitions found" if detected else "No mounted Ventoy detected"
        )
        raise SafetyError(f"{message}. Specify --destination PATH, or run interactively.")
    if not detected:
        print(
            "No mounted Ventoy data partition was detected. Mount the drive, then enter its path."
        )
    while True:
        for number, volume in enumerate(detected, 1):
            print(f"{number}. {volume.mountpoint} ({volume.label or 'unnamed data partition'})")
        value = input(
            "Choose a drive number or enter its mounted data-partition path (q = cancel): "
        )
        if value.strip().lower() in {"q", "quit", "cancel"}:
            return None
        try:
            if value.strip().isdecimal():
                index = int(value.strip())
                if not 1 <= index <= len(detected):
                    raise SafetyError("Choose one of the listed drive numbers.")
                volume = detected[index - 1]
                return make_target(volume.mountpoint, volume, ventoy=True)
            root = destination(value.strip())
            # Refresh after the user mounts a drive or supplies a path.
            inventory = scan_volumes()
            reject_boot_partition(root, inventory)
            volume = containing_volume(root, inventory.detected)
            if volume:
                return make_target(root, volume, ventoy=True)
            volume = containing_volume(root, inventory.volumes)
            if volume and volume.number != 1:
                raise SafetyError("Ventoy images must be on the first (data) partition.")
            # Inconclusive detection requires a mount root and explicit user confirmation.
            if not os.path.ismount(root):
                raise SafetyError("Enter the mounted data-partition root, not an ordinary folder.")
            target = make_target(root, volume, ventoy=True)
            print(f"Ventoy installation could not be verified on {root}.")
            print("1. I confirm this is the mounted Ventoy DATA partition\n2. Choose another path")
            if input("Choice [2]: ").strip() == "1":
                return target
        except (LibraryError, OSError) as exc:
            print(f"{exc} Please try again.")
