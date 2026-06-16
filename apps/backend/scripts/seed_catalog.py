"""Refresh selected catalog tables from JSON seed files without wiping the database."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from scripts import seed_moves, seed_official_maps, seed_units, seed_items

CATALOGS = {
    "maps": ("Official maps", seed_official_maps.load_maps),
    "units": ("Units", seed_units.load_units),
    "moves": ("Moves", seed_moves.load_moves),
    "items": ("Items", seed_items.load_items),
}


def parse_catalogs(raw: str) -> list[str]:
    selected = [part.strip().lower() for part in raw.split(",") if part.strip()]
    if not selected:
        raise ValueError("At least one catalog must be selected")

    unknown = [name for name in selected if name not in CATALOGS]
    if unknown:
        valid = ", ".join(sorted(CATALOGS))
        raise ValueError(f"Unknown catalog(s): {', '.join(unknown)}. Valid options: {valid}")

    # Preserve user order while removing duplicates.
    seen: set[str] = set()
    ordered: list[str] = []
    for name in selected:
        if name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def refresh_catalogs(catalogs: list[str], *, refresh: bool = True) -> None:
    for name in catalogs:
        label, loader = CATALOGS[name]
        print(f"\n=== Seeding {label} ===")
        loader(refresh=refresh)


def ensure_bootstrap_admin_account() -> None:
    from app.bootstrap import BootstrapError, run_bootstrap_admin

    print("\n=== Ensuring bootstrap admin account ===")
    try:
        run_bootstrap_admin()
    except BootstrapError as exc:
        raise SystemExit(f"Bootstrap admin setup failed: {exc}") from exc


def run_from_args(args: argparse.Namespace) -> None:
    if args.bootstrap_only:
        ensure_bootstrap_admin_account()
        print("\n✅ Bootstrap admin check complete.")
        return

    catalogs = parse_catalogs(args.only)
    refresh_catalogs(catalogs, refresh=args.refresh)
    if not args.skip_bootstrap:
        ensure_bootstrap_admin_account()
    print("\n✅ Catalog refresh complete.")


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    parser = argparse.ArgumentParser(
        description=(
            "Refresh selected catalog tables from seed JSON files. "
            "Existing rows are updated in place so games, users, and other data stay intact."
        )
    )
    parser.add_argument(
        "--only",
        default="maps,units,moves",
        help="Comma-separated catalogs to refresh: maps, units, moves, items (default: all)",
    )
    parser.add_argument(
        "--refresh",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Update existing seed rows instead of skipping them (default: true)",
    )
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="Do not create or sync the bootstrap admin account",
    )
    parser.add_argument(
        "--bootstrap-only",
        action="store_true",
        help="Only create or sync the bootstrap admin account",
    )
    args = parser.parse_args()
    run_from_args(args)


if __name__ == "__main__":
    main()
