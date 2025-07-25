# tests/apps/backend/app/routes/test_maps_route.py
import app.db.models as models

# ---------- Tests ----------

def test_get_official_maps(client, db):
    # Create 2 maps, only 1 is official
    db.add(models.Map(
        name="Grasslands",
        is_official=True,
        width=10,
        height=10,
        tileset_names=["grass"],
        tile_data={},
        allowed_modes=["Conquest"],
        allowed_player_counts=[2],
        creator_id=None
    ))
    db.add(models.Map(
        name="UnrankedMap",
        is_official=False,
        width=8,
        height=8,
        tileset_names=["forest"],
        tile_data={},
        allowed_modes=["Conquest"],
        allowed_player_counts=[2],
        creator_id=None
    ))
    db.commit()

    response = client.get("/maps/official")
    assert response.status_code == 200
    maps = response.json()
    assert len(maps) == 1
    assert maps[0]["name"] == "Grasslands"
