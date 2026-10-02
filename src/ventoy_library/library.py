"""Application service: plan first, validate space, then acquire/verify/install/record."""

import os
from datetime import UTC, datetime
from pathlib import Path

from .destinations import Target
from .downloader import HTTPDownloader, import_local
from .errors import SafetyError
from .models import AcquisitionMethod, ManagedImage, Plan
from .progress import Progress
from .safety import contained
from .state import StateStore
from .storage import inspect
from .verification import verify


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

        def update(offset, key=item.provider):
            if target_guard:
                target_guard.check_mount()
            progress.update(key, offset)
            on_progress(progress.render(key))

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
