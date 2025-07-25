from app.schemas.user import UserOut

def test_user_out_fields():
    model = UserOut(id=7, username="Gary")
    assert model.username == "Gary"
