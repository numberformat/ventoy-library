# Destination detection and Ventoy visibility

Ventoy mode is the default. The application manages files, never partitions or raw
devices. A directory named Ventoy is not proof of an installation.

## Detection

The candidate is a writable, mounted first partition on a disk whose second FAT
partition is labelled `VTOYEFI`, following the official
[Ventoy disk layout](https://www.ventoy.net/en/doc_disk_layout.html).
On macOS, `diskutil` may report an unmounted Ventoy EFI partition without its FAT
filesystem or label. In that case the detector also accepts an external MBR disk
whose second partition is exactly 32 MiB with partition type `0xEF`.
The data partition can have any label. Supported filesystem metadata includes exFAT,
NTFS, FAT, ext2/3/4, XFS and UDF. Read-only and unsupported filesystems are refused.

- macOS: read-only `diskutil list -plist` and `diskutil info -plist` metadata,
  including the unlabeled EFI-partition layout described above.
- Linux: `/sys/class/block`, `/run/udev/data`, and `/proc/self/mountinfo`. No block
  device is opened. Missing udev information can prevent automatic identification.
  Subtree bind mounts do not qualify as the data-partition root.
- Windows: read-only PowerShell `Get-Partition`/`Get-Volume` metadata. Mounted drive
  letters are supported; volumes without drive letters require manual selection.

This is a layout heuristic, not authentication of Ventoy boot code. If metadata is
unavailable, the interactive fallback requires an actual mounted filesystem root
and explicit confirmation that it is Ventoy's data partition. Known boot partitions,
known non-first partitions, and the system filesystem root remain forbidden. The
application does not mount drives or save fallback confirmation. A manually confirmed
installation must be confirmed again if subsequent automatic detection still fails.

The current directory is checked first when no `--destination` was supplied. If it is
on a detected Ventoy data partition, that partition's mount root is used without a
prompt, including when the current directory is a subfolder. An explicit
`--destination` takes precedence, followed by a valid saved destination. The app scans
all mounted partitions on Linux and Windows before prompting. One detected drive is
automatically selected even when a saved path is stale; multiple drives produce numeric
choices. An unrecognized explicit path prompts in interactive mode. Noninteractive
use fails when the target cannot be identified. `list` needs no drive or prompt.

## Menu visibility checks

Before downloading any selected image, every planned ISO/IMG path is checked against:

- containment on the data partition, symlinks and intermediate mount boundaries;
- `.ventoyignore` at any ancestor directory;
- `VTOY_DEFAULT_SEARCH_ROOT` and `VTOY_MAX_SEARCH_LEVEL`;
- `VTOY_FILE_FLT_ISO` / `VTOY_FILE_FLT_IMG`;
- `image_list` and `image_blacklist`, including filename wildcards;
- legacy, UEFI, IA32, AA64 and MIPS configuration overrides.

References: official [search rules](https://www.ventoy.net/en/doc_search_path.html),
[control plugin](https://www.ventoy.net/en/plugin_control.html),
[image lists](https://www.ventoy.net/en/plugin_imagelist.html),
[boot-mode overrides](https://www.ventoy.net/en/plugin_dual_option.html), and
[path matching](https://www.ventoy.net/en/plugin_path_match.html).
Ventoy's `*` matches exactly one filename character, not an arbitrary string.

Unsupported or malformed relevant configuration fails closed. Paths use the
application's conservative portable filename policy. Reserved Ventoy boot-plugin
image filenames and compressed artifacts are refused. FAT images of 4 GiB or larger
are refused. WIM/VHD/EFI and other formats need additional plugin/mode validation
before this application will accept them in Ventoy mode. These restrictions are
application limits, not a claim that Ventoy cannot boot those formats.

The application never edits `ventoy/ventoy.json`. If the configured search directory
excludes the planned path, select a destination within it. If depth or allow-list
settings exclude a planned image, adjust those settings yourself before retrying.
All supported boot-mode profiles must allow the image; this deliberately errs on the
side of refusal even when a user only boots in one mode.

Checks repeat after confirmation and before each acquisition/installation. Transfer
callbacks verify that the mount and filesystem identity remain present. These checks
do not guarantee bootability, protect against malicious concurrent filesystem changes,
or eliminate every unplug/remount race. Real-device integration testing remains
necessary; automated tests use synthetic OS metadata and temporary directories.
No Ventoy drive was attached during implementation. Windows parsing is fixture-tested,
not verified against a live Windows installation.

## Ordinary directories and the safety buffer

`--directory --destination PATH` explicitly opts out of Ventoy detection and menu
rules while retaining file safety and storage checks. Save the preference with
`config set destination_mode directory`; `--ventoy` overrides it for one invocation.
Known `VTOYEFI` boot partitions are prohibited even in directory mode.

The safety buffer defaults to 2 GiB without any configuration. The storage check
requires free bytes for the full planned downloads plus the buffer. It does not count
future old-image deletions as available space. The buffer provides headroom; it is
not an allocation reservation and does not stop concurrent applications using space.
`config set safety_margin 2` sets 2 GiB; fractional values and zero are supported.
