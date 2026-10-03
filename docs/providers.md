# Provider research and catalog behavior

Researched 2026-09-29 using live official metadata, small checksum manifests,
and HEAD responses. No operating-system image bodies were downloaded.
The automated tests use recorded metadata fixtures plus synthetic failure cases;
normal test runs cannot access the network.

## Arch Linux

- Official sources: [release JSON](https://archlinux.org/releng/releases/json/) and
  [download page](https://archlinux.org/download/).
- Discovery: JSON `releases`, filtered to `available: true` and date versions
  `YYYY.MM.DD`, choosing the newest available entry.
- Architecture/artifact: the torrent filename must be the matching versioned
  `archlinux-VERSION-x86_64.iso`. Bootstrap archives and other architectures are excluded.
- Size: exact `torrent.file_length` from upstream metadata; no rounded display sizes.
- Checksum: `sha256_sum` from the same release entry.
- Download: the upstream `iso_url` path is resolved against the official Fastly mirror
  advertised by Arch. Its [mirror index](https://fastly.mirror.pkgbuild.com/iso/2026.09.01/)
  was checked against the metadata. The relative path on archlinux.org itself returned
  HTTP 403 during research, so the download host is the official mirror instead.
- Limitations: mirror availability is not guaranteed; discovery fails closed on schema
  changes. PGP verification is not implemented.

## SystemRescue

- Official source: [download page](https://www.system-rescue.org/Download/).
- Discovery: links from the official current-download page. No structured current-release
  API was identified; parsing link targets avoids depending on presentation text/tables.
- Stable selection: versioned `systemrescue-N.N-amd64.iso` links on the official Fastly
  host; beta directories, non-amd64 builds, checksum files and signatures are excluded.
- Size: HEAD Content-Length of the exact linked ISO; absent/unreliable size stays unknown.
- Checksum: fetch the matching `.sha256` link actually advertised on system-rescue.org
  and require an exact filename match in its manifest.
- Limitations: HTML link or host changes can require adapter maintenance. No rounded MiB
  count is used for space checking. GPG signatures are not verified.

## Ubuntu Server LTS and Ubuntu Desktop LTS

- Official sources: [LTS metadata](https://changelogs.ubuntu.com/meta-release-lts),
  [release index](https://releases.ubuntu.com/), and its per-release download pages.
- Discovery: select the highest supported stable numeric LTS version from the metadata.
  Resolve its series directory from an actual link in the official index, then inspect
  the artifacts published there. This keeps the series and boot artifacts linked to
  official sources rather than constructing an assumed image URL.
- Stable selection: highest numeric point release in the selected LTS series; no beta,
  RC, daily or development names. The LTS upgrade metadata may lag the initial release
  until upstream enables LTS upgrades; discovery follows that channel deliberately.
- Architecture/artifact: Server selects `ubuntu-VERSION-live-server-amd64.iso`;
  Desktop separately selects `ubuntu-VERSION-desktop-amd64.iso`. ARM, WSL, cloud,
  netboot and torrent files are excluded.
- Size: HEAD Content-Length of the selected ISO.
- Checksum: exact filename entry from the linked `SHA256SUMS` manifest.
- Limitations: changes to metadata/index layouts can fail discovery. Missing sizes block
  acquisition. GPG manifest verification is not implemented.
- Both variants have their own provider IDs, destination directories and state records.
  Desktop is included as catalog entry 24.

## New runtime providers

- **Alpine:** [latest-stable x86_64 index](https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/); newest numeric Standard ISO, matching SHA256 sidecar and HEAD size.
- **Debian:** [current amd64 ISO index](https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/); newest netinst ISO, SHA256SUMS and HEAD size. The catalog label remains Debian Live for compatibility, though this selected image is an installer.
- **GParted:** [official download page](https://gparted.org/download.php); current stable amd64 SourceForge URL advertised there, [official checksum manifest](https://gparted.org/gparted-live/stable/CHECKSUMS.TXT) and HEAD size.
- **Clonezilla:** [project-endorsed SourceForge stable directory](https://sourceforge.net/projects/clonezilla/files/clonezilla_live_stable/); newest Debian-based amd64 ISO and HEAD size. Its [official download page](https://clonezilla.org/downloads.php) and checksum endpoint currently return a browser challenge to this client, so checksum verification is unavailable and the image is explicitly unverified.
- **Rescuezilla:** [official GitHub Releases API](https://api.github.com/repos/rescuezilla/rescuezilla/releases); newest stable release, primary 64-bit ISO named in its release notes, exact asset size and SHA256SUM when published. Other codename variants are excluded.
- **Kali:** [current image index](https://cdimage.kali.org/current/); newest live amd64 ISO, SHA256SUMS and HEAD size. On 2026-10-02 the official index listed only the live ISO torrent, not the ISO itself. Discovery reports this explicitly and fails until upstream restores a direct ISO; it does not substitute an installer or development image.
- **Tails:** [stable update JSON](https://tails.net/install/v2/Tails/amd64/stable/latest.json); amd64 ISO, exact size and SHA256 directly from the structured metadata.
- **FreeBSD:** [amd64 release index](https://download.freebsd.org/releases/amd64/amd64/ISO-IMAGES/); newest directory with a production RELEASE disc1 ISO, official SHA256 manifest and HEAD size. Beta/RC-only directories are skipped.

All metadata reads are capped at 2 MiB. These adapters validate advertised hosts,
paths, architectures and artifact names. A missing required artifact or malformed
metadata fails discovery; no fixed YAML version is used as a fallback.

## Remaining catalog entries

Fedora Workstation, Linux Mint, Knoppix, Tiny Core, Hiren's BootCD PE, Parrot,
OpenMediaVault, Memtest86+, OPNsense, OpenWrt, FreeDOS and ReactOS have no runtime
upstream discovery adapter yet. Candidate snapshots and manual entries continue to
work according to their catalog status.

The [YAML release refresh workflow](release-refresh-prompt.md) lets a maintainer
refresh official source details and prepare a candidate snapshot. The YAML ships
inside the package and loads automatically. Candidate records with release identity
are usable download sources. Manual records remain available for explicit user-supplied
files or URLs.
The twelve built-in providers discover releases at runtime.

The shared manual acquisition adapter supports explicit local files and direct HTTP(S)
URLs. Users must obtain an appropriate bootable artifact from its official upstream.
The app uses the supplied basename, local file size or HEAD response, marks the version
`user-supplied`, and marks verification `unverified`. Local or URL acquisition is recorded
in state. It does not validate architecture, licensing, signatures, or bootability, and
does not unpack compressed images. Existing targets are never overwritten.

Interactive selection collects local files/URLs or explicit skips for manual entries
before the complete space check. Unresolved entries in unattended runs/dry runs are
reported, excluded from the executable plan, and cause nonzero status. Available
entries can proceed when the executable plan passes preflight; no failed entry is
silently reported as successfully downloaded.

## Numeric selection

`catalog.py` defines the stable display order. `list` checks links with HEAD and shows
only entries whose link passed, using a three-day cache. It includes acquisition status
and installed versions when available. Use `list --refresh-links` to recheck now.
`add` and `update-images` accept an interactive choice, `--select 1,8,20,24`, or `--all`.
`0` means all shown entries in the chooser; `--select 0` explicitly chooses the full
catalog. `q` cancels. Filtered `list --only` output
retains global catalog numbers. Local overrides can use numeric keys, e.g. `--local 13=PATH`.
