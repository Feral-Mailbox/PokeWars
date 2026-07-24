import app.db.models as models
from app.dependencies import get_current_user
from app.main import app
from app.routes.auth import hash_password, verify_password


def _auth_as(user):
    app.dependency_overrides[get_current_user] = lambda: user
    return user


def _clear_auth():
    app.dependency_overrides.pop(get_current_user, None)


def test_update_email_success(client, db):
    user = models.User(
        username="mailer",
        email="old@example.com",
        hashed_password=hash_password("secretpw"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _auth_as(user)
    try:
        resp = client.patch(
            "/me/email",
            json={"email": "New@Example.com", "current_password": "secretpw"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "new@example.com"
        db.refresh(user)
        assert user.email == "new@example.com"
    finally:
        _clear_auth()


def test_update_email_wrong_password(client, db):
    user = models.User(
        username="mailer2",
        email="mailer2@example.com",
        hashed_password=hash_password("secretpw"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _auth_as(user)
    try:
        resp = client.patch(
            "/me/email",
            json={"email": "other@example.com", "current_password": "nope"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Current password is incorrect"
    finally:
        _clear_auth()


def test_update_email_conflict(client, db):
    owner = models.User(
        username="owner",
        email="owner@example.com",
        hashed_password=hash_password("secretpw"),
    )
    other = models.User(
        username="other",
        email="taken@example.com",
        hashed_password=hash_password("secretpw"),
    )
    db.add_all([owner, other])
    db.commit()
    db.refresh(owner)
    _auth_as(owner)
    try:
        resp = client.patch(
            "/me/email",
            json={"email": "taken@example.com", "current_password": "secretpw"},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Email already taken"
    finally:
        _clear_auth()


def test_change_password_success(client, db):
    user = models.User(
        username="changer",
        email="changer@example.com",
        hashed_password=hash_password("oldsecret"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _auth_as(user)
    try:
        resp = client.patch(
            "/me/password",
            json={"current_password": "oldsecret", "new_password": "newsecret1"},
        )
        assert resp.status_code == 200
        db.refresh(user)
        assert verify_password("newsecret1", user.hashed_password)
        assert not verify_password("oldsecret", user.hashed_password)
    finally:
        _clear_auth()


def test_change_password_wrong_current(client, db):
    user = models.User(
        username="changer2",
        email="changer2@example.com",
        hashed_password=hash_password("oldsecret"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _auth_as(user)
    try:
        resp = client.patch(
            "/me/password",
            json={"current_password": "wrong", "new_password": "newsecret1"},
        )
        assert resp.status_code == 401
    finally:
        _clear_auth()


def test_change_password_rejects_same_password(client, db):
    user = models.User(
        username="changer3",
        email="changer3@example.com",
        hashed_password=hash_password("samepass1"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _auth_as(user)
    try:
        resp = client.patch(
            "/me/password",
            json={"current_password": "samepass1", "new_password": "samepass1"},
        )
        assert resp.status_code == 400
    finally:
        _clear_auth()


def test_get_player_public_profile_hides_email(client, db):
    user = models.User(
        username="publicuser",
        email="public@example.com",
        hashed_password=hash_password("secretpw"),
        trainer_id="ABCDEF12",
    )
    db.add(user)
    db.commit()

    resp = client.get("/players/ABCDEF12")
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "publicuser"
    assert "email" not in data
