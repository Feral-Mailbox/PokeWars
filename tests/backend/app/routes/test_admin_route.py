from datetime import datetime, timedelta, timezone

import app.db.models as models
from app.db.models import StaffActionType, UserRole
from app.dependencies import get_current_user
from app.main import app
from app.routes.auth import hash_password


def _make_user(db, username, *, role=UserRole.user):
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=hash_password("password"),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_admin_routes_require_admin(client, db):
    user = _make_user(db, "regular")
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        assert client.get("/admin/staff").status_code == 403
        assert client.get("/admin/audit-log").status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_staff_and_audit_log(client, db):
    admin = _make_user(db, "admin1", role=UserRole.admin)
    mod = _make_user(db, "mod1", role=UserRole.moderator)
    _make_user(db, "player1", role=UserRole.user)
    db.add(
        models.StaffAction(
            actor_id=admin.id,
            target_user_id=mod.id,
            action_type=StaffActionType.promote_moderator,
            reason="trusted",
        )
    )
    db.commit()

    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        staff_resp = client.get("/admin/staff")
        assert staff_resp.status_code == 200
        usernames = {row["username"] for row in staff_resp.json()}
        assert usernames == {"admin1", "mod1"}

        audit_resp = client.get("/admin/audit-log")
        assert audit_resp.status_code == 200
        assert len(audit_resp.json()) == 1
        assert audit_resp.json()[0]["action_type"] == "promote_moderator"
        assert audit_resp.json()[0]["actor_username"] == "admin1"
        assert audit_resp.json()[0]["target_username"] == "mod1"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_ban_and_unban_user(client, db):
    admin = _make_user(db, "admin-ban", role=UserRole.admin)
    target = _make_user(db, "target-ban")

    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        missing = client.post(
            "/admin/users/99999/ban",
            json={"reason": "gone", "permanent": True},
        )
        assert missing.status_code == 404

        bad_temp = client.post(
            f"/admin/users/{target.id}/ban",
            json={"reason": "temp", "permanent": False},
        )
        assert bad_temp.status_code == 400

        ban = client.post(
            f"/admin/users/{target.id}/ban",
            json={"reason": "cheating", "permanent": False, "days": 2},
        )
        assert ban.status_code == 200
        assert ban.json()["ok"] is True
        assert ban.json()["permanent"] is False

        db.refresh(target)
        assert target.is_banned is True

        unban_missing = client.post(
            "/admin/users/99999/unban",
            json={"reason": "nope"},
        )
        assert unban_missing.status_code == 404

        unban = client.post(
            f"/admin/users/{target.id}/unban",
            json={"reason": "appealed"},
        )
        assert unban.status_code == 200
        db.refresh(target)
        assert target.is_banned is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_change_user_role_rules(client, db):
    admin = _make_user(db, "admin-role", role=UserRole.admin)
    target = _make_user(db, "role-target")

    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        assert client.post(
            "/admin/users/99999/role",
            json={"role": "moderator"},
        ).status_code == 404

        demote_self = client.post(
            f"/admin/users/{admin.id}/role",
            json={"role": "user"},
        )
        assert demote_self.status_code == 400

        promote = client.post(
            f"/admin/users/{target.id}/role",
            json={"role": "moderator"},
        )
        assert promote.status_code == 200
        assert promote.json()["role"] == "moderator"
        db.refresh(target)
        assert target.role == UserRole.moderator

        # Only one admin remains; cannot demote them via another admin account path
        # (target is mod). Promote target to admin, then try demoting original when sole admin.
        client.post(f"/admin/users/{target.id}/role", json={"role": "admin"})
        db.refresh(target)
        assert target.role == UserRole.admin

        # Two admins now; demote original admin should work from target's session
        app.dependency_overrides[get_current_user] = lambda: target
        demote = client.post(
            f"/admin/users/{admin.id}/role",
            json={"role": "user"},
        )
        assert demote.status_code == 200
        db.refresh(admin)
        assert admin.role == UserRole.user

        # Last admin cannot demote self through role endpoint when alone
        alone = client.post(
            f"/admin/users/{target.id}/role",
            json={"role": "moderator"},
        )
        assert alone.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)
