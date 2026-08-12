"""WebSocket game_patch helpers — push deltas instead of invalidate-and-refetch signals."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable

import redis


def event_seq_key(game_link: str) -> str:
    return f"game_event_seq:{game_link}"


def next_event_seq(redis_client: redis.Redis, game_link: str) -> int:
    try:
        return int(redis_client.incr(event_seq_key(game_link)))
    except Exception:
        return 0


def unit_to_patch(unit: Any, *, include_unit_summary: bool = True) -> dict[str, Any]:
    """Lightweight unit snapshot for client-side merge."""
    patch: dict[str, Any] = {
        "id": int(getattr(unit, "id", 0) or 0),
        "game_id": int(getattr(unit, "game_id", 0) or 0),
        "unit_id": int(getattr(unit, "unit_id", 0) or 0),
        "user_id": int(getattr(unit, "user_id", 0) or 0),
        "current_x": int(getattr(unit, "current_x", 0) or 0),
        "current_y": int(getattr(unit, "current_y", 0) or 0),
        "starting_x": int(getattr(unit, "starting_x", getattr(unit, "current_x", 0)) or 0),
        "starting_y": int(getattr(unit, "starting_y", getattr(unit, "current_y", 0)) or 0),
        "level": int(getattr(unit, "level", 50) or 50),
        "current_hp": int(getattr(unit, "current_hp", 0) or 0),
        "current_stats": getattr(unit, "current_stats", None) or {},
        "stat_boosts": getattr(unit, "stat_boosts", None) or {},
        "status_effects": getattr(unit, "status_effects", None) or [],
        "states": getattr(unit, "states", None) or [],
        "is_fainted": bool(getattr(unit, "is_fainted", False)),
        "can_move": getattr(unit, "can_move", True) is not False,
        "move_pp": list(getattr(unit, "move_pp", None) or []),
        "held_item": getattr(unit, "held_item", None),
        "held_item_slug": getattr(unit, "held_item_slug", None),
        "held_tm_move_id": getattr(unit, "held_tm_move_id", None),
        "equipped_move_ids": list(getattr(unit, "equipped_move_ids", None) or []),
        "ability": getattr(unit, "ability", None),
        "ability_id": getattr(unit, "ability_id", None),
    }
    flags = getattr(unit, "flags", None)
    jailed = getattr(unit, "jailed", None)
    jailed_by = getattr(unit, "jailed_by", None)
    if jailed is None and isinstance(flags, dict):
        jailed = bool(flags.get("jailed"))
    if jailed_by is None and isinstance(flags, dict) and flags.get("jailed_by") is not None:
        jailed_by = flags.get("jailed_by")
    patch["jailed"] = bool(jailed)
    patch["jailed_by"] = int(jailed_by) if jailed_by is not None else None
    if include_unit_summary and getattr(unit, "unit", None) is not None:
        u = unit.unit
        patch["unit"] = {
            "id": getattr(u, "id", None),
            "name": getattr(u, "name", None),
            "types": getattr(u, "types", None),
            "base_stats": getattr(u, "base_stats", None),
            "sprite_url": getattr(u, "sprite_url", None),
            "asset_folder": getattr(u, "asset_folder", None),
            "cost": getattr(u, "cost", None),
        }
    return patch


def turn_op_from_state(state: Any) -> dict[str, Any]:
    deadline = getattr(state, "turn_deadline", None)
    if isinstance(deadline, datetime):
        deadline_s = deadline.isoformat()
    else:
        deadline_s = deadline
    status = getattr(state, "status", None)
    status_s = getattr(status, "value", None) or (str(status) if status is not None else None)
    return {
        "op": "turn",
        "current_turn": getattr(state, "current_turn", None),
        "turn_deadline": deadline_s,
        "status": status_s,
        "winner_id": getattr(state, "winner_id", None),
        "players": list(getattr(state, "players", None) or []),
    }


def players_op(players: Iterable[Any]) -> dict[str, Any] | None:
    rows: list[dict[str, Any]] = []
    for p in players or []:
        rows.append(
            {
                "player_id": int(getattr(p, "player_id", 0) or 0),
                "cash_remaining": getattr(p, "cash_remaining", None),
                "is_ready": bool(getattr(p, "is_ready", False)),
                "game_units": list(getattr(p, "game_units", None) or []),
            }
        )
    if not rows:
        return None
    return {"op": "players", "players": rows}


def read_turnlock(
    redis_client: redis.Redis,
    game_link: str,
    current_player_id: int,
) -> dict[str, Any]:
    key = f"turnlock:{game_link}:{current_player_id}"
    try:
        raw = redis_client.hgetall(key) or {}
    except Exception:
        return {}
    out: dict[str, Any] = {}
    for k, v in raw.items():
        try:
            out[str(int(k))] = json.loads(v)
        except Exception:
            continue
    return out


def build_game_patch_payload(
    *,
    event_seq: int,
    ops: list[dict[str, Any]],
    cause: str | None = None,
    refetch: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": "game_patch",
        "event_seq": int(event_seq),
        "ops": list(ops or []),
    }
    if cause:
        payload["cause"] = cause
    if refetch:
        payload["refetch"] = list(refetch)
    return payload


def publish_game_patch(
    redis_client: redis.Redis,
    game_link: str,
    ops: list[dict[str, Any]],
    *,
    cause: str | None = None,
    refetch: list[str] | None = None,
) -> int:
    """Publish a game_patch envelope on game_updates:{link}. Returns event_seq."""
    if not game_link:
        return 0
    if not ops and not refetch:
        return 0
    seq = next_event_seq(redis_client, game_link)
    payload = build_game_patch_payload(
        event_seq=seq,
        ops=ops,
        cause=cause,
        refetch=refetch,
    )
    try:
        redis_client.publish(f"game_updates:{game_link}", json.dumps(payload))
    except Exception:
        return seq
    return seq
