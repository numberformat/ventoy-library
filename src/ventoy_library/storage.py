import shutil
from dataclasses import dataclass
from pathlib import Path

from .errors import SafetyError
from .models import Plan
from .safety import destination


@dataclass(frozen=True)
class StorageReport:
    capacity: int
    used: int
    available: int
    managed_bytes: int
    download_bytes: int | None
    safety_margin: int

    @property
    def required_free(self) -> int | None:
        return None if self.download_bytes is None else self.download_bytes + self.safety_margin

    @property
    def projected_free(self) -> int | None:
        return None if self.download_bytes is None else self.available - self.download_bytes

    @property
    def shortfall(self) -> int | None:
        return None if self.required_free is None else max(0, self.required_free - self.available)

    def require_safe(self) -> None:
        if self.required_free is None:
            raise SafetyError("Unknown image sizes: cannot prove sufficient storage; no downloads.")
        if self.shortfall:
            raise SafetyError(f"Insufficient space: shortfall {self.shortfall} bytes.")


def inspect(root: Path, plan: Plan, margin: int, managed_bytes: int = 0) -> StorageReport:
    if margin < 0:
        raise SafetyError("Safety margin cannot be negative.")
    usage = shutil.disk_usage(destination(root))
    return StorageReport(
        usage.total, usage.used, usage.free, managed_bytes, plan.total_bytes, margin
    )
