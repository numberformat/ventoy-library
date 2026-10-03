from dataclasses import dataclass, field


def format_bytes(value: int | None) -> str:
    if value is None:
        return "UNKNOWN"
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(size) < 1024 or unit == "PiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    raise AssertionError("unreachable")


@dataclass
class Progress:
    """Absolute per-file offsets avoid double counting resumed/restarted transfers."""

    sizes: dict[str, int | None]
    offsets: dict[str, int] = field(default_factory=dict)

    def update(self, key: str, offset: int) -> None:
        if key not in self.sizes or offset < 0:
            raise ValueError("Invalid progress event.")
        size = self.sizes[key]
        if size is not None and offset > size:
            raise ValueError("Progress exceeds expected size.")
        self.offsets[key] = offset

    @property
    def downloaded(self) -> int:
        return sum(self.offsets.values())

    @property
    def total(self) -> int | None:
        return None if None in self.sizes.values() else sum(self.sizes.values())

    @property
    def percentage(self) -> float | None:
        if self.total is None:
            return None
        return 100 * self.downloaded / self.total if self.total else 100.0

    def render(self, key: str) -> str:
        percentage = "" if self.percentage is None else f" ({self.percentage:.1f}%)"
        overall = (
            f"Overall: {format_bytes(self.downloaded)} / {format_bytes(self.total)}{percentage}"
        )
        if self.total is None:
            overall += f"; {list(self.sizes.values()).count(None)} files have unknown sizes"
        size = self.sizes[key]
        file_percentage = (
            ""
            if size is None
            else f" ({100 * self.offsets.get(key, 0) / size if size else 100:.1f}%)"
        )
        return (
            f"{overall} | Current: {key}: {format_bytes(self.offsets.get(key, 0))}"
            f" / {format_bytes(size)}{file_percentage}"
        )
