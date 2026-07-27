from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import app.db.models as models
from app.routes.auth import hash_password
from app.routes import ws as ws_routes
from app.utils.session import create_session_token


def test_login_rejects_unknown_user(client):
    resp = client.post("/login", json={"username": "missing", "password": "x"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


def test_login_rejects_user_without_password_hash(client, db):
    user = models.User(username="nopw", email="nopw@example.com", hashed_password="")
    db.add(user)
    db.commit()

    resp = client.post("/login", json={"username": "nopw", "password": "x"})
    assert resp.status_code == 401


def test_login_rejects_active_ban(client, db):
    user = models.User(
        username="banned",
        email="banned@example.com",
        hashed_password=hash_password("secret"),
        is_banned=True,
        ban_reason="abuse",
        # SQLite stores naive datetimes; keep naive to match clear_expired_ban comparisons.
        ban_expires_at=datetime.utcnow() + timedelta(days=1),
    )
    db.add(user)
    db.commit()

    resp = client.post("/login", json={"username": "banned", "password": "secret"})
    assert resp.status_code == 403
    assert resp.json()["detail"]["message"] == "Account restricted"


def test_login_clears_expired_ban_and_succeeds(client, db):
    user = models.User(
        username="exban",
        email="exban@example.com",
        hashed_password=hash_password("secret"),
        is_banned=True,
        ban_reason="old",
        ban_expires_at=datetime.utcnow() - timedelta(days=1),
    )
    db.add(user)
    db.commit()

    resp = client.post("/login", json={"username": "exban", "password": "secret"})
    assert resp.status_code == 200
    db.refresh(user)
    assert user.is_banned is False


def test_login_handles_password_verify_exception(client, db, monkeypatch):
    db.add(
        models.User(
            username="broken",
            email="broken@example.com",
            hashed_password="not-a-real-hash",
        )
    )
    db.commit()

    def boom(*_args, **_kwargs):
        raise ValueError("bad hash")

    monkeypatch.setattr("app.routes.auth.verify_password", boom)
    resp = client.post("/login", json={"username": "broken", "password": "x"})
    assert resp.status_code == 401


def test_ws_resolve_authenticated_user(db):
    user = models.User(
        username="wsuser",
        email="wsuser@example.com",
        hashed_password=hash_password("pw"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_session_token(user.id)
    resolved = ws_routes._resolve_authenticated_user(token)
    assert resolved is not None
    assert resolved.id == user.id
    assert ws_routes._resolve_authenticated_user("not-a-token") is None


def test_ws_user_is_game_participant(db):
    host = models.User(username="host", email="host@example.com", hashed_password="x")
    guest = models.User(username="guest", email="guest@example.com", hashed_password="x")
    db.add_all([host, guest])
    db.flush()
    from tests.backend.conftest import make_test_map

    map_obj = make_test_map(db, creator_id=host.id)
    game = models.Game(
        game_name="WS Game",
        map_id=map_obj.id,
        map_name=map_obj.name,
        max_players=2,
        gamemode="Conquest",
        is_private=False,
        host_id=host.id,
        link="ws-link",
    )
    db.add(game)
    db.flush()
    db.add(models.GamePlayer(game_id=game.id, player_id=host.id))
    db.commit()

    assert ws_routes._user_is_game_participant(host.id, "ws-link") is True
    assert ws_routes._user_is_game_participant(guest.id, "ws-link") is False
    assert ws_routes._user_is_game_participant(host.id, "missing") is False
    assert ws_routes._game_exists("ws-link") is True
    assert ws_routes._game_exists("missing") is False


def test_spectator_connection_refcount(monkeypatch):
    fake = MagicMock()
    fake.incr.side_effect = [1, 2, 1]
    fake.decr.side_effect = [1, 0]
    monkeypatch.setattr(ws_routes, "r", fake)

    assert ws_routes._register_spectator_connection("g1", 7) is True
    assert ws_routes._register_spectator_connection("g1", 7) is False
    assert ws_routes._unregister_spectator_connection("g1", 7) is False
    assert ws_routes._unregister_spectator_connection("g1", 7) is True
    fake.delete.assert_called()
