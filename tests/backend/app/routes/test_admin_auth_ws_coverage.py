from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

import app.db.models as models
from app.db.models import UserRole
from app.dependencies import get_current_user
from app.main import app
from app.routes.auth import hash_password
from app.utils.session import create_session_token
from tests.backend.conftest import make_test_map


def _make_user(db, username, role=UserRole.user, **kwargs):
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=hash_password("password"),
        role=role,
        **kwargs,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_admin_demote_last_admin_blocked(client, db):
    sole = _make_user(db, "sole-admin", role=UserRole.admin)
    # Actor is admin only in-memory so DB still has a single admin row.
    actor = _make_user(db, "fake-admin-actor", role=UserRole.user)
    actor.role = UserRole.admin
    app.dependency_overrides[get_current_user] = lambda: actor
    try:
        alone = client.post(f"/admin/users/{sole.id}/role", json={"role": "moderator"})
        assert alone.status_code == 400
        assert "last admin" in alone.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_admin_demote_moderator_to_user(client, db):
    admin = _make_user(db, "demote-admin", role=UserRole.admin)
    mod = _make_user(db, "demote-mod", role=UserRole.moderator)
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        resp = client.post(f"/admin/users/{mod.id}/role", json={"role": "user"})
        assert resp.status_code == 200
        assert resp.json()["role"] == "user"
        db.refresh(mod)
        assert mod.role == UserRole.user
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_admin_permanent_ban(client, db):
    admin = _make_user(db, "perm-admin", role=UserRole.admin)
    target = _make_user(db, "perm-target")
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        resp = client.post(
            f"/admin/users/{target.id}/ban",
            json={"reason": "cheat", "permanent": True},
        )
        assert resp.status_code == 200
        assert resp.json()["permanent"] is True
        assert resp.json()["expires_at"] is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_login_user_response_validation_error(client, db, monkeypatch):
    db.add(
        models.User(
            username="serfail",
            email="serfail@example.com",
            hashed_password=hash_password("secret"),
        )
    )
    db.commit()

    def boom(*_args, **_kwargs):
        raise ValidationError.from_exception_data("UserResponse", [])

    monkeypatch.setattr("app.routes.auth.UserResponse.model_validate", boom)
    resp = client.post("/login", json={"username": "serfail", "password": "secret"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "User serialization failed"


def test_ws_endpoints_auth_and_global(client, db):
    from starlette.websockets import WebSocketDisconnect

    user = _make_user(db, "ws-live")
    outsider = _make_user(db, "ws-out")
    map_obj = make_test_map(db, creator_id=user.id)
    game = models.Game(
        game_name="WS",
        map_id=map_obj.id,
        map_name=map_obj.name,
        max_players=2,
        gamemode="Conquest",
        is_private=False,
        host_id=user.id,
        link="ws-live-link",
    )
    db.add(game)
    db.flush()
    db.add(models.GamePlayer(game_id=game.id, player_id=user.id))
    db.commit()

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws/game/ws-live-link"):
            pass

    banned = _make_user(db, "ws-banned", is_banned=True, ban_expires_at=None)
    client.cookies.set("session_user", create_session_token(banned.id))
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws/global"):
            pass
    client.cookies.clear()

    client.cookies.set("session_user", create_session_token(user.id))
    with client.websocket_connect("/api/ws/global") as ws:
        assert ws is not None

    client.cookies.set("session_user", create_session_token(outsider.id))
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws/game/ws-live-link"):
            pass

    fake_pubsub = MagicMock()
    calls = {"n": 0}

    def _get_message(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            # Non-message pubsub event: covers `if message and type == message` false branch.
            return {"type": "subscribe", "data": 1}
        if calls["n"] == 2:
            return {"type": "message", "data": "hello"}
        raise WebSocketDisconnect()

    fake_pubsub.get_message.side_effect = _get_message
    fake_redis = MagicMock()
    fake_redis.pubsub.return_value = fake_pubsub

    client.cookies.set("session_user", create_session_token(user.id))
    with patch("app.routes.ws.r", fake_redis):
        with client.websocket_connect("/api/ws/game/ws-live-link") as ws:
            assert ws.receive_text() == "hello"


def test_global_ws_accept_failure_and_disconnect(db, monkeypatch):
    import asyncio
    from starlette.websockets import WebSocketDisconnect
    from app.routes import ws as ws_routes

    user = _make_user(db, "ws-async")
    monkeypatch.setattr(
        ws_routes,
        "_resolve_authenticated_user",
        lambda _token: user,
    )

    async def _run():
        ws = MagicMock()
        ws.cookies = {"session_user": "token"}

        async def _fail_accept():
            raise RuntimeError("accept failed")

        ws.accept = _fail_accept
        await ws_routes.global_ws(ws)

        ws2 = MagicMock()
        ws2.cookies = {"session_user": "token"}

        async def _accept():
            return None

        async def _sleep(_seconds):
            raise WebSocketDisconnect()

        ws2.accept = _accept
        monkeypatch.setattr(ws_routes.asyncio, "sleep", _sleep)
        await ws_routes.global_ws(ws2)

    asyncio.run(_run())
