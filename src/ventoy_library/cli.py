import argparse
import json
import logging
import sys
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

import httpx

from . import app_update, config
from .availability import check_download
from .availability_cache import available_names
from .destinations import current_ventoy_root, resolve_target
from .downloader import HTTPDownloader, http_client
from .errors import LibraryError
from .library import execute
from .metadata import PROJECT_NAME, __version__
from .models import Action, Plan, PlannedDownload, http_url
from .planner import build_plan
from .progress import format_bytes
from .providers import default_registry
from .release_catalog import load_bundled_catalog, load_catalog
from .safety import contained, destination
from .selection import prompt_selection, select_numbers, show_catalog
from .state import StateStore
from .storage import inspect


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        prog=PROJECT_NAME,
        description=(
            "Choose, download and manage bootable images on an ordinary filesystem directory."
        ),
    )
    application = cli.add_mutually_exclusive_group()
    application.add_argument("--version", action="version", version=f"{PROJECT_NAME} {__version__}")
    application.add_argument(
        "--check-update", action="store_true", help="check application releases"
    )
    application.add_argument(
        "--update", action="store_true", help="update application from its GitHub Release wheel"
    )
    cli.add_argument("--yes", action="store_true", help="confirm an application update")
    cli.add_argument("-v", "--verbose", action="count", default=0)
    commands = cli.add_subparsers(dest="command")
    cfg = commands.add_parser("config", help="manage per-user configuration")
    cfg_commands = cfg.add_subparsers(dest="config_command", required=True)
    cfg_commands.add_parser("show")
    setter = cfg_commands.add_parser("set")
    setter.add_argument(
        "key", choices=["destination", "destination_mode", "safety_margin", "release_catalog"]
    )
    setter.add_argument(
        "value",
        help="destination/catalog path, mode (ventoy/directory), or safety margin in GiB",
    )
    for name in ("list", "status", "check", "add", "update-images"):
        sub = commands.add_parser(name)
        sub.add_argument("--destination", type=Path, help="override the configured destination")
        sub.add_argument(
            "--release-catalog", type=Path, help="use a YAML release catalog for this run"
        )
        modes = sub.add_mutually_exclusive_group()
        modes.add_argument(
            "--directory",
            dest="destination_mode",
            action="store_const",
            const="directory",
            help="explicit ordinary-folder library mode",
        )
        modes.add_argument(
            "--ventoy",
            dest="destination_mode",
            action="store_const",
            const="ventoy",
            help="require a mounted Ventoy data partition (default)",
        )
        selection = sub.add_mutually_exclusive_group()
        selection.add_argument(
            "--only", action="append", help="provider ID; repeat to select several"
        )
        if name != "status":
            sub.add_argument(
                "--refresh-links",
                action="store_true",
                help="recheck image links now instead of using the three-day cache",
            )
        if name in {"check", "add", "update-images"}:
            selection.add_argument(
                "--select", metavar="NUMBERS", help="catalog numbers, e.g. 1,3,9-11; 0 selects all"
            )
            selection.add_argument("--all", action="store_true", help="select all available images")
        if name == "check":
            sub.add_argument(
                "--downloads",
                action="store_true",
                help="check image URLs with HEAD requests; no destination or image download",
            )
            sub.add_argument(
                "--exclude", action="append", metavar="PROVIDER", help="omit a provider from checks"
            )
            sub.add_argument(
                "--url", action="append", default=[], metavar="PROVIDER=URL",
                help="probe an alternate HTTP(S) URL for one provider",
            )
        sub.add_argument("-v", "--verbose", action="count", default=argparse.SUPPRESS)
        if name in {"add", "update-images"}:
            sub.add_argument("--dry-run", action="store_true")
            sub.add_argument("--keep-old", action="store_true")
            sub.add_argument(
                "--no-interactive",
                action="store_true",
                help="execute without prompting; fail when input would be required",
            )
            sub.add_argument("--local", action="append", default=[], metavar="PROVIDER=PATH_OR_URL")
    return cli


def overrides(values: list[str], option: str = "--local") -> dict[str, str]:
    result = {}
    for value in values:
        key, sep, source = value.partition("=")
        if not key or not sep or not source or key in result:
            value_hint = "URL" if option == "--url" else "PATH_OR_URL"
            raise LibraryError(f"Use each {option} PROVIDER={value_hint} exactly once.")
        result[key] = source
    return result


def manual_choices(providers, sources):
    """Resolve manual inputs before planning so every selected byte is accounted for."""
    sources = dict(sources)
    active, skipped = [], []
    for provider in providers:
        if not getattr(provider, "manual", False) or provider.name in sources:
            active.append(provider)
            continue
        print(f"\n{provider.display_name}: automatic discovery is not implemented.")
        print(f"Choose an official stable bootable image for {provider.architecture}.")
        print("1. Provide local file\n2. Provide direct download URL\n3. Skip")
        while True:
            choice = input("Choice [3]: ").strip() or "3"
            if choice == "3":
                skipped.append(provider.name)
                break
            if choice in {"1", "2"}:
                source = input("Local file: " if choice == "1" else "Download URL: ").strip()
                if not source:
                    print("Enter a source, or choose 3 to skip.")
                    continue
                if choice == "2" and not source.startswith(("https://", "http://")):
                    print("Enter an HTTP(S) URL.")
                    continue
                sources[provider.name] = source
                active.append(provider)
                break
            print("Choose 1, 2 or 3.")
    return active, sources, skipped


def show_storage(report) -> None:
    for label, value in (
        ("Capacity", report.capacity),
        ("Used", report.used),
        ("Available", report.available),
        ("Managed images", report.managed_bytes),
        ("Downloads required / peak additional space", report.download_bytes),
        ("Safety buffer (kept free after downloads)", report.safety_margin),
        ("Required free", report.required_free),
        ("Projected free before cleanup", report.projected_free),
        ("Shortfall", report.shortfall),
    ):
        print(f"{label}: {format_bytes(value)}")
    print(
        "Space check: "
        + ("UNKNOWN" if report.required_free is None else "FAILED" if report.shortfall else "OK")
    )


def show_plan(plan: Plan, keep_old: bool = False) -> None:
    print("PROVIDER          INSTALLED    AVAILABLE    SIZE           ACTION")
    for item in plan.items:
        release = item.release
        print(
            f"{item.provider:17} {item.installed.version if item.installed else '-':12} "
            f"{release.version if release else '-':12} "
            f"{format_bytes(release.size if release else None):14} {item.action}"
        )
        if release:
            print(f"  File: {release.filename}\n  Destination: {item.destination}")
            source = (
                "existing local image"
                if item.action in {Action.RELOCATE, Action.ADOPT}
                else item.source or "manual required"
            )
            print(f"  Source: {source}")
            if release.checksum is None:
                print("  No authoritative checksum available; installation will be UNVERIFIED.")
        if item.action == Action.RELOCATE:
            print("  Existing managed image will move to ISO/ after verification.")
        if item.action == Action.ADOPT:
            print("  Existing top-level image will be checked before adding it to state.")
        if item.reason:
            print(f"  {item.reason}")
        if (
            item.action in {Action.UPDATE, Action.RELOCATE, Action.ADOPT}
            and item.installed
            and not keep_old
        ):
            print(f"  Remove after successful replacement: {item.installed.relative_path}")
    print(f"Downloads: {len(plan.downloads)}; download size: {format_bytes(plan.total_bytes)}")
    if any(i.action in {Action.MANUAL, Action.ERROR} for i in plan.items):
        print("Unresolved images are excluded from the download total and will not be downloaded.")


def application_update(args) -> int:
    with http_client() as client:
        release = app_update.latest_release(client)
    installed = app_update.installed_version()
    print(f"Installed application: {installed}")
    print(f"Latest release:        {release.version if release else 'No stable releases/tags'}")
    if not release or release.version <= installed:
        print("No application update available.")
        return 0
    print("Application update available.")
    if not args.update:
        return 0
    executable = app_update.update_executable(release)
    print(f"Release wheel: {release.wheel_name}")
    if not args.yes:
        if not sys.stdin.isatty():
            raise LibraryError("Application update needs confirmation; use --update --yes.")
        if input("Update the application? [y/N] ").strip().lower() not in {"y", "yes"}:
            return 0
    with tempfile.TemporaryDirectory(prefix="ventoy-library-update-") as temp_dir:
        with http_client() as client:
            wheel = app_update.download_release_wheel(client, release, Path(temp_dir))
        return app_update.run_update(app_update.update_command(executable, wheel))


def check_downloads(args, catalog, registry, document) -> int:
    """Check advertised artifacts without selecting a drive or writing library state."""
    if args.only:
        providers = registry.select(args.only)
    elif args.select is not None:
        providers = select_numbers(args.select, catalog)
    else:
        providers = catalog
    excluded = {p.name for p in registry.select(args.exclude)} if args.exclude else set()
    providers = [p for p in providers if p.name not in excluded]
    urls = overrides(args.url, "--url")
    for url in urls.values():
        http_url(url)
    unknown = urls.keys() - {p.name for p in providers}
    if unknown:
        raise LibraryError(
            f"URL overrides refer to unselected providers: {', '.join(sorted(unknown))}"
        )
    failures: list[tuple[str, str]] = []
    skipped: list[str] = []
    available = 0
    print(
        f"Checking {len(providers)} image sources with HEAD requests; "
        "no image files will be downloaded."
    )
    with http_client() as client:
        for provider in providers:
            try:
                if provider.manual:
                    release = (document.manual_sources or {}).get(provider.name)
                    if release is None and provider.name in urls:
                        release = provider.release_from_source(urls[provider.name])
                    if release is None:
                        print(f"{provider.name}: SKIPPED (no catalog or supplied URL)")
                        skipped.append(provider.name)
                        continue
                else:
                    release = provider.get_latest_release()
                if (
                    release.provider != provider.name
                    or release.category != provider.category
                    or release.architecture != provider.architecture
                ):
                    raise LibraryError("Provider returned mismatched release identity.")
                if provider.name in urls:
                    release = replace(release, url=urls[provider.name])
                result = check_download(client, release)
            except (LibraryError, httpx.HTTPError, OSError, ValueError) as exc:
                print(f"{provider.name}: UNAVAILABLE ({exc})")
                failures.append((provider.name, str(exc)))
                continue
            if not result.available:
                failures.append((provider.name, result.detail))
            else:
                available += 1
            label = "AVAILABLE" if result.available else "UNAVAILABLE"
            kind = "manual package" if provider.manual else "image"
            print(
                f"{provider.name}: {label} | {kind} {release.filename} | "
                f"version {release.version} | "
                f"{format_bytes(result.size)} | {result.detail} | {release.url or '-'}"
            )
    print(
        f"Availability check complete: {available} available, "
        f"{len(failures)} unavailable, {len(skipped)} skipped."
    )
    if failures:
        print("Failed image sources:")
        for name, reason in failures:
            print(f"  {name}: {reason}")
    if skipped:
        print("Not testable automatically: " + ", ".join(skipped))
    return int(bool(failures or skipped))


def run(args) -> int:
    if args.check_update or args.update:
        if args.command:
            raise LibraryError("Application update flags cannot be combined with image commands.")
        return application_update(args)
    if args.yes:
        raise LibraryError("--yes applies only to --update.")
    if args.command == "check" and (args.exclude or args.url) and not args.downloads:
        raise LibraryError("--exclude and --url require check --downloads.")
    if args.command == "config":
        cfg = (
            config.set_value(args.key, args.value)
            if args.config_command == "set"
            else config.load()
        )
        print(json.dumps(asdict(cfg), indent=2))
        return 0
    cfg = config.load()
    catalog_path = getattr(args, "release_catalog", None) or cfg.release_catalog
    document = load_catalog(Path(catalog_path)) if catalog_path else load_bundled_catalog()
    registry = default_registry()
    if document.releases or document.versions or document.researched_at:
        registry.add_snapshots(document.releases, document.researched_at, document.versions)
    catalog = registry.select()
    if document.releases:
        print(
            f"Release catalog loaded ({len(document.releases)} candidate snapshots)"
        )
    if args.command == "check" and args.downloads:
        return check_downloads(args, catalog, registry, document)
    mode = args.destination_mode or cfg.destination_mode
    chosen = args.destination or cfg.destination
    # Listing needs no mounted drive or prompt; link checks use a per-user cache.
    if args.command == "list":
        if args.destination is None and mode == "ventoy":
            chosen = current_ventoy_root() or chosen
        images = []
        if chosen:
            try:
                images = StateStore(destination(chosen)).load()
                print(f"Destination: {chosen}")
            except (LibraryError, OSError) as exc:
                print(f"Installed status unavailable: {exc}")
        if args.only:
            registry.select(args.only)
        visible = available_names(
            registry.select(args.only) if args.only else catalog,
            document,
            refresh=args.refresh_links,
        )
        show_catalog(catalog, images, names=args.only, visible_names=visible)
        if not visible:
            print(
                "No image links could be confirmed. "
                "Check your connection or use --refresh-links."
            )
        print("Run 'ventoy-library add' to choose images and check storage before downloading.")
        return 0
    target_guard = resolve_target(
        chosen,
        mode=mode,
        interactive=sys.stdin.isatty() and not getattr(args, "no_interactive", False),
        prefer_current_directory=args.destination is None,
    )
    if target_guard is None:
        print("Cancelled.")
        return 0
    root = target_guard.root
    store = StateStore(root)
    images = store.load()
    print(f"Destination: {root}")
    print(
        "Mode: Ventoy data partition"
        if target_guard.ventoy
        else "Mode: ordinary directory (not a Ventoy boot library)"
    )
    managed_bytes = sum(
        contained(root, i.relative_path).stat().st_size
        for i in images
        if contained(root, i.relative_path).is_file()
    )
    if args.command == "status":
        print("PROVIDER          INSTALLED    VERIFIED      SIZE           PATH")
        for image in images:
            if not args.only or image.provider in args.only:
                print(
                    f"{image.provider:17} {image.version:12} {image.verification_status:13} "
                    f"{format_bytes(image.expected_size):14} {image.relative_path}"
                )
        show_storage(inspect(root, Plan(()), cfg.safety_margin, managed_bytes))
        return 0
    manual = overrides(getattr(args, "local", []))
    # Numeric keys in --local use the same catalog numbers as the interactive menu.
    normalized = {}
    for key, source in manual.items():
        if key.isdecimal():
            matches = select_numbers(key, catalog)
            if len(matches) != 1:
                raise LibraryError("Each --local argument must identify exactly one image.")
            key = matches[0].name
        if key in normalized:
            raise LibraryError(f"Duplicate local override for {key}.")
        normalized[key] = source
    manual = normalized
    if args.only:
        providers = registry.select(args.only)
    elif args.select is not None:
        providers = select_numbers(args.select, catalog)
    elif args.all:
        visible = available_names(catalog, document, refresh=args.refresh_links)
        providers = [provider for provider in catalog if provider.name in visible]
    elif manual:
        providers = registry.select(list(manual))
    elif args.command in {"add", "update-images"} and not args.dry_run:
        if args.no_interactive or not sys.stdin.isatty():
            raise LibraryError("Choose images with --select NUMBERS, --all, --only, or --local.")
        visible = available_names(catalog, document, refresh=args.refresh_links)
        if not visible:
            raise LibraryError(
                "No image links could be confirmed. "
                "Check your connection or use --only with a local file."
            )
        providers = prompt_selection(catalog, images, visible_names=visible)
        if not providers:
            print("Cancelled.")
            return 0
    else:
        visible = available_names(catalog, document, refresh=args.refresh_links)
        providers = [provider for provider in catalog if provider.name in visible]
    if manual.keys() - {p.name for p in providers}:
        raise LibraryError("Manual overrides must name selected providers.")
    skipped = []
    if (
        args.command in {"add", "update-images"}
        and not args.dry_run
        and not args.no_interactive
        and sys.stdin.isatty()
    ):
        providers, manual, skipped = manual_choices(providers, manual)
    with http_client() as client:
        downloader = HTTPDownloader(client)
        print("Checking selected images and sizes; no downloads have started.")
        plan = build_plan(providers, root, images, manual, downloader.size)
        plan = Plan(
            (
                *plan.items,
                *(
                    PlannedDownload(name, None, None, Action.SKIP, reason="Skipped by user")
                    for name in skipped
                ),
            )
        )
        show_plan(plan, getattr(args, "keep_old", False))
        target_guard.validate_plan(plan)
        if target_guard.ventoy:
            print("Ventoy image visibility: OK")
        report = inspect(root, plan, cfg.safety_margin, managed_bytes)
        show_storage(report)
        if not plan.items:
            print("No images selected; nothing to download.")
            return 0
        errors = sum(i.action in {Action.ERROR, Action.MANUAL} for i in plan.items)
        if args.command == "check" or args.dry_run:
            return int(bool(errors or report.shortfall or plan.unknown_sizes))
        changes = [
            i
            for i in plan.items
            if i.action in {Action.DOWNLOAD, Action.UPDATE, Action.RELOCATE, Action.ADOPT}
        ]
        if not changes:
            return int(bool(errors))
        report.require_safe()
        if not args.no_interactive:
            if not sys.stdin.isatty():
                raise LibraryError(
                    "Use --no-interactive to authorize downloads without a terminal."
                )
            if input(
                f"Proceed with {format_bytes(plan.total_bytes)} of downloads "
                f"and {sum(i.action in {Action.RELOCATE, Action.ADOPT} for i in changes)} "
                "existing-file changes? [Y/n] "
            ).lower() not in {"", "y", "yes"}:
                print("Cancelled.")
                return 0
        target_guard.validate_plan(plan)
        with store.lock():
            if store.load() != images:
                raise LibraryError("Library state changed after planning; run again.")
            records = execute(
                plan,
                root,
                store,
                downloader,
                cfg.safety_margin,
                keep_old=args.keep_old,
                on_progress=print,
                target_guard=target_guard,
            )
        print(
            f"Update complete. Installed: {len(records)}; "
            f"current: {sum(i.action == Action.CURRENT for i in plan.items)}; "
            f"manual/failed: {errors}; skipped: {len(skipped)}; "
            f"unverified: {sum(r.verification_status == 'unverified' for r in records)}"
        )
        print(
            f"Free before: {format_bytes(report.available)}; "
            f"after: {format_bytes(inspect(root, Plan(()), cfg.safety_margin).available)}"
        )
        return int(bool(errors))


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG
        if args.verbose > 1
        else logging.INFO
        if args.verbose
        else logging.WARNING
    )
    if not args.command and not args.check_update and not args.update:
        cli.print_help()
        return 0
    try:
        return run(args)
    except (LibraryError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        if args.verbose > 1:
            logging.exception("Operation failed")
        return 1
    except (KeyboardInterrupt, EOFError):
        print("Interrupted; previous images preserved.", file=sys.stderr)
        return 130
