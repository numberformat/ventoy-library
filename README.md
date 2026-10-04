# ventoy-library

`ventoy-library` downloads and manages bootable images on a Ventoy USB drive or
in an ordinary folder. It checks available space, verifies upstream checksums
when available, and keeps the old image until a replacement succeeds. It does
not install Ventoy or change partitions.

This independent project is not affiliated with Ventoy or the projects whose
images it downloads.

## Install

Requires Python 3.11 or newer and an internet connection. The installer sets up
pipx if needed; Git is not required.

On macOS or Linux, install from the latest GitHub Release:

```bash
PIPX_DEFAULT_PYTHON="$(command -v python3)" python3 -c 'import urllib.request; exec(urllib.request.urlopen("https://numberformat.github.io/noami-installer/install.py").read())' ventoy-library
```

If you keep [install-ventoy-library.sh](install-ventoy-library.sh) on your USB
drive, run `sh install-ventoy-library.sh` from that drive instead. Use
`VENTOY_LIBRARY_PYTHON=/path/to/python3.11` if your default `python3` is older.

On Windows PowerShell:

```powershell
$env:PIPX_DEFAULT_PYTHON = (py -3.11 -c 'import sys; print(sys.executable)')
py -3.11 -c 'import urllib.request; exec(urllib.request.urlopen("https://numberformat.github.io/noami-installer/install.py").read())' ventoy-library
```

## Use

Mount the Ventoy USB drive. Run the app from anywhere on that drive; it will
detect the drive automatically. If needed, save its path with
`ventoy-library config set destination /Volumes/Ventoy` (replace the path for
your system).

```bash
ventoy-library list                  # Show images with checked download links
ventoy-library add                   # Choose images, review space, then download
ventoy-library status                # Show managed images and storage
ventoy-library update-images         # Check selected images for newer releases
```

`add` and `update-images` offer a numbered chooser. Enter `0` for all available
images, or choose one with `--only systemrescue`. No image downloads until you
approve the plan. Images are saved in `ISO/`; the app records managed files in
`.ventoy-library/state.json` on that drive. Keep this file with the library.

Useful options:

```bash
ventoy-library add --only systemrescue --dry-run
ventoy-library add --local hirens=~/Downloads/HBCD_PE_x64.iso
ventoy-library update-images --only systemrescue --keep-old
ventoy-library check --downloads     # Check all image links without a USB or ISO download
ventoy-library list --refresh-links  # Recheck links now instead of using the three-day cache
```

For an ordinary folder instead of Ventoy, use
`--directory --destination /path/to/folder` with `add`, `status`, `check`, or
`update-images`. The folder must already exist.

## Update or uninstall the app

```bash
ventoy-library --check-update
ventoy-library --update
pipx uninstall ventoy-library
```

`--update` updates the app; `update-images` updates the image library. The
published v0.1.0 wheel cannot self-update. After the next release is published,
run the installer above once more; later versions can update themselves from
GitHub Release wheels without Git. Uninstalling the app leaves USB images in place.

## Available images

The CLI displays only images whose links passed a check. Some entries have live
release discovery; others use a bundled link or ask for a local file or direct
URL. A checked link does not guarantee a complete download. Images without an
upstream checksum are marked **unverified**.

| # | Project | Category | Architecture | Live discovery |
|---|---|---|---|---|
| 1 | Arch Linux | desktop | x86_64 | Yes |
| 2 | Alpine Linux | desktop | x86_64 | Yes |
| 3 | Fedora Workstation | desktop | x86_64 | No |
| 4 | Debian Live | desktop | x86_64 | Yes |
| 5 | Linux Mint | desktop | x86_64 | No |
| 6 | Knoppix | desktop | x86_64 | No |
| 7 | Tiny Core Linux | desktop | x86_64 | No |
| 8 | SystemRescue | rescue | x86_64 | Yes |
| 9 | GParted Live | rescue | x86_64 | Yes |
| 10 | Clonezilla Live | rescue | x86_64 | Yes |
| 11 | Rescuezilla | rescue | x86_64 | Yes |
| 12 | Hiren's BootCD PE | rescue | x86_64 | No |
| 13 | Memtest86+ | rescue | x86_64 | No |
| 14 | Kali Linux | security | x86_64 | Yes |
| 15 | Parrot Security | security | x86_64 | No |
| 16 | Tails | security | x86_64 | Yes |
| 17 | OPNsense | network | x86_64 | No |
| 18 | OpenWrt x86-64 | network | x86_64 | No |
| 19 | OpenMediaVault | server | x86_64 | No |
| 20 | Ubuntu Server LTS | server | x86_64 | Yes |
| 21 | FreeBSD | other | x86_64 | Yes |
| 22 | FreeDOS | other | x86 | No |
| 23 | ReactOS | other | x86 | No |
| 24 | Ubuntu Desktop LTS | desktop | x86_64 | Yes |

## If something goes wrong

- **Drive not found:** mount its data partition, run the command from that drive, or set its destination path.
- **Not enough space:** free space or select fewer images. The app reserves a 2 GiB buffer and keeps old images until a replacement succeeds.
- **Download interrupted:** run the command again. Checksummed partial downloads can resume when the server supports it.
- **Link unavailable or image needs manual download:** use `--local PROVIDER=/path/to/file` or provide a direct URL when prompted.
- **Checksum mismatch:** the old image remains intact; do not use the failed download.

Run `ventoy-library --help` for all options. Licensed under [MIT](LICENSE).
