# ventoy-library

Safely manage bootable operating-system, rescue, diagnostic, security, networking,
and server images on a Ventoy data partition **or any ordinary directory**.
This independent project is not affiliated with Ventoy or any supported operating-system project.
It never installs or updates Ventoy, formats a drive, or accesses raw block devices.

**Version 0.1.0.** Browse the available images in a numbered
24-image catalog, choose a few or all, then review the storage plan before downloading.
Twelve providers discover releases at runtime. Most have SHA256 manifests; Clonezilla
currently installs as unverified because its official checksum endpoint blocks automated
requests. Other entries accept a user-supplied local image or URL; candidate YAML
release snapshots can also supply download URLs for them.
See the [project status and roadmap](docs/roadmap.md) for completed milestones and
the next development steps.
For periodic manual research, use the [ChatGPT web research prompt](docs/release-refresh-prompt.md)
to produce a sourced YAML snapshot of current official image URLs. Verify each candidate
entry before publishing it; the twelve built-in providers already discover releases at runtime.

## Features and scope

Implemented core capabilities:

- Numbered image catalog filtered by checked links, with multi-selection and ranges.
- Latest stable release discovery for twelve automatic providers.
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

The application needs Python 3.11 or newer. The
[NOAMi installer](https://github.com/numberformat/noami-installer) downloads the wheel
attached to the latest published GitHub Release and installs it with pipx. It can
bootstrap pipx if needed, so Git and a preinstalled pipx are not required. Run the
installer with a Python 3.11+ interpreter that includes `venv`:

```bash
PIPX_DEFAULT_PYTHON="$(command -v python3)" python3 -c 'import urllib.request; exec(urllib.request.urlopen("https://numberformat.github.io/noami-installer/install.py").read())' ventoy-library
ventoy-library --help
ventoy-library --version
```

If `python3` is older than 3.11, use the command for your newer interpreter, such as
`python3.11`, in both places. `PIPX_DEFAULT_PYTHON` ensures an existing pipx uses that
interpreter for the application environment. The installer requires a public release
with exactly one wheel asset.
On Windows PowerShell, use:

```powershell
$env:PIPX_DEFAULT_PYTHON = (py -3.11 -c 'import sys; print(sys.executable)')
py -3.11 -c 'import urllib.request; exec(urllib.request.urlopen("https://numberformat.github.io/noami-installer/install.py").read())' ventoy-library
```

For a Git checkout, `pipx install "git+https://github.com/numberformat/ventoy-library.git"`
remains an alternative; it requires Git and a separately installed pipx. For a local
checkout, use `pipx install .`. The application also supports
`python -m ventoy_library` within its Python environment.

## Keep an installer on a Ventoy USB drive

Copy [install-ventoy-library.sh](install-ventoy-library.sh) to the USB drive once.
When you find the drive on a computer later, run the script to install or reinstall
the application through pipx from this project's GitHub repository:

```bash
cd /Volumes/Ventoy
sh install-ventoy-library.sh
ventoy-library config set destination /Volumes/Ventoy
```

The script stays on the USB and invokes the NOAMi installer to install the latest
published release wheel on the current computer. It needs Python 3.11+ and network
access, but no Git, GitHub account, SSH setup, or preinstalled pipx. Set
`VENTOY_LIBRARY_PYTHON=/path/to/python3.11` when the default `python3` is older.
Run the USB script again to update a wheel installation.

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

`--check-update` works for wheel and Git installations. `--update` currently requires
a positively identified, unsuffixed, unpinned pipx Git installation. To update a
NOAMi wheel installation, rerun the NOAMi installer or the USB script above.
Editable/development installations are not automatically changed; update development
checkouts yourself with Git. No automatic `git pull` is run.

Plain `pipx upgrade ventoy-library` retains its recorded source, including a pinned
Git tag. Self-update instead installs the checked stable tag explicitly through pipx:

```bash
# Example only: substitute an existing stable release tag.
pipx install --force "git+https://github.com/numberformat/ventoy-library.git@v0.1.0"
```

This uses pipx's supported force-install mechanism and avoids updating to an
unreleased default-branch commit. It requires confirmation unless `--yes` is passed.
The application exits after pipx returns. See
[research notes](docs/self-update.md).

## Configure and inspect a library

Ventoy mode is the default. When the current directory is on a detected Ventoy data
partition, the application uses that drive's root without asking, even if another
destination was saved. This also works from a subdirectory on the drive. An explicit
`--destination PATH` takes precedence. Otherwise, the app checks a saved destination,
then searches all mounted partitions. One detected drive is selected automatically,
including when a saved path is stale; multiple drives produce a numbered choice. If detection fails,
interactive commands ask for the
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

Detection searches mounted partitions on Linux, Windows, and macOS using operating-system
metadata, including the sibling `VTOYEFI`
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
`--directory` override the saved mode; `--destination PATH` overrides current-directory
detection and the saved path.
Previously configured ordinary folders now require explicit directory mode.
Configuration follows platform per-user conventions, outside the installed package.
`list` shows only catalog entries whose download link passed a metadata-only HEAD
check, even without a mounted drive. It shows
catalog or installed versions, plus the catalog research date or installed download date
when available. Fresh checks are cached for three days in
`~/.noami.us/ventoy-library/availability.json` (under the user profile on Windows).
After that, `list` checks the links again before displaying them. Use
`list --refresh-links` to check again immediately. An unavailable link is hidden
from the normal catalog; `check --downloads` reports failures for diagnosis.
`status` lists managed files and storage. `check` queries providers.
`check` and `--dry-run` never write configuration, state, locks or partial files.

To check whether upstream image URLs respond without a USB drive or an image download:

```bash
ventoy-library check --downloads --only alpine
ventoy-library check --downloads --only arch --only systemrescue
ventoy-library check --downloads          # the entire catalog
ventoy-library check --downloads --exclude kali
ventoy-library check --downloads --exclude kali --url fedora=https://MIRROR/Fedora-Workstation.iso
```

This mode discovers current releases and sends **HEAD requests only** to the image URLs.
It needs network access but no destination, mounted drive, or saved library state.
It reports unreachable URLs, unsupported HEAD requests, and size mismatches, then
lists every failed source again at the end. It cannot guarantee that a later full
transfer will complete. Use `--only` or `--select NUMBERS` to narrow the check.
Candidate snapshots and manual entries with catalog URLs are checked too. A manual
entry may point to a ZIP, gzip, or bzip2 package rather than a bootable ISO; a successful
HEAD request confirms only that the package URL responds. Entries without a catalog
URL are listed as not testable automatically. Supply an alternate URL with repeatable
`--url PROVIDER=URL`, or omit entries with repeatable `--exclude PROVIDER`. These options
affect this check only; replace `MIRROR` with a verified source. The command exits
nonzero when a source fails or is skipped.

For a full release and storage dry run without a USB drive, use an existing ordinary
folder as the destination:

```bash
mkdir -p ~/ventoy-library-preview
ventoy-library update-images --dry-run --directory --destination ~/ventoy-library-preview --only alpine
```

The dry run creates no image files. Its storage figures describe that folder's
filesystem, not the USB drive you may use later.

## Choose and add images

```bash
ventoy-library list
ventoy-library add
```

`add` displays the available catalog entries with their stable numbers. Enter, for example,
`1,8,20,24` for Arch, SystemRescue, Ubuntu Server and Ubuntu Desktop; ranges such as
`1-3,9` also work when those entries are shown. Enter **0** (or `all`) for every
available image, or `q` to cancel. `--all` also selects only available images.
`--only` and `--select` let you explicitly choose an unlisted entry when providing
your own image or investigating its source. `--refresh-links` forces a new link check.
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

The table describes the built-in registry. Candidate YAML entries supply release
snapshots without live discovery. Manual entries accept user-supplied files or URLs.
Official-source research and metadata fixtures for automatic providers are documented in
[provider research](docs/providers.md).

| # | Project | Category | Architecture | Runtime discovery | Catalog entry | Acquisition | Notes |
|---|---|---|---|---|---|---|---|
| 1 | Arch Linux | desktop | x86_64 | Yes | builtin | Automatic | Stable ISO |
| 2 | Alpine Linux | desktop | x86_64 | Yes | builtin | Automatic | Standard ISO; SHA256 |
| 3 | Fedora Workstation | desktop | x86_64 | No | candidate | Catalog URL | Fedora mirror selector; snapshot version |
| 4 | Debian Live | desktop | x86_64 | Yes | builtin | Automatic | amd64 netinst ISO; SHA256 |
| 5 | Linux Mint | desktop | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 6 | Knoppix | desktop | x86_64 | No | candidate | Manual source | Catalog URL unavailable |
| 7 | Tiny Core Linux | desktop | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 8 | SystemRescue | rescue | x86_64 | Yes | builtin | Automatic | Stable ISO |
| 9 | GParted Live | rescue | x86_64 | Yes | builtin | Automatic | Stable ISO; SHA256 |
| 10 | Clonezilla Live | rescue | x86_64 | Yes | builtin | Automatic | Stable ISO; unverified |
| 11 | Rescuezilla | rescue | x86_64 | Yes | builtin | Automatic | Primary 64-bit ISO; SHA256 when published |
| 12 | Hiren's BootCD PE | rescue | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 13 | Memtest86+ | rescue | x86_64 | No | manual | Manual source | Archive needs special handling |
| 14 | Kali Linux | security | x86_64 | Yes | builtin | Automatic | Live ISO; SHA256; currently absent upstream |
| 15 | Parrot Security | security | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 16 | Tails | security | x86_64 | Yes | builtin | Automatic | Stable ISO; SHA256 |
| 17 | OPNsense | network | x86_64 | No | manual | Manual source | Compressed ISO needs special handling |
| 18 | OpenWrt x86-64 | network | x86_64 | No | manual | Manual source | Compressed disk image needs special handling |
| 19 | OpenMediaVault | server | x86_64 | No | candidate | Catalog URL | Direct ISO URL; unverified |
| 20 | Ubuntu Server LTS | server | x86_64 | Yes | builtin | Automatic | Stable ISO |
| 21 | FreeBSD | other | x86_64 | Yes | builtin | Automatic | Production disc1 ISO; SHA256 |
| 22 | FreeDOS | other | x86 | No | manual | Manual source | Archive needs special handling |
| 23 | ReactOS | other | x86 | No | manual | Manual source | Archive needs special handling |
| 24 | Ubuntu Desktop LTS | desktop | x86_64 | Yes | builtin | Automatic | Stable ISO |
NixOS, Windows 11 and Proxmox VE are excluded from the initial catalog. The catalog
contains 24 projects, including Ubuntu Desktop alongside Ubuntu Server. x86-only projects are labeled explicitly.

## Layout and state

```text
DESTINATION/
├── ISO/
│   ├── archlinux-YYYY.MM.DD-x86_64.iso
│   └── ubuntu-YY.MM.P-desktop-amd64.iso
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
Keep-old records remain tracked. New images are saved directly in `ISO/`. Existing
managed images in older category/provider subfolders are moved to `ISO/` when selected
for an update. If a top-level copy already exists, it must pass the upstream checksum
before the tracked nested copy is removed. An untracked top-level image with a matching
upstream checksum can be added to state without downloading it again. Untracked nested
images are left untouched; move or import them explicitly.

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
unsafe remote filenames and conflicting targets. Only tracked exact files can be deleted,
after the replacement is installed, recorded and rechecked.
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
After committing the release contents, push a tag matching the package version (for
example, `v0.1.0`). The [release workflow](.github/workflows/release.yml) builds one
platform-independent wheel, checks its version and bundled catalog, and publishes a
GitHub Release with that wheel attached. The NOAMi installer reads the latest published
release; a tag alone or a wheel stored only in the repository is insufficient.

## License

[MIT](LICENSE).
