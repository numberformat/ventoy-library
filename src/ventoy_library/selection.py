"""Numbered presentation and deterministic selection parsing."""

import re
from datetime import datetime

from .errors import LibraryError
from .models import ManagedImage
from .providers.base import Provider


def select_numbers(value: str, providers: list[Provider]) -> list[Provider]:
    """Accept 1,3,5-7, whitespace, or 0/all; return catalog order, without duplicates."""
    value = value.strip().lower()
    if value in {"0", "all"}:
        return list(providers)
    if not value:
        raise LibraryError("Select image numbers (e.g. 1,3,9-11), or 0 for all.")
    if not re.fullmatch(r"\d+(?:-\d+)?(?:(?:\s*,\s*|\s+)\d+(?:-\d+)?)*", value):
        raise LibraryError("Use numbers, comma-separated choices or ranges (e.g. 1,3,9-11).")
    selected = set()
    for token in re.split(r"[\s,]+", value):
        ends = token.split("-")
        start, stop = int(ends[0]), int(ends[-1])
        if not 1 <= start <= stop <= len(providers):
            raise LibraryError(
                f"Image numbers must be between 1 and {len(providers)}; 0 selects all."
            )
        selected.update(range(start, stop + 1))
    return [p for number, p in enumerate(providers, 1) if number in selected]


def show_catalog(
    providers: list[Provider],
    images: list[ManagedImage],
    names: list[str] | None = None,
    visible_names: set[str] | None = None,
) -> None:
    latest = {i.provider: i for i in images}
    print(
        "  #  IMAGE                      CATEGORY   ARCH     ACQUISITION  "
        "VERSION      INSTALLED    DATE"
    )
    for number, provider in enumerate(providers, 1):
        if names and provider.name not in names:
            continue
        if visible_names is not None and provider.name not in visible_names:
            continue
        previous = latest.get(provider.name)
        mode = (
            "catalog"
            if getattr(provider, "snapshot", False)
            else "manual"
            if getattr(provider, "manual", False)
            else "automatic"
        )
        snapshot = getattr(provider, "release", None)
        version = (
            snapshot.version
            if snapshot
            else getattr(provider, "catalog_version", None)
            or (previous.version if previous else "-")
        )
        installed_date = _display_date(previous.download_timestamp) if previous else "-"
        catalog_date = getattr(provider, "researched_at", None)
        date_value = (
            installed_date if previous else catalog_date.isoformat() if catalog_date else "-"
        )
        print(
            f"{number:3}  {provider.display_name:26} {provider.category:10} "
            f"{provider.architecture:8} {mode:12} {version:12} "
            f"{previous.version if previous else '-':12} {date_value}"
        )
    print("\n  0  All available images" if visible_names is not None else "\n  0  All images")
    print("Date: download date for installed images; catalog research date otherwise.")


def _display_date(value: str) -> str:
    """Format a managed image timestamp as a compact local-independent date."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value[:10] if len(value) >= 10 else value


def prompt_selection(
    providers: list[Provider], images: list[ManagedImage], visible_names: set[str] | None = None
) -> list[Provider]:
    show_catalog(providers, images, visible_names=visible_names)
    while True:
        value = input("Choose images (e.g. 1,3,9-11; 0 = all; q = cancel): ").strip()
        if value.lower() in {"q", "quit", "cancel"}:
            return []
        try:
            selected = select_numbers(value, providers)
            if visible_names is not None:
                if value.strip().lower() in {"0", "all"}:
                    return [provider for provider in selected if provider.name in visible_names]
                if any(provider.name not in visible_names for provider in selected):
                    raise LibraryError("Choose only numbers shown in the catalog.")
            return selected
        except LibraryError as exc:
            print(f"{exc} Please try again.")
