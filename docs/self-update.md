# Application updater research

Reviewed 2026-10-03. Application updates never update image libraries.

Sources:

- [pipx CLI](https://pipx.pypa.io/stable/reference/cli.html): `install --force`
  modifies an existing environment; install accepts VCS package specifications.
- [pipx upgrade implementation](https://github.com/pypa/pipx/blob/main/src/pipx/commands/upgrade.py):
  `_upgrade_package` passes stored `package_or_url` through `parse_specifier_for_upgrade`.
  A Git source is preserved, rather than implicitly switching to the package index.
- [pipx source installation examples](https://pipx.pypa.io/latest/how-to/install-pipx.html):
  Git URLs may include a branch, tag or commit reference.
- [GitHub releases API](https://docs.github.com/en/rest/releases/releases): structured
  release metadata includes draft/prerelease flags, a tag name, and wheel assets
  with a SHA-256 digest.

Decision: select the highest stable SemVer release using `packaging.version.Version`.
Do not use ordinary `pipx upgrade` to implement a stable-release channel: its stored
source could track an unreleased default branch or remain pinned to an earlier tag.
Download the exact wheel asset attached to the selected release, verify its size and
SHA-256 digest, then pass the local wheel to `pipx install --force`. This works for
pipx installations originally made from Git or a release wheel. No shell or Git
command is invoked.

Detection uses installed distribution metadata (`direct_url.json`) and the running
interpreter's `pipx_metadata.json`. Editable/non-pipx/suffixed/pinned/locked
installations are refused. pipx installations from a matching local release wheel
are accepted. `pipx environment --value PIPX_LOCAL_VENVS` must match
the running environment, preventing a different pipx installation from being modified.
The USB can hold `install-ventoy-library.sh`, which invokes NOAMi Installer to install
the latest published release wheel through pipx on the current computer. A pipx
installation from a temporary wheel has no durable source URL for ordinary pipx
upgrades; use `ventoy-library --update` for subsequent releases.
No live upgrade is run during development or tests; subprocess behavior is mocked.

Checks paginate release metadata (bounded at 1,000 entries, failing if incomplete),
ignore malformed version tags, honor prerelease/draft flags, and fall back to tags only
when there are no published releases. Invalid response shapes, API failures and rate
limits are failures, not “already up to date”. Tags must be stable X.Y.Z with optional v.

Limitations: future pipx metadata schema changes fail closed; Windows self-replacement
and actual released-package upgrade integration remain to validate. Updates are not
transactionally rolled back if package installation fails. GitHub release-asset digests
are used for integrity; signed application-release verification is not implemented.
