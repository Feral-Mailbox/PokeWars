from app.schemas.maps import MapDetail

def test_map_detail_fields():
    model = MapDetail(
        id=1,
        name="Lake",
        allowed_modes=["War"],
        allowed_player_counts=[2, 4],
        width=20,
        height=10,
        tileset_names=["forest", "hill"],
        tile_data={}
    )
    assert "forest" in model.tileset_names
