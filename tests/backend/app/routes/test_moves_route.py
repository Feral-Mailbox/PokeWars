import app.db.models as models


def test_get_all_moves_returns_catalog(client, db):
    db.add_all(
        [
            models.Move(name="Tackle", type="Normal", category="Physical", pp=35),
            models.Move(name="Ember", type="Fire", category="Special", pp=25),
        ]
    )
    db.commit()

    resp = client.get("/moves/all")
    assert resp.status_code == 200
    names = {move["name"] for move in resp.json()}
    assert names == {"Tackle", "Ember"}
