import app.db.models as models


def test_get_all_abilities(client, db):
    db.add_all([
        models.Ability(id=9, name="Static", slug="static", generation=3),
        models.Ability(id=31, name="Lightning Rod", slug="lightning_rod", generation=3),
    ])
    db.commit()

    resp = client.get("/abilities/all")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "Static"
