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


def _async_redis_with_messages(*messages):
    """Build a fake async Redis client whose pubsub.listen yields the given messages."""
    from starlette.websockets import WebSocketDisconnect

    class FakePubSub:
        async def subscribe(self, *_channels):
            return None

        async def unsubscribe(self, *_channels):
            return None

        async def aclose(self):
            return None

        async def listen(self):
            for message in messages:
                yield message
            raise WebSocketDisconnect()

    class FakeAsyncRedis:
        def pubsub(self):
            return FakePubSub()

        async def aclose(self):
            return None

    return FakeAsyncRedis()


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
    with patch(
        "app.routes.ws._async_redis_client",
        return_value=_async_redis_with_messages({"type": "message", "data": '{"ok":true}'}),
    ):
        with client.websocket_connect("/api/ws/global") as ws:
            assert ws.receive_text() == '{"ok":true}'

    client.cookies.set("session_user", create_session_token(user.id))
    with patch(
        "app.routes.ws._async_redis_client",
        return_value=_async_redis_with_messages(
            {"type": "subscribe", "data": 1},
            {"type": "message", "data": "hello"},
        ),
    ):
        with client.websocket_connect("/api/ws/game/ws-live-link") as ws:
            assert ws.receive_text() == "hello"

    # Authenticated non-participants may spectate.
    client.cookies.set("session_user", create_session_token(outsider.id))
    with patch(
        "app.routes.ws._async_redis_client",
        return_value=_async_redis_with_messages({"type": "message", "data": "spec-hello"}),
    ), patch("app.routes.ws._announce_spectator_system_log") as announce:
        with client.websocket_connect("/api/ws/game/ws-live-link") as ws:
            assert ws.receive_text() == "spec-hello"
        assert announce.call_count >= 1
        join_messages = [call.args[1] for call in announce.call_args_list]
        assert any("is now spectating" in msg for msg in join_messages)
        assert any("stopped spectating" in msg for msg in join_messages)


def test_global_ws_accept_failure_and_disconnect(db, monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
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

        monkeypatch.setattr(
            ws_routes,
            "_async_redis_client",
            lambda: _async_redis_with_messages({"type": "message", "data": '{"event":"ping"}'}),
        )

        ws2.accept = _accept
        ws2.send_text = AsyncMock()
        await ws_routes.global_ws(ws2)
        assert ws2.send_text.await_count == 1

    asyncio.run(_run())
