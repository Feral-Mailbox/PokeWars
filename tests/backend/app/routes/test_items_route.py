import app.db.models as models


def test_get_all_items_returns_catalog(client, db):
    db.add_all(
        [
            models.Item(name="Oran Berry", slug="oran_berry", category="berry", cost=100),
            models.Item(name="Leftovers", slug="leftovers", category="held", cost=200),
        ]
    )
    db.commit()

    resp = client.get("/items/all")
    assert resp.status_code == 200
    payload = resp.json()
    assert {item["slug"] for item in payload} == {"oran_berry", "leftovers"}


def test_get_all_items_filters_by_category(client, db):
    db.add_all(
        [
            models.Item(name="Oran Berry", slug="oran_berry", category="berry", cost=100),
            models.Item(name="Leftovers", slug="leftovers", category="held", cost=200),
        ]
    )
    db.commit()

    resp = client.get("/items/all", params={"category": "berry"})
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 1
    assert payload[0]["slug"] == "oran_berry"
