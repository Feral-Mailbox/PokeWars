"""Populate unit seed JSON files with ability_ids and hidden_ability from PokeAPI.

Run from apps/backend:
    python scripts/populate_unit_abilities.py
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
ABILITIES_DIR = Path(__file__).resolve().parent.parent / "seed" / "abilities"
HEADERS = {"User-Agent": "poketactics-seed/1.0"}

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


def build_ability_lookup() -> dict[str, int]:
    lookup: dict[str, int] = {}
    for path in ABILITIES_DIR.rglob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        keys = {
            data["slug"],
            data["name"].lower(),
            re.sub(r"[^a-z0-9]+", "_", data["name"].lower()).strip("_"),
        }
        for key in keys:
            lookup[key] = data["id"]
    return lookup


def poke_slug_to_id(slug: str, lookup: dict[str, int]) -> int | None:
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


def fetch_abilities(poke_name: str, lookup: dict[str, int]) -> tuple[list[int], int | None]:
    url = f"https://pokeapi.co/api/v2/pokemon/{poke_name}"
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)

    regular: list[int] = []
    hidden: int | None = None
    for entry in payload["abilities"]:
        ability_id = poke_slug_to_id(entry["ability"]["name"], lookup)
        if ability_id is None:
            raise KeyError(f"Unknown ability '{entry['ability']['name']}' for {poke_name}")
        if entry["is_hidden"]:
            hidden = ability_id
        else:
            regular.append(ability_id)

    deduped: list[int] = []
    seen: set[int] = set()
    for ability_id in regular:
        if ability_id in seen:
            continue
        seen.add(ability_id)
        deduped.append(ability_id)
    return deduped, hidden


def update_unit_file(path: Path, lookup: dict[str, int]) -> None:
    unit = json.loads(path.read_text(encoding="utf-8"))
    poke_name = unit_poke_name(unit, path.name)
    ability_ids, hidden_ability = fetch_abilities(poke_name, lookup)
    unit["ability_ids"] = ability_ids
    unit["hidden_ability"] = hidden_ability
    path.write_text(json.dumps(unit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[+] {path.name:25} {poke_name:22} abilities={ability_ids} hidden={hidden_ability}")


def main() -> None:
    lookup = build_ability_lookup()
    failures: list[tuple[str, str]] = []

    for path in sorted(UNITS_DIR.glob("*.json")):
        try:
            update_unit_file(path, lookup)
        except (urllib.error.HTTPError, urllib.error.URLError, KeyError, TimeoutError) as exc:
            failures.append((path.name, str(exc)))
            print(f"[!] {path.name:25} {exc}")
        time.sleep(0.05)

    if failures:
        raise SystemExit(f"Failed to populate {len(failures)} unit file(s).")
    print(f"✅ Populated abilities for {len(list(UNITS_DIR.glob('*.json')))} units.")


if __name__ == "__main__":
    main()
