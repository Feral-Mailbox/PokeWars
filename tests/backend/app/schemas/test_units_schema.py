from app.schemas.units import UnitSummary, UnitDetail, GameUnitCreateRequest, GameUnitSchema

def test_unit_summary_fields():
    model = UnitSummary(
        id=1, species_id=10, form_id=None, name="Pikachu",
        asset_folder="pikachu", types=["Electric"], cost=200,
        base_stats={"hp": 35, "attack": 55}
    )
    assert model.base_stats["hp"] == 35

def test_unit_detail_fields():
    model = UnitDetail(
        id=1, species_id=10, form_id=1, name="Lycanroc",
        species="Wolf", asset_folder="lycanroc",
        types=["Rock"], base_stats={"hp": 75}, cost=500,
        evolution_cost=600, evolves_into=[101], is_legendary=False,
        description="A wolf Pokémon"
    )
    assert model.evolves_into == [101]

def test_game_unit_create_request():
    model = GameUnitCreateRequest(
        unit_id=5, x=3, y=4, current_hp=30,
        stat_boosts={"attack": 1}, status_effects=["poison"], states=["confusion", 2], is_fainted=False
    )
    assert model.status_effects == ["poison"]
    assert model.states == ["confusion", 2]

def test_game_unit_schema():
    unit = UnitSummary(
        id=1, species_id=5, form_id=None, name="Charmander",
        asset_folder="charmander", types=["Fire"], cost=100,
        base_stats={"hp": 39}
    )
    model = GameUnitSchema(
        id=1, game_id=2, unit_id=3, user_id=4,
        starting_x=1, starting_y=1, current_x=1, current_y=1,
        level=50, current_hp=39, current_stats={"hp": 39},
        stat_boosts={}, status_effects=[], states=[],
        is_fainted=False, can_move=True, move_pp=[], unit=unit
    )
    assert model.unit.name == "Charmander"
