"""Application service: plan first, validate space, then acquire/verify/install/record."""

import os
import time
from datetime import UTC, datetime
from pathlib import Path

from .destinations import Target
from .downloader import HTTPDownloader, import_local
from .errors import SafetyError
from .models import AcquisitionMethod, Action, ManagedImage, Plan
from .progress import Progress
from .safety import contained
from .state import StateStore
from .storage import inspect
from .verification import verify

PROGRESS_INTERVAL_SECONDS = 3.0


def execute(
    plan: Plan,
    root: Path,
    store: StateStore,
    downloader: HTTPDownloader,
    margin: int,
    *,
    keep_old: bool = False,
    on_progress=lambda text: None,
    target_guard: Target | None = None,
) -> list[ManagedImage]:
    """Caller holds store.lock() across planning and execution. Errors preserve old images."""
    if target_guard:
        target_guard.validate_plan(plan)
    inspect(root, plan, margin).require_safe()
    progress = Progress({item.provider: item.release.size for item in plan.downloads})
    installed = []
    for item in plan.items:
        if item.action not in {Action.RELOCATE, Action.ADOPT}:
            continue
        release = item.release
        target = contained(root, item.destination.relative_to(root))
        if target_guard:
            target_guard.validate_plan(Plan((item,)))
        old = item.installed
        if old and old not in store.load():
            raise SafetyError("Relocation source is not tracked in library state.")
        moved = False
        if item.action == Action.RELOCATE:
            old_path = contained(root, old.relative_path)
            status = verify(old_path, release.checksum_algorithm, release.checksum, release.size)
            if target.exists() and release.checksum is None:
                raise SafetyError(
                    "Cannot reconcile an existing top-level image without an upstream checksum."
                )
        if item.action == Action.ADOPT or target.exists():
            status = verify(target, release.checksum_algorithm, release.checksum, release.size)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            # The writer lock coordinates this application; recheck before renaming.
            if target.exists():
                raise SafetyError("Top-level target appeared during relocation.")
            os.rename(old_path, target)
            moved = True
        timestamp = (
            old.download_timestamp
            if item.action == Action.RELOCATE
            else datetime.now(UTC).isoformat()
        )
        method = (
            old.acquisition_method
            if item.action == Action.RELOCATE
            else AcquisitionMethod.EXISTING_FILE
        )
        record = ManagedImage(
            release.provider,
            release.display_name,
            release.version,
            release.filename,
            target.relative_to(root).as_posix(),
            old.source_url if item.action == Action.RELOCATE else release.url,
            release.size,
            release.checksum_algorithm,
            release.checksum,
            timestamp,
            status,
            method,
        )
        if moved:
            try:
                store.save([i for i in store.load() if i != old] + [record])
            except Exception:
                os.rename(target, old_path)
                raise
        else:
            store.save([*store.load(), record])
            if old:
                store.remove_old(old, record, keep_old=keep_old)
        installed.append(record)
    for item in plan.downloads:
        release = item.release
        target = contained(root, item.destination.relative_to(root))
        if target.exists():
            raise SafetyError("Refusing to overwrite an existing target.")
        # Recheck free space between files. No credit for partials or future old-file cleanup.
        single = Plan((item,))
        if target_guard:
            target_guard.validate_plan(single)
        inspect(root, single, margin).require_safe()
        part = contained(root, str(target.relative_to(root)) + ".part")
        last_report_at: float | None = None
        last_reported_offset: int | None = None

        def update(offset, key=item.provider, expected_size=release.size):
            nonlocal last_report_at, last_reported_offset
            if target_guard:
                target_guard.check_mount()
            progress.update(key, offset)
            now = time.monotonic()
            finished = expected_size is not None and offset == expected_size
            if last_reported_offset != offset and (
                last_report_at is None
                or now - last_report_at >= PROGRESS_INTERVAL_SECONDS
                or finished
            ):
                on_progress(progress.render(key))
                last_report_at = now
                last_reported_offset = offset

        if item.acquisition_method == AcquisitionMethod.LOCAL_FILE:
            import_local(Path(item.source), root, part, release.size, update)
        else:
            downloader.fetch(release, item.source, root, part, update)
        status = verify(part, release.checksum_algorithm, release.checksum, release.size)
        if target_guard:
            target_guard.validate_plan(single)
        # Revalidate following network IO. A cooperating writer holds the library lock.
        target = contained(root, target.relative_to(root))
        contained(root, part.relative_to(root))
        if target.exists():
            raise SafetyError("Target appeared during acquisition; refusing replacement.")
        os.rename(part, target)
        record = ManagedImage(
            release.provider,
            release.display_name,
            release.version,
            release.filename,
            target.relative_to(root).as_posix(),
            None if item.acquisition_method == AcquisitionMethod.LOCAL_FILE else item.source,
            release.size,
            release.checksum_algorithm,
            release.checksum,
            datetime.now(UTC).isoformat(),
            status,
            item.acquisition_method,
        )
        store.save([*store.load(), record])
        installed.append(record)
        marker = contained(root, str(part.relative_to(root)) + ".json")
        if item.acquisition_method != AcquisitionMethod.LOCAL_FILE and marker.exists():
            marker.unlink()
        if item.installed:
            store.remove_old(item.installed, record, keep_old=keep_old)
    return installed
