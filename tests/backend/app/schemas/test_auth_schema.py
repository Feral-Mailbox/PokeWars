from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    UserResponse,
    UpdateEmailRequest,
    ChangePasswordRequest,
)

def test_register_request_fields():
    data = {"username": "ash", "email": "ash@example.com", "password": "1234"}
    model = RegisterRequest(**data)
    assert model.username == "ash"

def test_login_request_fields():
    model = LoginRequest(username="misty", password="water")
    assert model.password == "water"

def test_user_response_fields():
    model = UserResponse(
        id=1,
        trainer_id="a3f2c91b",
        username="brock",
        email="brock@example.com",
        avatar="default.png",
        elo_conquest=1000, elo_war=1000,
        currency=0,
        role="user",
    )
    assert model.model_dump()["elo_conquest"] == 1000
    assert model.trainer_id == "A3F2C91B"


def test_update_email_request_fields():
    model = UpdateEmailRequest(email="new@example.com", current_password="secret")
    assert model.email == "new@example.com"


def test_change_password_request_min_length():
    model = ChangePasswordRequest(current_password="old", new_password="12345678")
    assert model.new_password == "12345678"
