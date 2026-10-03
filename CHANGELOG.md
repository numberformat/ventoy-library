# Changelog

Notable changes follow a simple Keep a Changelog style and Semantic Versioning.

## [Unreleased]

## [0.1.0] - 2026-10-03

### Changed
- New images are saved directly in `ISO/`; selected, tracked images in the older nested layout are migrated there.
- Existing top-level images require an upstream checksum match before adoption or removal of a tracked nested duplicate.
- macOS Ventoy detection now recognizes the unlabeled 32 MiB EFI partition shown
  by `diskutil` on some drives, allowing current-directory selection to work.
- Ventoy commands use the detected data partition containing the current directory
  before considering a saved destination, then scan mounted partitions before prompting.
- The normal image catalog and chooser now show only links that pass a HEAD check;
  results are cached for three days in the user's `.noami.us/ventoy-library` folder.
- Fedora's candidate snapshot now uses the direct HTTPS link published on its official
  Workstation download page through Fedora's mirror selector.
- Kali discovery now explains when the official stable live image is available only
  as a torrent and refuses to select an older or different image.
- Download progress now prints one combined status line when each file starts,
  about every three seconds during transfer, and when it completes.
- Ventoy mode is now the default; ordinary folders require explicit `--directory` mode.
- `list` displays checked catalog links; `status` displays managed files.
- `config set safety_margin` now accepts GiB, including fractional amounts;
  saved configuration continues to use bytes.
- The USB-resident installer script now installs the latest published release wheel
  through NOAMi Installer, without requiring Git or a preinstalled pipx.

### Added
- A tag-triggered GitHub Actions workflow builds one wheel and attaches it to a
  published release for NOAMi Installer.
- `check --downloads` probes the full catalog, including cataloged manual package URLs,
  with HEAD requests; `--url` and `--exclude` handle missing links and exclusions.
- Runtime discovery for Alpine, Debian, GParted, Clonezilla, Rescuezilla, Kali,
  Tails and FreeBSD, replacing their bundled release snapshots.
- Packaged YAML release catalog, loaded automatically, with a reusable research prompt.
- Read-only mounted Ventoy detection, numeric drive selection and interactive path fallback.
- Preflight checks for Ventoy search rules, hidden images, FAT file limits and mount changes.
- Documentation of the automatic 2 GiB safety buffer and optional overrides.
- A 24-image catalog with numeric multi-selection, ranges, and an all-images choice.
- Interactive `add` and `update-images` selection plus `--select` and `--all` flags.
- Automatic Arch, SystemRescue, Ubuntu Server LTS and Ubuntu Desktop LTS discovery,
  using official release metadata, SHA256 manifests and exact byte sizes.
- Numbered local-file/URL/skip choices for manual entries, resolved before storage checks.
- Phase 1 Python 3.11+ package, CLI, per-user configuration and provider protocol/registry.
- Preflight storage planning, byte progress, streaming acquisition and checksum verification.
- Defensive file boundaries, atomic JSON state, previous-state backup and writer locking.
- Stable GitHub application checks and guarded pipx self-update.
- Mocked core tests, Linux/macOS CI, public documentation and MIT license.

### Pending
- Phase 3: remaining requested upstream providers and interactive failure fallback.
