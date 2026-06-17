"""Populate unit seed JSON files with Gen 9 (Scarlet/Violet) learnsets from PokeAPI.

Run from apps/backend:
    python3 scripts/populate_unit_moves.py
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

UNITS_DIR = Path(__file__).resolve().parent.parent / "seed" / "units"
MOVES_DIR = Path(__file__).resolve().parent.parent / "seed" / "moves"
HEADERS = {"User-Agent": "poketactics-seed/1.0"}
VERSION_GROUPS = ("scarlet-violet", "the-teal-mask", "the-indigo-disk")
FALLBACK_VERSION_GROUPS = ("sword-shield", "ultra-sun-ultra-moon")

POKE_NAME_OVERRIDES = {
    "ho-oh.json": "ho-oh",
    "mimikyu_base.json": "mimikyu-disguised",
    "mimikyu_busted.json": "mimikyu-disguised",
    "morpeko_base.json": "morpeko-full-belly",
    "morpeko_hangry.json": "morpeko-hangry",
    "shellos_east.json": "shellos",
    "shellos_west.json": "shellos",
    "gastrodon_east.json": "gastrodon",
    "gastrodon_west.json": "gastrodon",
}

FORM_SUFFIX = {
    "alola": "alola",
    "hisui": "hisui",
    "east": "east",
    "west": "west",
    "midday": "midday",
    "midnight": "midnight",
    "dusk": "dusk",
}


def build_move_lookup() -> dict[str, int]:
    lookup: dict[str, int] = {}
    for path in MOVES_DIR.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        keys = {
            path.stem.replace("-", "_"),
            re.sub(r"[^a-z0-9]+", "_", data["name"].lower()).strip("_"),
        }
        for key in keys:
            lookup[key] = data["id"]
    return lookup


def poke_slug_to_move_id(slug: str, lookup: dict[str, int]) -> int | None:
    normalized = slug.replace("-", "_")
    if normalized in lookup:
        return lookup[normalized]
    compact = normalized.replace("_", "")
    for key, value in lookup.items():
        if key.replace("_", "") == compact:
            return value
    return None


def unit_poke_name(unit: dict, filename: str) -> str:
    if filename in POKE_NAME_OVERRIDES:
        return POKE_NAME_OVERRIDES[filename]

    asset_folder = unit["asset_folder"]
    base = re.sub(r"^\d+[a-z]?_", "", asset_folder)
    parts = base.split("_")
    if len(parts) >= 2 and parts[-1] in FORM_SUFFIX and FORM_SUFFIX[parts[-1]]:
        return f"{parts[0]}-{FORM_SUFFIX[parts[-1]]}"
    return parts[0]


def fetch_learnsets(
    poke_name: str,
    lookup: dict[str, int],
) -> tuple[list[dict[str, int]], list[int], list[int], list[str], str]:
    url = f"https://pokeapi.co/api/v2/pokemon/{poke_name}"
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)

    level_up_entries: list[tuple[int, int]] = []
    tm_moves: list[int] = []
    egg_moves: list[int] = []
    missing_moves: list[str] = []
    active_groups = list(VERSION_GROUPS)

    def collect_for_groups(groups: tuple[str, ...]) -> None:
        nonlocal level_up_entries, tm_moves, egg_moves, missing_moves
        for entry in payload["moves"]:
            move_slug = entry["move"]["name"]
            move_id = poke_slug_to_move_id(move_slug, lookup)
            if move_id is None:
                missing_moves.append(move_slug)
                continue

            for version_detail in entry["version_group_details"]:
                if version_detail["version_group"]["name"] not in groups:
                    continue

                method = version_detail["move_learn_method"]["name"]
                if method == "level-up":
                    level_up_entries.append((version_detail["level_learned_at"], move_id))
                elif method == "machine":
                    tm_moves.append(move_id)
                elif method == "egg":
                    egg_moves.append(move_id)

    collect_for_groups(active_groups)
    source = "gen9"
    if not level_up_entries and not tm_moves and not egg_moves:
        for fallback_group in FALLBACK_VERSION_GROUPS:
            level_up_entries = []
            tm_moves = []
            egg_moves = []
            missing_moves = []
            collect_for_groups((fallback_group,))
            if level_up_entries or tm_moves or egg_moves:
                source = f"fallback:{fallback_group}"
                break

    level_up_entries.sort(key=lambda item: (item[0], item[1]))
    deduped_level_up: list[dict[str, int]] = []
    seen_level_up: dict[int, int] = {}
    for level, move_id in level_up_entries:
        if move_id not in seen_level_up or level < seen_level_up[move_id]:
            seen_level_up[move_id] = level
    for move_id, level in sorted(seen_level_up.items(), key=lambda item: (item[1], item[0])):
        deduped_level_up.append({"level": level, "move_id": move_id})

    deduped_tm: list[int] = []
    seen_tm: set[int] = set()
    for move_id in sorted(tm_moves):
        if move_id in seen_tm:
            continue
        seen_tm.add(move_id)
        deduped_tm.append(move_id)

    deduped_egg: list[int] = []
    seen_egg: set[int] = set()
    for move_id in sorted(egg_moves):
        if move_id in seen_egg:
            continue
        seen_egg.add(move_id)
        deduped_egg.append(move_id)

    return deduped_level_up, deduped_tm, deduped_egg, missing_moves, source


def update_unit_file(path: Path, lookup: dict[str, int]) -> list[str]:
    unit = json.loads(path.read_text(encoding="utf-8"))
    poke_name = unit_poke_name(unit, path.name)
    level_up_moves, tm_moves, egg_moves, missing_moves, source = fetch_learnsets(poke_name, lookup)

    unit.pop("move_ids", None)
    unit["level_up_moves"] = level_up_moves
    unit["tm_moves"] = tm_moves
    unit["egg_moves"] = egg_moves

    path.write_text(json.dumps(unit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"[+] {path.name:25} {poke_name:22} "
        f"level-up={len(level_up_moves)} tm={len(tm_moves)} egg={len(egg_moves)} ({source})"
    )
    return missing_moves


def main() -> None:
    lookup = build_move_lookup()
    failures: list[tuple[str, str]] = []
    all_missing: dict[str, list[str]] = {}

    for path in sorted(UNITS_DIR.glob("*.json")):
        try:
            missing = update_unit_file(path, lookup)
            if missing:
                all_missing[path.name] = sorted(set(missing))
        except (urllib.error.HTTPError, urllib.error.URLError, KeyError, TimeoutError) as exc:
            failures.append((path.name, str(exc)))
            print(f"[!] {path.name:25} {exc}")
        time.sleep(0.05)

    if all_missing:
        print("\n[!] Moves missing from seed catalog:")
        for filename, moves in sorted(all_missing.items()):
            print(f"  {filename}: {', '.join(moves)}")

    if failures:
        raise SystemExit(f"Failed to populate {len(failures)} unit file(s).")

    print(f"✅ Populated Gen 9 learnsets for {len(list(UNITS_DIR.glob('*.json')))} units.")


if __name__ == "__main__":
    main()
