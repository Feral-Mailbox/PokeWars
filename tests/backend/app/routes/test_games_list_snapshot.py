"""Tests for snapshot-paginated game list endpoints."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.db.models as models
from app.dependencies import get_current_user, get_db
from app.main import app


@pytest.fixture(scope="function")
def user(db):
    u = models.User(
        username="list_player",
        email="list_player@example.com",
        hashed_password="hashed",
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture(scope="function")
def client(db, user):
    def override_get_db():
        yield db

    def override_get_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed_open_game(db, user, *, link: str, name: str, created_at: datetime, max_players: int = 2):
    map_obj = db.query(models.Map).filter_by(name="Snapshot Map").first()
    if map_obj is None:
        map_obj = models.Map(
            name="Snapshot Map",
            creator_id=user.id,
            is_official=True,
            width=8,
            height=8,
            tileset_names=["grass"],
            tile_data={},
            allowed_modes=["Conquest"],
            allowed_player_counts=[2, 4],
        )
        db.add(map_obj)
        db.flush()

    game = models.Game(
        game_name=name,
        map_id=map_obj.id,
        map_name=map_obj.name,
        max_players=max_players,
        gamemode="Conquest",
        is_private=False,
        host_id=user.id,
        link=link,
        timestamp=created_at,
    )
    db.add(game)
    db.flush()
    db.add(
        models.GameState(
            game_id=game.id,
            current_turn=0,
            status=models.GameStatus.open,
            players=[user.id],
            winner_id=None,
            replay_log=[],
        )
    )
    db.add(
        models.GamePlayer(
            game_id=game.id,
            player_id=user.id,
            cash_remaining=1000,
            game_units=[],
            is_ready=False,
        )
    )
    db.commit()
    return game


def test_open_games_snapshot_pagination_excludes_newer_rows(client, db, user):
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    older = _seed_open_game(db, user, link="old-1", name="Older", created_at=t0)
    newer = _seed_open_game(
        db,
        user,
        link="new-1",
        name="Newer",
        created_at=t0 + timedelta(days=2),
    )

    snap = (t0 + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    resp = client.get(f"/games/open?page=1&page_size=10&as_of={snap}")
    assert resp.status_code == 200
    body = resp.json()
    ids = {row["id"] for row in body["items"]}
    assert older.id in ids
    assert newer.id not in ids
    assert body["as_of"].startswith("2026-01-02")

    page1 = client.get("/games/open?page=1&page_size=1")
    assert page1.status_code == 200
    assert page1.json()["total"] >= 2
    assert len(page1.json()["items"]) == 1
    as_of = page1.json()["as_of"]

    page2 = client.get(f"/games/open?page=2&page_size=1&as_of={as_of}")
    assert page2.status_code == 200
    assert page2.json()["as_of"] == as_of
    assert page2.json()["items"][0]["id"] != page1.json()["items"][0]["id"]
