# tests/apps/backend/app/routes/test_units_route.py
import app.db.models as models

# ---------- Tests ----------

def test_get_units_summary(client, db):
    db.add_all([
        models.Unit(
            species_id=1,
            form_id=0,
            name="Pikachu",
            species="Mouse",
            asset_folder="pikachu",
            types=["Electric"],
            base_stats={"hp": 35, "attack": 55},
            move_ids=[101],
            ability_ids=[201],
            cost=200
        ),
        models.Unit(
            species_id=2,
            form_id=0,
            name="Charmander",
            species="Lizard",
            asset_folder="charmander",
            types=["Fire"],
            base_stats={"hp": 39, "attack": 52},
            move_ids=[102],
            ability_ids=[202],
            cost=150
        )
    ])
    db.commit()

    response = client.get("/units/summary")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    pikachu = next((u for u in data if u["name"] == "Pikachu"), None)
    assert pikachu is not None
    assert pikachu["types"] == ["Electric"]
    assert pikachu["base_stats"]["hp"] == 35
    assert "cost" in pikachu
