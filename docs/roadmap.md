# Project status and roadmap

Last updated: 2026-10-01

This document records the implementation status and the next work in priority
order. The README describes user-facing behavior; this page tracks development
milestones and known validation gaps.

## Current status

The Phase 1 core architecture is in place: Python packaging and CLI, per-user
configuration, provider registry, preflight planning and storage checks, streaming
downloads, progress reporting, SHA256/SHA512 verification, atomic state, and guarded
application self-update.

The representative-provider phase is implemented for Arch Linux, SystemRescue,
Ubuntu Server LTS, and Ubuntu Desktop LTS. Their adapters use official release
metadata and provide size/checksum information. The numbered catalog contains 24
projects; the other entries currently support manual local-file or URL acquisition
by default. A YAML release catalog ships in the package and can supply
release snapshots for them after a new application release, without claiming
live discovery. See [provider research](providers.md) for the implemented
providers and their sources.

Ventoy is the default destination mode. The application detects candidate mounted
data partitions, prompts for a drive or path when needed, and checks plans against
Ventoy search and filtering settings. Ordinary filesystem directories require an
explicit directory mode. The safety buffer is optional to configure and defaults to
2 GiB.

## Provider URL policy

The long-term goal is to keep each provider pointed at an official upstream location
that continues to serve the latest stable boot image, with as little project-side
release maintenance as possible. During research, prefer an official stable `latest`
endpoint, download alias, or redirect when upstream documents it and its behavior can
be verified. Do not assume that a URL containing the word `latest` actually tracks a
stable release.

When no reliable latest-artifact URL exists, use official structured release metadata
or an official release index to discover the current stable version and its artifact
each time the provider runs. Do not bake a version-specific download URL into the
catalog or silently fall back to an old one. If neither route is dependable, keep the
entry manual and explain why.

Resolve the selected artifact before planning storage. Obtain its size and checksum
from upstream metadata or manifests tied to that same release; a stable redirect alone
may not provide enough information to identify or verify the image. Record both the
discovery URL and resolved artifact behavior in provider research notes, along with
how stable releases, architecture, and bootable formats are selected. Fixtures should
cover the documented metadata shape and failure cases, while recognizing that mocked
tests do not prove an upstream endpoint is still current. Refresh the research date
when checking a provider against its live official source.

The current automatic providers discover release metadata at runtime and select
versioned artifacts from it. They do not yet share one universal “latest URL” format;
their current discovery mechanisms are documented in [provider research](providers.md).
For projects without reliable live discovery, the
[release catalog workflow](release-refresh-prompt.md) supports periodic human updates.

## Next steps

1. **Validate Ventoy detection on real systems.** Exercise detection and image
   visibility on macOS, Linux, and Windows with actual Ventoy media. Current tests use
   synthetic partition metadata and temporary directories; no Ventoy drive was
   attached during development. In particular, verify Windows volume metadata and
   filesystem behavior against a live installation.
2. **Harden transfer recovery.** Add interactive local-file/alternate-URL/skip
   fallback after an automatic transfer fails, plus a useful multi-image completion
   summary when individual transfers fail.
3. **Expand failure testing.** Exercise disk-full and unplug/remount behavior during
   real transfers, and verify assumptions around network filesystem space reporting,
   rename, and lock behavior. Current mount checks reduce risk but cannot eliminate
   every concurrent unplug or remount race.
4. **Add automatic providers one at a time.** Apply the provider URL policy above.
   Record the current official source, whether a stable latest endpoint exists,
   stable x86-64 artifact rules, size and checksum sources, and limitations. Add
   fixture-based tests before registering the provider. Keep projects manual where
   official discovery is unreliable. The [ChatGPT research prompt](release-refresh-prompt.md)
   can help prepare a sourced YAML snapshot for human review during periodic refreshes.
5. **Smoke-test application self-update after a stable release exists.** Confirm
   the published GitHub tag and pipx Git installation flow end to end. Also verify
   repeat installation through NOAMi Installer using the attached wheel.

No real multi-gigabyte images are needed for these tasks; network and transfer tests
should continue to use mocked responses and small fixtures.
