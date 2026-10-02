import json

import pytest

from ventoy_library.errors import SafetyError
from ventoy_library.ventoy import path_matches, read_config, validate_image


def control(**options):
    return {"control": [{k: v} for k, v in options.items()]}


def test_default_and_custom_search_root(root):
    target = root / "ISO/rescue/example/example.iso"
    validate_image(root, target)
    validate_image(
        root, target, control(VTOY_DEFAULT_SEARCH_ROOT="/ISO", VTOY_MAX_SEARCH_LEVEL="2")
    )
    with pytest.raises(SafetyError, match="outside"):
        validate_image(root, target, control(VTOY_DEFAULT_SEARCH_ROOT="/Images"))
    with pytest.raises(SafetyError, match="depth"):
        validate_image(root, target, control(VTOY_MAX_SEARCH_LEVEL="2"))


@pytest.mark.parametrize("folder", ["", "ISO", "ISO/rescue", "ISO/rescue/example"])
def test_ignored_ancestor(root, folder):
    parent = root / folder
    parent.mkdir(parents=True, exist_ok=True)
    (parent / ".ventoyignore").touch()
    with pytest.raises(SafetyError, match="will skip"):
        validate_image(root, root / "ISO/rescue/example/example.iso")


@pytest.mark.parametrize(
    "config",
    [
        control(VTOY_FILE_FLT_ISO="1"),
        {"control_uefi": [{"VTOY_FILE_FLT_ISO": "1"}]},
        {"image_list": ["/different.iso"]},
        {"image_blacklist": ["/image.iso"]},
        {"image_blacklist_uefi": ["/image.iso"]},
        {"image_list": ["/image.iso"], "image_blacklist": []},
        control(VTOY_MAX_SEARCH_LEVEL="-1"),
        control(VTOY_FILE_FLT_ISO="yes"),
        {"control": "broken"},
        {"control": [{"VTOY_FILE_FLT_ISO": 1}]},
        {"image_list": "broken"},
    ],
)
def test_hidden_or_malformed_config(root, config):
    with pytest.raises(SafetyError):
        validate_image(root, root / "image.iso", config)


def test_mode_override_and_filename_wildcard(root):
    validate_image(root, root / "image.iso", {"image_list": ["/imag*.iso"]})
    assert path_matches("/imag*.iso", "/image.iso")
    assert not path_matches("/imag*.iso", "/images.iso")
    with pytest.raises(SafetyError):
        path_matches("/*/image.iso", "/ISO/image.iso")
    with pytest.raises(SafetyError):
        validate_image(
            root,
            root / "image.iso",
            {"image_list": ["/image.iso"], "image_list_uefi": ["/other.iso"]},
        )


@pytest.mark.parametrize("name", ["image.img.gz", "image.zip", "image.wim", "ventoy_wimboot.img"])
def test_unhandled_artifacts_are_refused(root, name):
    with pytest.raises(SafetyError):
        validate_image(root, root / name)


@pytest.mark.parametrize("text", ["[]", "{", '{"control":[],"control":[]}'])
def test_bad_json_fails_closed(root, text):
    (root / "ventoy").mkdir()
    (root / "ventoy/ventoy.json").write_text(text)
    with pytest.raises(SafetyError):
        read_config(root)


def test_read_configuration_and_refuse_symlink(root):
    (root / "ventoy").mkdir()
    config = control(VTOY_FILE_FLT_IMG="1")
    (root / "ventoy/ventoy.json").write_text(json.dumps(config))
    assert read_config(root) == config
    with pytest.raises(SafetyError, match="filters IMG"):
        validate_image(root, root / "disk.img")
    (root / "ISO").symlink_to(root / "ventoy", target_is_directory=True)
    with pytest.raises(SafetyError):
        validate_image(root, root / "ISO/test.iso")
