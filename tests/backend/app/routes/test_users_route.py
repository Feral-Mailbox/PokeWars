# tests/apps/backend/app/routes/test_user_route.py
import app.db.models as models
from app.utils.session import create_session_token

# ---------- Tests ----------

def test_get_me_success(client, db):
    user = models.User(
        username="gary",
        email="gary@example.com",
        hashed_password="pw",
        avatar="default.png",
        elo=1500,
        currency=250
    )
    db.add(user)
    db.commit()

    client.cookies.set("session_user", create_session_token(user.id))
    response = client.get("/me")
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "gary"
    assert data["elo"] == 1500
    assert data["currency"] == 250
    assert len(data["trainer_id"]) == 8


def test_get_me_unauthorized_without_cookie(client):
    response = client.get("/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not logged in"


def test_get_me_unauthorized_invalid_user(client, db):
    client.cookies.set("session_user", create_session_token(999))
    response = client.get("/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "User not found"


def test_get_player_by_trainer_id_public(client, db):
    user = models.User(
        username="public-ash",
        email="ash-public@example.com",
        hashed_password="pw",
        avatar="default.png",
        elo=1337,
        currency=42,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    response = client.get(f"/players/{user.trainer_id.lower()}")
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "public-ash"
    assert data["trainer_id"] == user.trainer_id
    assert data["elo"] == 1337
    assert data["currency"] == 42
    assert "email" not in data
    assert "id" not in data


def test_get_player_by_trainer_id_not_found(client):
    response = client.get("/players/DEADBEEF")
    assert response.status_code == 404
    assert response.json()["detail"] == "Player not found"


def test_get_player_rejects_invalid_trainer_id_shape(client):
    response = client.get("/players/short")
    assert response.status_code == 404
