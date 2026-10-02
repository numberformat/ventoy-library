"""Conservative, read-only checks for visibility in Ventoy's normal image menu."""

import json
import os
import re
from pathlib import Path, PurePosixPath

from .errors import SafetyError
from .safety import contained, open_regular

IMAGE_TYPES = {".iso": "ISO", ".img": "IMG"}
BOOT_MODES = ("legacy", "uefi", "ia32", "aa64", "mips")


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SafetyError(f"Duplicate key in ventoy.json: {key}")
        result[key] = value
    return result


def read_config(volume: Path) -> dict:
    path = contained(volume, "ventoy/ventoy.json")
    if not path.exists():
        return {}
    try:
        with os.fdopen(open_regular(path, os.O_RDONLY), "rb") as stream:
            data = stream.read(2 * 1024**2 + 1)
        if len(data) > 2 * 1024**2:
            raise SafetyError("ventoy.json exceeds the 2 MiB metadata limit.")
        config = json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_keys)
        if not isinstance(config, dict):
            raise ValueError("JSON root is not an object")
        return config
    except (ValueError, UnicodeError) as exc:
        raise SafetyError("Cannot validate image visibility: ventoy.json is malformed.") from exc


def path_setting(value: str, *, pattern: bool = False) -> PurePosixPath:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or "\\" in value
        or any(p in {".", ".."} for p in value.split("/"))
        or any(ord(c) < 32 or ord(c) > 126 or c.isspace() for c in value)
    ):
        raise SafetyError("Unsupported or unsafe path in ventoy.json; use absolute ASCII paths.")
    path = PurePosixPath(value)
    if "*" in str(path.parent) or (not pattern and "*" in value):
        raise SafetyError("Unsupported wildcard in a Ventoy directory path.")
    return path


def path_matches(pattern: str, image: str) -> bool:
    path_setting(pattern, pattern=True)
    # Ventoy's * matches exactly ONE filename character, not an arbitrary string.
    return re.fullmatch(re.escape(pattern).replace(r"\*", "[^/]"), image) is not None


def mode_value(config: dict, name: str, mode: str, default):
    return config.get(f"{name}_{mode}", config.get(name, default))


def control_options(config: dict, mode: str) -> dict[str, str]:
    control = mode_value(config, "control", mode, [])
    if not isinstance(control, list):
        raise SafetyError(f"Invalid control configuration for Ventoy {mode} mode.")
    options = {}
    for entry in control:
        if not isinstance(entry, dict):
            raise SafetyError("Ventoy control entries must be objects.")
        for key, value in entry.items():
            if key in options or not isinstance(value, str):
                raise SafetyError("Duplicate or non-string Ventoy control value.")
            options[key] = value
    return options


def image_list(config: dict, name: str, mode: str):
    value = mode_value(config, name, mode, None)
    if value is not None:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise SafetyError(f"Invalid Ventoy {name} for {mode} mode.")
        for path in value:
            path_setting(path, pattern=True)
    return value


def validate_image(volume: Path, target: Path, config: dict | None = None) -> None:
    """Reject a file hidden by any supported boot-mode profile; never change Ventoy settings."""
    try:
        relative = target.relative_to(volume)
    except ValueError as exc:
        raise SafetyError("Image destination is outside the Ventoy data partition.") from exc
    contained(volume, relative)
    kind = IMAGE_TYPES.get(target.suffix.lower())
    if kind is None:
        raise SafetyError(
            f"Cannot validate Ventoy visibility for {target.name}. "
            "This application currently validates uncompressed ISO/IMG images."
        )
    if target.name.lower() in {"ventoy_wimboot.img", "ventoy_vhdboot.img"}:
        raise SafetyError("Ventoy reserves this image filename for its boot plugins.")
    for parent in (target.parent, *target.parent.parents):
        if not parent.is_relative_to(volume):
            break
        ignored = parent / ".ventoyignore"
        if ignored.exists() or ignored.is_symlink():
            raise SafetyError(f"Ventoy will skip {target.name}: {ignored} exists.")
    image = "/" + relative.as_posix()
    config = read_config(volume) if config is None else config
    for mode in BOOT_MODES:
        options = control_options(config, mode)
        search_root = path_setting(options.get("VTOY_DEFAULT_SEARCH_ROOT", "/"))
        try:
            below = PurePosixPath(image).relative_to(search_root)
        except ValueError as exc:
            raise SafetyError(
                f"Ventoy {mode} searches {search_root}; {image} is outside it. "
                "Choose a destination inside that directory."
            ) from exc
        depth = options.get("VTOY_MAX_SEARCH_LEVEL", "max")
        if depth != "max":
            if not re.fullmatch(r"\d{1,6}", depth):
                raise SafetyError("Invalid VTOY_MAX_SEARCH_LEVEL in ventoy.json.")
            if len(below.parts) - 1 > int(depth):
                raise SafetyError(f"Ventoy {mode} search depth {depth} excludes {image}.")
        filtered = options.get(f"VTOY_FILE_FLT_{kind}", "0")
        if filtered not in {"0", "1"}:
            raise SafetyError(f"Invalid VTOY_FILE_FLT_{kind} in ventoy.json.")
        if filtered == "1":
            raise SafetyError(f"Ventoy {mode} filters {kind} images; refusing {image}.")
        allow = image_list(config, "image_list", mode)
        deny = image_list(config, "image_blacklist", mode)
        if allow is not None and deny is not None:
            raise SafetyError("Ventoy image_list and image_blacklist cannot both be active.")
        if allow is not None and not any(path_matches(p, image) for p in allow):
            raise SafetyError(f"{image} is not in Ventoy's {mode} image_list.")
        if deny is not None and any(path_matches(p, image) for p in deny):
            raise SafetyError(f"{image} is excluded by Ventoy's {mode} image_blacklist.")
