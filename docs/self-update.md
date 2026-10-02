# Application updater research

Reviewed 2026-09-29. Application updates never update image libraries.

Sources:

- [pipx CLI](https://pipx.pypa.io/stable/reference/cli.html): `install --force`
  modifies an existing environment; install accepts VCS package specifications.
- [pipx upgrade implementation](https://github.com/pypa/pipx/blob/main/src/pipx/commands/upgrade.py):
  `_upgrade_package` passes stored `package_or_url` through `parse_specifier_for_upgrade`.
  A Git source is preserved, rather than implicitly switching to the package index.
- [pipx source installation examples](https://pipx.pypa.io/latest/how-to/install-pipx.html):
  Git URLs may include a branch, tag or commit reference.
- [GitHub releases API](https://docs.github.com/en/rest/releases/releases): structured
  release metadata includes draft/prerelease flags and a tag name.

Decision: select the highest stable SemVer release using `packaging.version.Version`.
Do not use ordinary `pipx upgrade` to implement a stable-release channel: its stored
source could track an unreleased default branch or remain pinned to an earlier tag.
Use `pipx install --force git+https://github.com/numberformat/ventoy-library.git@TAG`.
There is no assumption that `pipx upgrade --spec` is supported. The tag is strictly
validated before inclusion as a subprocess argument, and no shell is invoked.

Detection uses installed distribution metadata (`direct_url.json`) and the running
interpreter's `pipx_metadata.json`. Editable/local/non-pipx/suffixed/pinned/locked
installations are refused. `pipx environment --value PIPX_LOCAL_VENVS` must match
the running environment, preventing a different pipx installation from being modified.
No live upgrade is run during development or tests; subprocess behavior is mocked.

Checks paginate release metadata (bounded at 1,000 entries, failing if incomplete),
ignore malformed version tags, honor prerelease/draft flags, and fall back to tags only
when there are no published releases. Invalid response shapes, API failures and rate
limits are failures, not “already up to date”. Tags must be stable X.Y.Z with optional v.

Limitations: future pipx metadata schema changes fail closed; Windows self-replacement
and actual released-package upgrade integration remain to validate. Force-install is a
pipx operation, not an application-managed transactional rollback. Git tags must not
be retargeted; signed application-release verification is not implemented.
