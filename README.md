# ventoy-library

Safely manage bootable operating-system, rescue, diagnostic, security, networking,
and server images on a Ventoy data partition **or any ordinary directory**.
This independent project is not affiliated with Ventoy or any supported operating-system project.
It never installs or updates Ventoy, formats a drive, or accesses raw block devices.

**Status: version 0.1.0 (unreleased).** Browse a numbered catalog of 24 images,
choose a few or all, then review the complete storage plan before downloading.
Arch Linux, SystemRescue, Ubuntu Server LTS and Ubuntu Desktop LTS have automatic
release discovery and SHA256 verification. Other entries accept a user-supplied
local image or URL by default; candidate YAML release snapshots can also supply
download URLs for them.
See the [project status and roadmap](docs/roadmap.md) for completed milestones and
the next development steps.
For periodic manual research, use the [ChatGPT web research prompt](docs/release-refresh-prompt.md)
to produce a sourced YAML snapshot of current official image URLs. Verify each candidate
entry before publishing it; the four built-in providers already discover releases at runtime.

## Features and scope

Implemented core capabilities:

- Full numbered image catalog, multi-selection, ranges, and an all-images choice.
- Latest stable release discovery for four automatic providers.
- Bundled YAML release catalog for periodically refreshed image URLs.
- Complete-plan storage capacity checking and total download-size calculation.
- Byte-based overall and per-file progress; unknown totals never produce an exact percentage.
- Streamed downloads with bounded transient retries and checksum-backed Range resume.
- SHA256/SHA512 verification and explicit `unverified` status when no checksum exists.
- Verified installation before old-image removal; `--keep-old` retention.
- Local-file and alternate-URL acquisition primitives, preserving upstream checksums.
- Per-user configuration, destination-local atomic JSON state, backup recovery and writer lock.
- pipx installation and stable GitHub application self-update, separate from image updates.
- Extensible provider architecture, with no OS naming rules in the core.

Manual catalog entries offer numbered local-file, direct-URL, and skip choices before
planning. Transfer-time fallback and continuation after transfer failures remain future
work. A transfer failure stops safely, preserving previous images; rerunning can resume
recognized checksum-backed partials.

## Requirements and installation

Python 3.11+, pipx, and Git (for installation from this Git repository).
Install pipx using your platform's package manager or follow the
[official pipx installation guide](https://pipx.pypa.io/stable/installation/).
Run `pipx ensurepath` if its executable directory is not on your PATH.

```bash
pipx install "git+https://github.com/numberformat/ventoy-library.git"
ventoy-library --help
ventoy-library --version
```

Repository installation becomes available after the project is pushed to GitHub.
For a local checkout: `pipx install .`. The application also supports
`python -m ventoy_library` within its Python environment.

## Application updates

```bash
ventoy-library --check-update
ventoy-library --update
# Explicit unattended authorization:
ventoy-library --update --yes
```

The check reads GitHub's releases API and compares versions using `packaging`.
Drafts and prereleases are excluded. If there are no published releases, stable
Semantic Versioning tags are considered. An empty repository reports no release;
network errors and unavailable repositories produce useful errors and exit nonzero.

Self-update requires a positively identified, unsuffixed, unpinned pipx Git
installation. Editable/development, local-path and other installations are rejected;
update development checkouts yourself with Git. No automatic `git pull` is run.

Plain `pipx upgrade ventoy-library` retains its recorded source, including a pinned
Git tag. Self-update instead installs the checked stable tag explicitly through pipx:

```bash
# Example only: substitute an existing stable release tag.
pipx install --force "git+https://github.com/numberformat/ventoy-library.git@v0.1.0"
```

This uses pipx's supported force-install mechanism and avoids updating to an
unreleased default-branch commit. It requires confirmation unless `--yes` is passed.
The application exits after pipx returns. See [research notes](docs/self-update.md).

## Configure and inspect a library

Ventoy mode is the default. With no saved destination, the application detects mounted
Ventoy data partitions. One detected drive is selected automatically; multiple drives
produce a numbered choice. If detection fails, interactive commands ask for the
mounted data-partition path. An inconclusive installation requires explicit user
confirmation. Noninteractive commands fail rather than guess.

```bash
ventoy-library list
ventoy-library add
# Optional: remember a particular mounted destination
ventoy-library config set destination /Volumes/Ventoy
ventoy-library status
ventoy-library check
ventoy-library update-images --dry-run
```

Detection uses operating-system partition metadata, including the sibling `VTOYEFI`
boot partition; a folder or volume named "Ventoy" alone is insufficient. The boot
partition is never an image destination. Destinations must already exist and be mounted.
Before acquisition, the application checks each image against Ventoy's search root,
search depth, `.ventoyignore`, file-type filters, and image lists, including boot-mode
overrides. Hidden images are refused with an explanation; Ventoy settings are not changed.
Currently these checks accept uncompressed ISO/IMG artifacts. See
[destination detection and visibility](docs/destinations.md) for limits and platform details.

The **safety buffer defaults to 2 GiB; you do not need to specify it**. Downloads are
allowed only when their full temporary size fits while leaving this reserve free.
It provides headroom for filesystem overhead, state updates, and other writes; it
cannot prevent another application from filling the drive. Old images stay in place
until replacement succeeds, so their potential cleanup is not counted as free space.

```bash
# Optional override in GiB (fractional values such as 0.5 are accepted)
ventoy-library config set safety_margin 2
ventoy-library config show
```

`config set safety_margin` accepts GiB (1 GiB = 1,073,741,824 bytes). Configuration
storage and `config show` retain byte values. Fractional amounts are rounded up to
the next whole byte. A value of `0` disables the extra reserve, but not capacity checks.

Ordinary folders remain supported through **explicit directory mode**:

```bash
ventoy-library add --directory --destination /path/to/existing/library
# Or persist this preference:
ventoy-library config set destination_mode directory
ventoy-library config set destination /path/to/existing/library
# Return to Ventoy mode:
ventoy-library config set destination_mode ventoy
```

Directory mode does not promise that Ventoy can find the images. `--ventoy` and
`--directory` override the saved mode; `--destination PATH` overrides the saved path.
Previously configured ordinary folders now require explicit directory mode.
Configuration follows platform per-user conventions, outside the installed package.
`list` shows the full numbered catalog offline, even without a mounted drive; with a
configured destination it also shows installed versions. `status` lists managed files
and storage. `check` queries providers. `check` and `--dry-run` never write configuration,
state, locks or partial files.

## Choose and add images

```bash
ventoy-library list
ventoy-library add
```

`add` displays the full scrollable catalog with numbers. Enter, for example,
`1,8,20,24` for Arch, SystemRescue, Ubuntu Server and Ubuntu Desktop; ranges such as
`1-3,9` also work. Enter **0** (or `all`) for every image, or `q` to cancel.
Invalid input is explained and prompted again. Nothing downloads until the selected
images have been planned, available space checked, and the plan confirmed.

```bash
# Numeric choices without typing project names:
ventoy-library add --select 1,8,20,24
ventoy-library add --all
ventoy-library add --select 20,24 --dry-run
ventoy-library add --select 1,8,20,24 --no-interactive

# update-images supports the same chooser and flags:
ventoy-library update-images
ventoy-library update-images --only systemrescue
ventoy-library update-images --select 1,9 --keep-old
ventoy-library check --select 20,24
```

Catalog numbers are stable; new entries are appended. `--select`, `--all` and `--only`
are mutually exclusive. `--only` can be repeated. Unattended downloads require an
explicit selection or `--local` inputs; `--no-interactive` skips prompts but never
bypasses storage or checksum checks. `check` and dry runs default to all entries
when no selection is specified. `--update` always updates the application, never images.

## Manual images

For each selected manual entry, the interactive chooser offers:

```text
1. Provide local file
2. Provide direct download URL
3. Skip
```

Maintainers can make a manually researched URL a selectable download source by
following the [YAML refresh workflow](docs/release-refresh-prompt.md) and shipping
an updated `releases.yaml` in the application package. Users receive candidate
entries automatically when they install or upgrade. These snapshots participate
in the normal size, storage, download and checksum checks; they need a new
package release when upstream publishes newer versions.

Use official upstream downloads and choose the stable bootable artifact for the
listed architecture. The application does not infer the release version or an
authoritative checksum for manual catalog entries. It records `user-supplied` and
**UNVERIFIED**; architecture and bootability are not validated. It copies/downloads
the supplied artifact as-is, without decompressing it.

```bash
# Both provider IDs and catalog numbers are supported:
ventoy-library add --local "hirens=~/Downloads/HBCD_PE_x64.iso"
ventoy-library add --select 13 --local "13=~/Downloads/HBCD_PE_x64.iso" --no-interactive
ventoy-library add --local "13=https://example.com/HBCD_PE_x64.iso" --dry-run
```

With `--local` and no other selection, only the named images are selected. Repeat
`--local` for multiple inputs. An override for an automatic provider retains its
discovered checksum and size and requires successful release discovery.

All manual sources are collected **before** the combined space check. Entries
skipped by the user are excluded. Unresolved manual entries in noninteractive mode
or dry runs are clearly reported, excluded from download totals, and cause a nonzero
exit code. Available automatic entries may still be downloaded after a successful
space check. A URL without a reliable size blocks all planned transfers.

Dry runs show actions, installed/available versions, filenames, source URLs, expected
sizes, full temporary storage requirements, safety margin, and old paths eligible
for removal after success. No image is transferred until every selected provider
has been queried and the complete executable plan passes its space check.

## Image catalog and provider support

The table describes the built-in registry. Manual catalog entries can also use a
candidate YAML entries supply release snapshots without live discovery. Manual entries
remain available for user-supplied files or URLs.
Official-source research and metadata fixtures for automatic providers are documented in
[provider research](docs/providers.md).

| # | Project | Category | Architecture | Runtime discovery | Catalog entry | Acquisition | Notes |
|---|---|---|---|---|---|---|---|
| 1 | Arch Linux | desktop | x86_64 | Yes | builtin | Automatic | Stable ISO |
| 2 | Alpine Linux | desktop | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 3 | Fedora Workstation | desktop | x86_64 | No | candidate | Manual source | Catalog URL unavailable |
| 4 | Debian Live | desktop | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 5 | Linux Mint | desktop | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 6 | Knoppix | desktop | x86_64 | No | candidate | Manual source | Catalog URL unavailable |
| 7 | Tiny Core Linux | desktop | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 8 | SystemRescue | rescue | x86_64 | Yes | builtin | Automatic | Stable ISO |
| 9 | GParted Live | rescue | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 10 | Clonezilla Live | rescue | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 11 | Rescuezilla | rescue | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 12 | Hiren's BootCD PE | rescue | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 13 | Memtest86+ | rescue | x86_64 | No | manual | Manual source | Archive needs special handling |
| 14 | Kali Linux | security | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 15 | Parrot Security | security | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 16 | Tails | security | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 17 | OPNsense | network | x86_64 | No | manual | Manual source | Compressed ISO needs special handling |
| 18 | OpenWrt x86-64 | network | x86_64 | No | manual | Manual source | Compressed disk image needs special handling |
| 19 | OpenMediaVault | server | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 20 | Ubuntu Server LTS | server | x86_64 | Yes | builtin | Automatic | Stable ISO |
| 21 | FreeBSD | other | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 22 | FreeDOS | other | x86 | No | manual | Manual source | Archive needs special handling |
| 23 | ReactOS | other | x86 | No | manual | Manual source | Archive needs special handling |
| 24 | Ubuntu Desktop LTS | desktop | x86_64 | Yes | builtin | Automatic | Stable ISO |
NixOS, Windows 11 and Proxmox VE are excluded from the initial catalog. The catalog
contains 24 projects, including Ubuntu Desktop alongside Ubuntu Server. x86-only projects are labeled explicitly.

## Layout and state

```text
DESTINATION/
├── ISO/
│   ├── desktop/PROVIDER/
│   ├── rescue/PROVIDER/
│   ├── security/PROVIDER/
│   ├── network/PROVIDER/
│   ├── server/PROVIDER/
│   └── other/PROVIDER/
└── .ventoy-library/
    ├── state.json
    ├── state.json.bak
    └── write.lock          # only during writes
```

The schema-versioned state stores identity, version, filename, relative path,
source URL, expected bytes, checksum metadata, timestamp, verification and acquisition
method. State is serialized to a same-directory temporary file, flushed and fsynced,
then atomically replaced. The previous valid state is retained as a backup. Recovery
warns when using that backup and never silently resets a corrupted database.
Keep-old records remain tracked. An interrupted transaction may leave an untracked
completed file; it is preserved, never automatically adopted or deleted.

## Storage and security

Storage comes from `shutil.disk_usage`. Required free space reserves **all new bytes
plus the safety margin**: existing old images, partial files and anticipated cleanup
never reduce the reservation. The displayed projected free space is before cleanup.
Unknown sizes are reported honestly and block transfers. A local file can supply a
known size if upstream metadata did not have one. Size checks cannot account for
other applications writing concurrently, quotas, or every filesystem allocation limit.

Checksums authenticate bytes only to the extent the upstream checksum source is trusted;
GPG verification is not implemented. Missing checksums produce `unverified`, never
`verified`. Resume requires a checksum and an exact matching sidecar describing the
source/version/size/checksum; unverified downloads restart from zero. A server ignoring
Range causes a restart, while invalid Content-Range data is rejected.

Safety checks reject filesystem roots, raw/special files, traversal, symlink paths,
unsafe remote filenames and existing targets. Only tracked exact files in a provider's
directory can be deleted, after the replacement is installed, recorded and rechecked.
There is no recursive deletion. Same-filename updates currently fail closed; providers
should use versioned filenames. The destination and its parent directories must be
trusted: the writer lock coordinates this application, not hostile processes racing
filesystem changes. Atomic rename and lock reliability depend on the filesystem;
network filesystem and power-loss durability need platform validation.

## Adding a provider

Implement the protocol in `providers/base.py` and register the adapter in
`default_registry()`. Add new projects at the end of `catalog.py` to preserve existing
numbers. Core downloading and storage do not need changes. Keep the README table
synchronized; tests verify it against the registry.

```python
from ventoy_library.models import Release


class ExampleProvider:
    name = "example"
    display_name = "Example OS"
    category = "rescue"
    architecture = "x86_64"

    def get_latest_release(self) -> Release:
        # Fetch official metadata using an injected HTTP client, parse and validate it.
        # Select a stable x86-64 boot artifact; return its upstream URL/size/checksum.
        raise NotImplementedError("Implement and test official-source discovery first")
```

`Release` carries provider, display_name, version, category, architecture, filename,
url (or None for manual acquisition), size, checksum_algorithm and checksum.
Missing sizes/checksums are None. SHA256 and SHA512 names are lowercase.
Use `LibraryError` for expected discovery failures; planning reports them per provider.
Do not invent upstream endpoints. Record official source, mechanism, stable selection,
architecture, artifact rules, size/checksum sources and limitations before implementation.
Do not assume an artifact ends in `.iso`.

## Troubleshooting

- **Manual entry:** supply an official local image/direct URL or skip. Automatic discovery
  is currently available for Arch, SystemRescue, Ubuntu Server LTS and Ubuntu Desktop LTS.
- **Destination unavailable:** mount the drive and confirm the configured directory exists.
- **Download/website failure:** rerun later; provider adapters may need maintenance.
  Explicit local files and alternate URLs work when release metadata can still be discovered.
- **Insufficient storage:** free space yourself or select fewer providers. Existing managed
  images are not deleted to make room for a replacement.
- **Unknown file size:** no transfer begins; use an authoritative source with size metadata
  or a local file. There is no unsafe bypass flag.
- **Checksum mismatch:** the old image survives. Do not trust the new bytes. Quarantine/remove
  that exact `.part` and its `.part.json` sidecar yourself before retrying a fresh transfer.
- **Interrupted download:** rerun with the same source/version. Recognized partials resume
  if checksums and server Range support permit it. Unrecognized partials are preserved.
- **Stale lock:** ensure no writer is running before removing only `.ventoy-library/write.lock`.
- **Corrupt state:** valid backups are read with a warning. If both files are corrupt, restore
  trusted state manually; the application will not infer ownership of existing images.
- **pipx update problem:** confirm `pipx` is on PATH and manages this environment. Local,
  editable, suffixed or pinned installations require manual maintenance. A failed force install
  may require reinstalling the previous tag. Check the explicit command before approving it.
- **Verbose output:** `-v` or `-vv` adds diagnostics; ordinary errors avoid tracebacks.

## Development

```bash
git clone https://github.com/numberformat/ventoy-library.git
cd ventoy-library
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest
python -m build
```

On Windows activate `.venv\Scripts\Activate.ps1` instead. CI runs lint and tests on
Linux and macOS with Python 3.11–3.14, and builds distributions on Linux.
Tests use mocked HTTP transports and tiny local files; an autouse fixture blocks socket
connections. No tests fetch operating-system images. See [architecture](docs/architecture.md).

## Releases

Use Semantic Versioning, stable tags such as `v0.1.0` and matching GitHub releases.
The version lives in `src/ventoy_library/metadata.py`; Hatch reads it for packaging.
Runtime project/repository identity also lives there. Standard package metadata in
`pyproject.toml` and documentation must be kept consistent; tests check packaging URLs.
A `0.x` version signals an evolving interface. Update `CHANGELOG.md` before releasing.

## License

[MIT](LICENSE).
