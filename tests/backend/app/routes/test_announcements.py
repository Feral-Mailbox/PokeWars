import app.db.models as models
from app.db.models import UserRole
from app.dependencies import get_current_user
from app.main import app
from app.routes.auth import hash_password


def _auth_as(user):
    app.dependency_overrides[get_current_user] = lambda: user


def _clear_auth():
    app.dependency_overrides.pop(get_current_user, None)


def _make_user(db, username, role=UserRole.user):
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=hash_password("secretpw"),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_admin_can_create_announcement_moderator_cannot(client, db):
    mod = _make_user(db, "mod-announce", UserRole.moderator)
    admin = _make_user(db, "admin-announce", UserRole.admin)
    player = _make_user(db, "player-announce", UserRole.user)

    _auth_as(mod)
    try:
        denied = client.post(
            "/announcements",
            json={"title": "Mod post", "message": "Should fail"},
        )
        assert denied.status_code == 403
    finally:
        _clear_auth()

    _auth_as(admin)
    try:
        created = client.post(
            "/announcements",
            json={"title": "Weekend War", "message": "Double cash all weekend."},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["title"] == "Weekend War"
        assert body["author_username"] == "admin-announce"
        assert body["message"] == "Double cash all weekend."
    finally:
        _clear_auth()

    _auth_as(player)
    try:
        listed = client.get("/announcements")
        assert listed.status_code == 200
        rows = listed.json()
        assert len(rows) == 1
        assert rows[0]["title"] == "Weekend War"
        assert rows[0]["starred"] is False
    finally:
        _clear_auth()


def test_player_can_star_and_clear_keeps_starred(client, db):
    admin = _make_user(db, "admin-star", UserRole.admin)
    player = _make_user(db, "player-star", UserRole.user)

    _auth_as(admin)
    try:
        first = client.post(
            "/announcements",
            json={"title": "Keep me", "message": "Starred stays."},
        )
        second = client.post(
            "/announcements",
            json={"title": "Clear me", "message": "Gone after clear."},
        )
        assert first.status_code == 201
        assert second.status_code == 201
        keep_id = first.json()["id"]
        clear_id = second.json()["id"]
    finally:
        _clear_auth()

    _auth_as(player)
    try:
        starred = client.post(f"/announcements/{keep_id}/star")
        assert starred.status_code == 200
        assert starred.json()["starred"] is True

        cleared = client.post("/announcements/clear")
        assert cleared.status_code == 200
        assert cleared.json()["cleared"] >= 1

        listed = client.get("/announcements")
        assert listed.status_code == 200
        rows = listed.json()
        ids = {row["id"] for row in rows}
        assert keep_id in ids
        assert clear_id not in ids
        assert rows[0]["starred"] is True

        unstarred = client.delete(f"/announcements/{keep_id}/star")
        assert unstarred.status_code == 200
        assert unstarred.json()["starred"] is False
    finally:
        _clear_auth()
