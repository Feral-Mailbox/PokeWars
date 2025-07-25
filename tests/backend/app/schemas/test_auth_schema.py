from app.schemas.auth import RegisterRequest, LoginRequest, UserResponse

def test_register_request_fields():
    data = {"username": "ash", "email": "ash@example.com", "password": "1234"}
    model = RegisterRequest(**data)
    assert model.username == "ash"

def test_login_request_fields():
    model = LoginRequest(username="misty", password="water")
    assert model.password == "water"

def test_user_response_fields():
    model = UserResponse(id=1, username="brock", email="brock@example.com", avatar="default.png", elo=1000, currency=0)
    assert model.model_dump()["elo"] == 1000
