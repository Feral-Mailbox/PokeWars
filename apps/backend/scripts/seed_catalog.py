"""Refresh selected catalog tables from JSON seed files without wiping the database."""

from __future__ import annotations

import argparse

from scripts import seed_moves, seed_official_maps, seed_units

CATALOGS = {
    "maps": ("Official maps", seed_official_maps.load_maps),
    "units": ("Units", seed_units.load_units),
    "moves": ("Moves", seed_moves.load_moves),
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh selected catalog tables from seed JSON files. "
            "Existing rows are updated in place so games, users, and other data stay intact."
        )
    )
    parser.add_argument(
        "--only",
        default="maps,units,moves",
        help="Comma-separated catalogs to refresh: maps, units, moves (default: all)",
    )
    parser.add_argument(
        "--refresh",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Update existing seed rows instead of skipping them (default: true)",
    )
    args = parser.parse_args()

    catalogs = parse_catalogs(args.only)
    refresh_catalogs(catalogs, refresh=args.refresh)
    print("\n✅ Catalog refresh complete.")


if __name__ == "__main__":
    main()
