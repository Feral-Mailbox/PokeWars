import app.db.models as models
from app.dependencies import get_current_user
from app.main import app
from app.routes.auth import hash_password
from tests.backend.conftest import make_test_map


def _auth_as(user):
    app.dependency_overrides[get_current_user] = lambda: user


def _clear_auth():
    app.dependency_overrides.pop(get_current_user, None)


def _make_open_game(db, host):
    map_obj = make_test_map(db, creator_id=host.id)
    game = models.Game(
        game_name="Invite Lobby",
        map_id=map_obj.id,
        map_name=map_obj.name,
        max_players=2,
        gamemode="Conquest",
        is_private=True,
        host_id=host.id,
        link="invite-lobby-1",
        starting_cash=1000,
    )
    db.add(game)
    db.flush()
    db.add(models.GamePlayer(game_id=game.id, player_id=host.id, cash_remaining=1000))
    db.add(
        models.GameState(
            game_id=game.id,
            current_turn=0,
            status=models.GameStatus.open,
            players=[host.id],
            replay_log=[],
        )
    )
    db.commit()
    db.refresh(game)
    return game


def test_create_accept_invitation_flow(client, db):
    host = models.User(
        username="host-invite",
        email="host-invite@example.com",
        hashed_password=hash_password("secretpw"),
    )
    guest = models.User(
        username="guest-invite",
        email="guest-invite@example.com",
        hashed_password=hash_password("secretpw"),
    )
    db.add_all([host, guest])
    db.commit()
    db.refresh(host)
    db.refresh(guest)
    game = _make_open_game(db, host)

    _auth_as(host)
    try:
        create = client.post(
            "/invitations",
            json={"game_id": game.id, "invitee_username": guest.username},
        )
        assert create.status_code == 201, create.text
        invite = create.json()
        assert invite["status"] == "pending"
        assert invite["invitee_id"] == guest.id
        assert invite.get("expires_at")
        invitation_id = invite["id"]

        state = db.query(models.GameState).filter_by(game_id=game.id).first()
        invite_logs = [
            row.get("message")
            for row in (state.replay_log or [])
            if isinstance(row, dict) and row.get("event") == "system_log"
        ]
        assert any("host-invite invited guest-invite" in msg for msg in invite_logs)

        inbox_host = client.get("/invitations/inbox")
        assert inbox_host.status_code == 200
        assert inbox_host.json()["pending_count"] == 0
    finally:
        _clear_auth()

    _auth_as(guest)
    try:
        inbox = client.get("/invitations/inbox")
        assert inbox.status_code == 200
        body = inbox.json()
        assert body["pending_count"] == 1
        assert body["invitations"][0]["id"] == invitation_id

        accept = client.post(f"/invitations/{invitation_id}/accept")
        assert accept.status_code == 200, accept.text
        assert accept.json()["status"] == "accepted"

        state = db.query(models.GameState).filter_by(game_id=game.id).first()
        assert guest.id in state.players
        assert state.status == models.GameStatus.closed
    finally:
        _clear_auth()


def test_decline_invitation(client, db):
    host = models.User(
        username="host-decline",
        email="host-decline@example.com",
        hashed_password=hash_password("secretpw"),
    )
    guest = models.User(
        username="guest-decline",
        email="guest-decline@example.com",
        hashed_password=hash_password("secretpw"),
    )
    db.add_all([host, guest])
    db.commit()
    db.refresh(host)
    db.refresh(guest)
    game = _make_open_game(db, host)

    _auth_as(host)
    try:
        create = client.post(
            "/invitations",
            json={"game_id": game.id, "invitee_id": guest.id},
        )
        assert create.status_code == 201
        invitation_id = create.json()["id"]
    finally:
        _clear_auth()

    _auth_as(guest)
    try:
        cancel = client.post(f"/invitations/{invitation_id}/cancel")
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "declined"
        state = db.query(models.GameState).filter_by(game_id=game.id).first()
        decline_logs = [
            row.get("message")
            for row in (state.replay_log or [])
            if isinstance(row, dict) and row.get("event") == "system_log"
        ]
        assert any("guest-decline declined the invitation" in msg for msg in decline_logs)
    finally:
        _clear_auth()


def test_invitation_timeout_expires_and_logs_chat(client, db, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.routes import invitations as invitations_routes

    host = models.User(
        username="host-timeout",
        email="host-timeout@example.com",
        hashed_password=hash_password("secretpw"),
    )
    guest = models.User(
        username="guest-timeout",
        email="guest-timeout@example.com",
        hashed_password=hash_password("secretpw"),
    )
    db.add_all([host, guest])
    db.commit()
    db.refresh(host)
    db.refresh(guest)
    game = _make_open_game(db, host)

    _auth_as(host)
    try:
        create = client.post(
            "/invitations",
            json={"game_id": game.id, "invitee_id": guest.id},
        )
        assert create.status_code == 201
        invitation_id = create.json()["id"]
    finally:
        _clear_auth()

    invitation = db.query(models.GameInvitation).filter_by(id=invitation_id).first()
    invitation.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    expired = invitations_routes.expire_due_invitations(db)
    assert expired == 1
    db.refresh(invitation)
    assert invitation.status == models.InvitationStatus.expired

    state = db.query(models.GameState).filter_by(game_id=game.id).first()
    timeout_logs = [
        row.get("message")
        for row in (state.replay_log or [])
        if isinstance(row, dict) and row.get("event") == "system_log"
    ]
    assert any("Invitation to guest-timeout timed out" in msg for msg in timeout_logs)


def test_search_players(client, db):
    me = models.User(
        username="searcher",
        email="searcher@example.com",
        hashed_password=hash_password("secretpw"),
        trainer_id="ABCD1234",
    )
    other = models.User(
        username="targetuser",
        email="targetuser@example.com",
        hashed_password=hash_password("secretpw"),
        trainer_id="ZZZZ9999",
    )
    db.add_all([me, other])
    db.commit()

    _auth_as(me)
    try:
        by_name = client.get("/players/search", params={"q": "target"})
        assert by_name.status_code == 200
        assert any(row["username"] == "targetuser" for row in by_name.json())

        by_trainer = client.get("/players/search", params={"q": "zzzz9999"})
        assert by_trainer.status_code == 200
        assert by_trainer.json()[0]["trainer_id"] == "ZZZZ9999"
    finally:
        _clear_auth()
