"""Offline numbered presentation and deterministic selection parsing."""

import re

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
    providers: list[Provider], images: list[ManagedImage], names: list[str] | None = None
) -> None:
    latest = {i.provider: i for i in images}
    print("  #  IMAGE                      CATEGORY   ARCH     ACQUISITION  INSTALLED")
    for number, provider in enumerate(providers, 1):
        if names and provider.name not in names:
            continue
        previous = latest.get(provider.name)
        mode = (
            "catalog"
            if getattr(provider, "snapshot", False)
            else "manual"
            if getattr(provider, "manual", False)
            else "automatic"
        )
        version = previous.version if previous else "-"
        print(
            f"{number:3}  {provider.display_name:26} {provider.category:10} "
            f"{provider.architecture:8} {mode:12} {version}"
        )
    print("\n  0  All images")


def prompt_selection(providers: list[Provider], images: list[ManagedImage]) -> list[Provider]:
    show_catalog(providers, images)
    while True:
        value = input("Choose images (e.g. 1,3,9-11; 0 = all; q = cancel): ").strip()
        if value.lower() in {"q", "quit", "cancel"}:
            return []
        try:
            return select_numbers(value, providers)
        except LibraryError as exc:
            print(f"{exc} Please try again.")
