# tests/apps/backend/app/routes/test_user_route.py
import app.db.models as models

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

    client.cookies.set("session_user", str(user.id))
    response = client.get("/me")
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "gary"
    assert data["elo"] == 1500
    assert data["currency"] == 250


def test_get_me_unauthorized_without_cookie(client):
    response = client.get("/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not logged in"


def test_get_me_unauthorized_invalid_user(client, db):
    client.cookies.set("session_user", "999")
    response = client.get("/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid session"
