import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

import app.db.models as models
from app.db.models import (
    InfractionSeverity,
    InfractionStatus,
    StaffActionType,
    UserRole,
)
from app.dependencies import get_current_user
from app.main import app
from app.moderation.filter import (
    _match_spaced_term,
    _match_term_in_token,
    filter_message,
    normalize_token,
    reload_wordlist,
)
from app.moderation.service import apply_chat_moderation
from app.moderation.staff_actions import apply_ban, log_staff_action
from app.routes.auth import hash_password
from tests.backend.conftest import make_test_map


def _make_user(db, username, role=UserRole.user):
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


def _make_game(db, host):
    map_obj = make_test_map(db, creator_id=host.id, name=f"Map-{host.username}")
    game = models.Game(
        game_name=f"Game-{host.username}",
        map_id=map_obj.id,
        map_name=map_obj.name,
        max_players=2,
        gamemode="Conquest",
        is_private=False,
        host_id=host.id,
        link=f"link-{host.username}",
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def _make_infraction(db, user, game, *, status=InfractionStatus.pending_review):
    infraction = models.ChatInfraction(
        user_id=user.id,
        game_id=game.id,
        original_message="bad word here",
        censored_message="*** **** here",
        matched_terms=["bad"],
        severity=InfractionSeverity.slur,
        status=status,
        created_at=datetime.now(timezone.utc),
    )
    db.add(infraction)
    db.commit()
    db.refresh(infraction)
    return infraction


def test_filter_empty_and_substring_and_spaced_and_compact():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump({"blocked_terms": ["!!!", "ab", "bad", "hate", "slur"]}, handle)
        path = handle.name
    try:
        reload_wordlist()
        assert normalize_token("!!!") == ""
        assert _match_term_in_token("!!!", "hate") is False
        assert _match_term_in_token("hate", "!!!") is False
        assert _match_spaced_term("a b", "ab") == []
        assert filter_message("clean text", wordlist_path=path).had_match is False

        result = filter_message("superhateful", wordlist_path=path)
        assert result.had_match is True

        spaced = filter_message("s l u r", wordlist_path=path)
        assert spaced.had_match is True

        overlap = filter_message("hate hate", wordlist_path=path)
        assert overlap.had_match is True

        # Compact path: short term (<4) embedded without matching token equality/substring rules.
        compact = filter_message("xxbadxx", wordlist_path=path)
        assert compact.had_match is True
        assert compact.censored_message == "*" * len("xxbadxx")
    finally:
        os.unlink(path)
        reload_wordlist()


def test_apply_ban_rejects_self_for_regular_user(db):
    user = _make_user(db, "selfban")
    with pytest.raises(HTTPException) as exc:
        apply_ban(
            db,
            actor=user,
            target=user,
            reason="self",
            expires_at=None,
            action_type=StaffActionType.perm_ban,
        )
    assert exc.value.status_code == 400


def test_apply_chat_moderation_clean_and_dirty(db):
    host = _make_user(db, "modhost")
    game = _make_game(db, host)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump({"blocked_terms": ["badword"]}, handle)
        path = handle.name
    try:
        reload_wordlist()
        clean, inf = apply_chat_moderation(db, user_id=host.id, game_id=game.id, message="hello", wordlist_path=path)
        assert clean == "hello"
        assert inf is None

        censored, inf2 = apply_chat_moderation(
            db, user_id=host.id, game_id=game.id, message="say badword now", wordlist_path=path
        )
        assert "badword" not in censored.lower() or "*" in censored
        assert inf2 is not None
        assert inf2.status == InfractionStatus.pending_review
    finally:
        os.unlink(path)
        reload_wordlist()


def test_apply_ban_rejects_staff_and_self(db):
    admin = _make_user(db, "banadmin", role=UserRole.admin)
    mod = _make_user(db, "banmod", role=UserRole.moderator)
    with pytest.raises(HTTPException):
        apply_ban(
            db,
            actor=admin,
            target=mod,
            reason="nope",
            expires_at=None,
            action_type=StaffActionType.perm_ban,
        )
    with pytest.raises(HTTPException):
        apply_ban(
            db,
            actor=admin,
            target=admin,
            reason="self",
            expires_at=None,
            action_type=StaffActionType.perm_ban,
        )


def test_moderation_routes_full_flow(client, db):
    admin = _make_user(db, "modadmin", role=UserRole.admin)
    target = _make_user(db, "modtarget")
    staff = _make_user(db, "modstaff", role=UserRole.moderator)
    game = _make_game(db, admin)
    infraction = _make_infraction(db, target, game)

    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        queue = client.get("/moderation/queue")
        assert queue.status_code == 200
        assert len(queue.json()) == 1

        missing = client.get("/moderation/infractions/99999")
        assert missing.status_code == 404

        detail = client.get(f"/moderation/infractions/{infraction.id}")
        assert detail.status_code == 200
        assert detail.json()["original_message"] == "bad word here"

        hist_missing = client.get("/moderation/users/99999/history")
        assert hist_missing.status_code == 404

        history = client.get(f"/moderation/users/{target.id}/history")
        assert history.status_code == 200
        assert history.json()["pending_infractions"] == 1
        assert history.json()["total_infractions"] == 1

        assert client.post(
            "/moderation/infractions/99999/dismiss",
            json={"reason": "x"},
        ).status_code == 404

        dismiss = client.post(
            f"/moderation/infractions/{infraction.id}/dismiss",
            json={"reason": "false positive", "notes": "ok"},
        )
        assert dismiss.status_code == 200

        assert client.post(
            "/moderation/users/99999/warn",
            json={"reason": "x"},
        ).status_code == 404
        warn = client.post(
            f"/moderation/users/{target.id}/warn",
            json={"reason": "be nice", "notes": "first"},
        )
        assert warn.status_code == 200

        assert client.post(
            "/moderation/users/99999/mute",
            json={"reason": "x", "hours": 1},
        ).status_code == 404
        assert client.post(
            f"/moderation/users/{staff.id}/mute",
            json={"reason": "x", "hours": 1},
        ).status_code == 403
        mute = client.post(
            f"/moderation/users/{target.id}/mute",
            json={"reason": "spam", "hours": 2, "notes": "chat"},
        )
        assert mute.status_code == 200
        assert "expires_at" in mute.json()

        assert client.post(
            "/moderation/users/99999/temp-ban",
            json={"reason": "x", "days": 1},
        ).status_code == 404
        ban = client.post(
            f"/moderation/users/{target.id}/temp-ban",
            json={"reason": "repeat", "days": 2},
        )
        assert ban.status_code == 200
        db.refresh(target)
        assert target.is_banned is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)
