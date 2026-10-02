# Release catalog refresh

Use this workflow when refreshing `src/ventoy_library/releases.yaml`.

Research each non-builtin distribution from its official project source. Keep the
existing catalog order and IDs. `candidate` means the catalog entry contains a
usable release identity and artifact information; `manual` means automated
acquisition is unavailable or requires special handling. Built-in provider entries
remain `builtin` and are discovered by the runtime provider.

For `candidate` and `manual` entries, use only these fields:

```yaml
status: candidate # or manual
source_page: "https://official.example/downloads/"
discovery_url: "https://official.example/releases/"
version: "1.2.3" # null if genuinely unknown
architecture: "x86_64"
filename: "example.iso" # null if genuinely unknown
url: "https://official.example/example.iso" # null if not directly available
notes: "Concise source and limitation notes."
```

For `builtin` entries, use `status`, `source_page`, `discovery_url`, and `notes`.

Do not add file-size, checksum, or review timestamp metadata. Do not infer release
URLs or artifact names. A candidate's version, architecture and filename must identify
a usable artifact; use `manual` when these cannot be established. The application
checks URLs when supplied and resolves byte sizes at runtime when possible.

Before submitting, load the file with `ventoy-library check --release-catalog PATH`
or run the catalog tests. Never add distributions outside the IDs in `catalog.py`.
