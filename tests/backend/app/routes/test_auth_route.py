# tests/apps/backend/app/routes/test_auth_route.py
import app.db.models as models
from app.utils.security import hash_password

def _assert_session_cookie(resp):
    # Try the liberal way first
    if "session_user" in resp.cookies:
        return
    # Fallback to raw header (works when secure/domain prevents client storage)
    set_cookie = resp.headers.get("set-cookie", "")
    assert "session_user=" in set_cookie, f"No session_user cookie. Got: {set_cookie}"


# ---------- Tests ----------

def test_register_success(client):
    resp = client.post("/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "securepw"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "testuser"
    assert data["elo"] == 1000
    _assert_session_cookie(resp)


def test_register_conflict(client, db):
    db.add(models.User(username="testuser",
                       email="test@example.com",
                       hashed_password=hash_password("pw")))
    db.commit()

    resp = client.post("/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "any"
    })
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Username or email already taken"


def test_login_success(client, db):
    db.add(models.User(username="pikachu",
                       email="pikachu@example.com",
                       hashed_password=hash_password("thunder")))
    db.commit()

    resp = client.post("/login", json={"username": "pikachu", "password": "thunder"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "pikachu"
    _assert_session_cookie(resp)


def test_login_failure(client, db):
    db.add(models.User(username="bulba",
                       email="bulba@example.com",
                       hashed_password=hash_password("vine")))
    db.commit()

    resp = client.post("/login", json={"username": "bulba", "password": "wrongpass"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


def test_logout(client):
    resp = client.post("/logout")
    assert resp.status_code == 200
    assert resp.json()["detail"] == "Logged out"
