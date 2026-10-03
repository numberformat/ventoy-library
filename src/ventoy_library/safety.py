"""Conservative path boundaries for a trusted, non-concurrently-mutated filesystem."""

import os
import re
from pathlib import Path

from .errors import SafetyError
from .metadata import STATE_DIRECTORY


def component(value: str) -> str:
    # Portable names only, including rejection of Windows device names and path separators.
    if (
        not isinstance(value, str)
        or len(value) > 200
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", value)
        or value.endswith(".")
        or ".." in value
        or value.split(".")[0].upper()
        in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
    ):
        raise SafetyError(f"Unsafe filename or path component: {value!r}")
    return value


def destination(value: str | Path) -> Path:
    if not str(value).strip():
        raise SafetyError("Destination must not be empty.")
    path = Path(value).expanduser().absolute()
    for node in (path, *path.parents):
        if node.is_symlink():
            raise SafetyError(f"Symlink destinations are not supported: {node}")
    path = path.resolve()
    system_root = path == Path(path.anchor)
    if os.name == "nt" and path.drive.lower() != os.environ.get("SystemDrive", "C:").lower():
        system_root = False
    if system_root or not path.is_dir():
        raise SafetyError("Destination must be an existing directory, not a filesystem root.")
    return path


def contained(root: Path, relative: str | Path) -> Path:
    root = destination(root)
    rel = Path(relative)
    if rel.is_absolute() or not rel.parts or any(p in {".", ".."} for p in rel.parts):
        raise SafetyError(f"Unsafe relative path: {relative}")
    path = root
    for part in rel.parts:
        if part != STATE_DIRECTORY:
            component(part)
        path /= part
        if path.is_symlink():
            raise SafetyError(f"Refusing symlink: {path}")
        if path.exists() and not (path.is_dir() or path.is_file()):
            raise SafetyError(f"Refusing special file: {path}")
    if not path.resolve().is_relative_to(root):
        raise SafetyError("Path escapes destination.")
    return path


def image_path(root: Path, filename: str) -> Path:
    return contained(root, Path("ISO") / component(filename))


def open_regular(path: Path, flags: int):
    """Reject symlinks at open time too (where O_NOFOLLOW is available)."""
    fd = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), 0o600)
    import stat

    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise SafetyError(f"Not a regular file: {path}")
    return fd
