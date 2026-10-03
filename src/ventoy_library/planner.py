from dataclasses import replace
from pathlib import Path

import httpx

from .errors import LibraryError
from .models import AcquisitionMethod, Action, ManagedImage, Plan, PlannedDownload
from .providers.base import Provider
from .providers.manual import ManualProvider, ManualRequired
from .safety import contained, image_path


def build_plan(
    providers: list[Provider],
    root: Path,
    installed: list[ManagedImage],
    overrides: dict[str, str] | None = None,
    size_probe=None,
) -> Plan:
    overrides = overrides or {}
    unknown = overrides.keys() - {p.name for p in providers}
    if unknown:
        raise LibraryError(f"Overrides refer to unselected providers: {', '.join(sorted(unknown))}")
    items = []
    claimed_targets: set[str] = set()
    for provider in providers:
        previous = next((i for i in reversed(installed) if i.provider == provider.name), None)
        try:
            if isinstance(provider, ManualProvider) and provider.name in overrides:
                release = provider.release_from_source(overrides[provider.name])
            else:
                release = provider.get_latest_release()
            if (
                release.provider != provider.name
                or release.category != provider.category
                or release.architecture != provider.architecture
            ):
                raise LibraryError("Provider returned mismatched release identity.")
            target = image_path(root, release.filename)
            if any(
                image.provider != provider.name
                and Path(image.relative_path).parent == Path("ISO")
                and image.filename.casefold() == release.filename.casefold()
                for image in installed
            ):
                raise LibraryError("Top-level filename is tracked by another provider.")
            if target.name.casefold() in claimed_targets:
                raise LibraryError("Another selected provider uses the same ISO filename.")
            source = overrides.get(provider.name, release.url)
            method = AcquisitionMethod.AUTOMATIC
            if provider.name in overrides:
                if source.startswith(("http://", "https://")):
                    from .models import http_url

                    http_url(source)
                    method = AcquisitionMethod.ALTERNATE_URL
                else:
                    local = Path(source).expanduser()
                    if local.is_symlink() or not local.is_file():
                        raise LibraryError("Local source must be a regular file, not a symlink.")
                    size = local.stat().st_size
                    if release.size is not None and size != release.size:
                        raise LibraryError("Local file size differs from upstream metadata.")
                    release = replace(release, size=size)
                    source = str(local.absolute())
                    method = AcquisitionMethod.LOCAL_FILE
            if release.size is None and source and method != AcquisitionMethod.LOCAL_FILE:
                if size_probe:
                    release = replace(release, size=size_probe(source))
            current = False
            if previous and previous.version == release.version and provider.name not in overrides:
                old_path = contained(root, previous.relative_path)
                current = (
                    old_path.is_file()
                    and previous.filename == release.filename
                    and previous.checksum == release.checksum
                    and previous.checksum_algorithm == release.checksum_algorithm
                    and (release.size is None or old_path.stat().st_size == release.size)
                )
            if current:
                action = Action.CURRENT if old_path == target else Action.RELOCATE
            elif target.exists():
                if (
                    not target.is_file()
                    or release.checksum is None
                    or provider.name in overrides
                    or (previous and previous.relative_path == target.relative_to(root).as_posix())
                ):
                    raise LibraryError(
                        "Top-level target exists; a matching upstream checksum is required "
                        "to adopt it safely."
                    )
                if release.size is not None and target.stat().st_size != release.size:
                    raise LibraryError("Existing top-level image has the wrong size.")
                action = Action.ADOPT
            else:
                action = (
                    Action.MANUAL
                    if source is None
                    else Action.UPDATE
                    if previous
                    else Action.DOWNLOAD
                )
            if action != Action.MANUAL:
                claimed_targets.add(target.name.casefold())
            items.append(
                PlannedDownload(provider.name, release, target, action, previous, source, method)
            )
        except ManualRequired as exc:
            items.append(
                PlannedDownload(provider.name, None, None, Action.MANUAL, previous, reason=str(exc))
            )
        except (LibraryError, httpx.HTTPError, OSError, ValueError) as exc:
            items.append(
                PlannedDownload(provider.name, None, None, Action.ERROR, previous, reason=str(exc))
            )
    return Plan(tuple(items))
