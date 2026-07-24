"""Multiplayer Elo rating math.

Formula (pairwise placement Elo)
---------------------------------
For a finished match with N players and placements (1 = best):

  Expected score of i vs j:
      E_ij = 1 / (1 + 10 ** ((R_j - R_i) / 400))

  Actual score from placement:
      S_ij = 1.0 if place(i) < place(j)   # i finished ahead of j
           0.0 if place(i) > place(j)
           0.5 if place(i) == place(j)   # tie

  Rating change for i:
      ΔR_i = K * Σ_{j ≠ i} (S_ij - E_ij)

with K = 24 and a floor of 100 Elo after applying ΔR.

Equal-rating lobbies (important invariant)
-----------------------------------------
When every player has the same rating, E_ij = 0.5 for all pairs, so ΔR
depends only on place. Finishing one spot higher always yields a strictly
better delta (gain more / lose less). Example for four 1000-Elo players:

  1st +36, 2nd +12, 3rd -12, 4th -36

Why this scales for FFA
-----------------------
Each opponent is a separate comparison, so:
- larger lobbies create more pairwise terms (bigger potential swings)
- beating higher-rated players yields larger gains
- finishing near the top vs many players beats barely winning a 1v1 in total
  magnitude when ratings are similar (more +terms), while still zero-sum in
  expectation across the field.
"""

from __future__ import annotations

from typing import Iterable

ELO_K = 24.0
ELO_SCALE = 400.0
ELO_FLOOR = 100
DEFAULT_ELO = 1000

# Attribute names on User for each GameMode value string.
ELO_ATTR_BY_GAMEMODE = {
    "Conquest": "elo_conquest",
    "War": "elo_war",
    # CTF uses the Conquest ladder until it has its own rating track.
    "Capture The Flag": "elo_conquest",
}


def elo_attr_for_gamemode(gamemode) -> str:
    value = getattr(gamemode, "value", None) or str(gamemode)
    return ELO_ATTR_BY_GAMEMODE.get(value, "elo_conquest")


def elo_label_for_gamemode(gamemode) -> str:
    value = getattr(gamemode, "value", None) or str(gamemode)
    if value == "War":
        return "War Elo"
    if value == "Capture The Flag":
        return "Conquest Elo"
    return "Conquest Elo"


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / ELO_SCALE))


def build_placements(
    roster: Iterable[int],
    *,
    elimination_order: list[int] | None = None,
    winner_id: int | None = None,
    draw_ids: list[int] | None = None,
) -> dict[int, int]:
    """
    Map player_id -> place (1 = best).

    Prefer elimination order (earliest eliminated = worst) plus an explicit
    winner or draw set when the match ends by timeout / wipe.
    """
    players = [int(pid) for pid in roster]
    if not players:
        return {}

    elim = []
    seen = set()
    for pid in elimination_order or []:
        pid = int(pid)
        if pid in players and pid not in seen:
            elim.append(pid)
            seen.add(pid)

    draws = [int(pid) for pid in (draw_ids or []) if int(pid) in players]
    winner = int(winner_id) if winner_id is not None else None

    ordered: list[int] = []
    places: dict[int, int] = {}

    if winner is not None and winner in players:
        ordered.append(winner)
        elim_set = set(elim)
        for pid in players:
            if pid != winner and pid not in elim_set and pid not in ordered:
                ordered.append(pid)
        for pid in reversed(elim):
            if pid not in ordered:
                ordered.append(pid)
        for pid in players:
            if pid not in ordered:
                ordered.append(pid)
        return {pid: idx + 1 for idx, pid in enumerate(ordered)}

    if draws:
        # All draw winners share place 1; remaining ordered by reverse elimination.
        for pid in draws:
            places[pid] = 1
        rest: list[int] = []
        for pid in reversed(elim):
            if pid not in places and pid not in rest:
                rest.append(pid)
        for pid in players:
            if pid not in places and pid not in rest:
                rest.append(pid)
        for idx, pid in enumerate(rest):
            places[pid] = 2 + idx
        return places

    # No explicit winner: reverse elimination order, leftovers last.
    for pid in reversed(elim):
        if pid not in ordered:
            ordered.append(pid)
    for pid in players:
        if pid not in ordered:
            ordered.append(pid)
    return {pid: idx + 1 for idx, pid in enumerate(ordered)}


def compute_elo_deltas(
    ratings: dict[int, int],
    places: dict[int, int],
    *,
    k: float = ELO_K,
) -> dict[int, int]:
    """Return integer Elo deltas for each player_id in ``ratings``."""
    ids = [pid for pid in ratings if pid in places]
    if len(ids) < 2:
        return {pid: 0 for pid in ratings}

    raw: dict[int, float] = {pid: 0.0 for pid in ids}
    for i in ids:
        for j in ids:
            if i == j:
                continue
            expected = expected_score(float(ratings[i]), float(ratings[j]))
            if places[i] < places[j]:
                actual = 1.0
            elif places[i] > places[j]:
                actual = 0.0
            else:
                actual = 0.5
            raw[i] += k * (actual - expected)

    return {pid: int(round(raw[pid])) for pid in ids}


def apply_floor(rating: int, delta: int, floor: int = ELO_FLOOR) -> int:
    return max(floor, int(rating) + int(delta))
