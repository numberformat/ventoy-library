# Changelog

Notable changes follow a simple Keep a Changelog style and Semantic Versioning.

## [Unreleased]

### Changed
- Ventoy mode is now the default; ordinary folders require explicit `--directory` mode.
- `list` now displays the entire numbered catalog; `status` displays managed files.
- `config set safety_margin` now accepts GiB, including fractional amounts;
  saved configuration continues to use bytes.

### Added
- Packaged YAML release catalog, loaded automatically, with a reusable ChatGPT web
  research prompt and explicit human approval before a snapshot becomes a download source.
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

## [0.1.0] - Not released

Initial foundation release planned; no GitHub release has been published by this implementation.
