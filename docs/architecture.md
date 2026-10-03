# Architecture

`cli` orchestrates services and presentation. `models` contains immutable dataclasses
and string enums; OS release versions are opaque strings (date-based versions are valid).
`catalog` defines all 24 entries and their stable numeric order. `selection` displays
only entries whose link passed an availability check and parses numeric lists/ranges/all.
`availability_cache` stores three-day HEAD results under the user's
`.noami.us/ventoy-library` directory. `list` does not write to the destination;
`add` and `update-images` provide the interactive chooser. Manual source prompts
finish before discovery/planning, and the writer lock is only acquired after confirmation.

`providers` owns upstream-specific selection. Twelve entries have automatic adapters, including Arch, Alpine, Debian,
SystemRescue, GParted, Clonezilla, Rescuezilla, Kali, Tails, Ubuntu Server,
FreeBSD and Ubuntu Desktop; remaining entries use a generic manual import adapter. The bundled `releases.yaml` supplies candidate release
snapshots for manual entries; `release_catalog` loads usable `candidate` records
from the installed package and does not claim live discovery.
`planner` asks every provider for a release, resolves acquisition overrides, and returns
a complete immutable plan with per-provider discovery errors.

`volumes` reads OS partition metadata without accessing raw devices. `destinations`
selects mounted data partitions and captures mount identity; explicit directory mode
preserves ordinary-filesystem use. `ventoy` validates the image plan against read-only
Ventoy configuration. The guard runs before acquisition and installation, with mount
checks during transfer. See [destination policy](destinations.md).

`storage` reserves the full planned size and margin against actual filesystem free
space. Existing files already consume that free space, so old-image bytes are not
subtracted from required downloads. Unknown sizes fail closed. `progress` aggregates
absolute file offsets so resume/restart does not double-count bytes.

`downloader` streams bounded chunks using an injected HTTPX client. HTTP and local-copy
primitives do not install files. `verification` separates checksum policy and hashing.
`library` sequences acquisition, verification, same-filesystem rename, state recording,
and exact old-file cleanup. The caller holds a single-writer lock and rechecks the
state snapshot before execution. Existing target files always block overwrite.

`state` is a schema-versioned list of managed image records, allowing multiple kept
versions. Last recorded provider entry is its current version. Unknown schema versions
are rejected; a valid backup may be used with a warning. The library preserves orphaned
files after interruption; state is not reconstructed by scanning untracked images.
Atomic file replacement and backup protect against truncated writes, but the state/image
pair is not one filesystem transaction. Full power-loss durability and remote filesystem
locking need dedicated integration tests before stronger guarantees are made.

`app_update` uses GitHub metadata and version parsing separately from OS providers.
`metadata.py` centralizes runtime naming, version and repository URL. The build reads
that version. Static PEP 621 name/URLs are checked for consistency by tests.

Runtime dependencies: HTTPX (streaming/injected mock transport), platformdirs (per-user
configuration), packaging (application versions), PyYAML (safe parsing of an optional
release catalog). Standard-library argparse, hashlib,
pathlib, shutil and JSON keep the remaining surface small. No Rich dependency yet.

Open work: automatic discovery research/adapters for the remaining catalog entries;
version-qualified filenames for projects reusing names; transfer-time fallback menus
and multi-file failure summaries; disk-full/unplug recovery integration checks;
real pipx upgrade smoke test after a stable GitHub release is available.
