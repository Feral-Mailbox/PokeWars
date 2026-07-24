from app.utils.trainer_id import TRAINER_ID_HEX_LENGTH, generate_trainer_id


def test_generate_trainer_id_is_32bit_hex():
    value = generate_trainer_id()
    assert len(value) == TRAINER_ID_HEX_LENGTH
    assert int(value, 16) >= 0
    assert int(value, 16) < 2**32
    assert value == value.upper()


def test_new_user_gets_unique_trainer_id(db):
    import app.db.models as models

    u1 = models.User(username="t1", email="t1@example.com", hashed_password="x")
    u2 = models.User(username="t2", email="t2@example.com", hashed_password="x")
    db.add_all([u1, u2])
    db.commit()
    db.refresh(u1)
    db.refresh(u2)

    assert u1.trainer_id
    assert u2.trainer_id
    assert u1.trainer_id != u2.trainer_id
    assert len(u1.trainer_id) == 8
