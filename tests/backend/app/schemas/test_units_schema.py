from app.schemas.units import UnitSummary, UnitDetail, GameUnitCreateRequest, GameUnitSchema


def _unit_summary_kwargs(**overrides):
    data = {
        "id": 1,
        "species_id": 10,
        "form_id": None,
        "name": "Pikachu",
        "asset_folder": "pikachu",
        "types": ["Electric"],
        "cost": 200,
        "base_stats": {"hp": 35, "attack": 55},
        "level_up_moves": [],
        "tm_moves": [],
        "egg_moves": [],
        "equipped_moves": [],
        "ability_ids": [],
        "portrait_credits": [],
        "sprite_credits": [],
        "weight": 6.0,
        "height": 0.4,
    }
    data.update(overrides)
    return data


def test_unit_summary_fields():
    model = UnitSummary(**_unit_summary_kwargs())
    assert model.base_stats["hp"] == 35
    assert model.is_titanic is False
    assert model.titanic_footprint is None


def test_unit_summary_titanic_fields():
    model = UnitSummary(
        **_unit_summary_kwargs(
            is_titanic=True,
            titanic_footprint={"north": 3, "west": 1, "east": 1},
        )
    )
    assert model.is_titanic is True
    assert model.titanic_footprint == {"north": 3, "west": 1, "east": 1}


def test_unit_detail_fields():
    model = UnitDetail(
        id=1,
        species_id=10,
        form_id=1,
        name="Lycanroc",
        species="Wolf",
        asset_folder="lycanroc",
        types=["Rock"],
        base_stats={"hp": 75},
        cost=500,
        level_up_moves=[],
        tm_moves=[],
        egg_moves=[],
        equipped_moves=[],
        ability_ids=[],
        evolution_cost=600,
        evolves_into=[101],
        is_legendary=False,
        description="A wolf Pokémon",
        portrait_credits=[],
        sprite_credits=[],
        weight=25.0,
        height=0.8,
    )
    assert model.evolves_into == [101]


def test_game_unit_create_request():
    model = GameUnitCreateRequest(
        unit_id=5,
        x=3,
        y=4,
        current_hp=30,
        status_effects=["poison"],
        states=["confusion", 2],
        is_fainted=False,
    )
    assert model.status_effects == ["poison"]
    assert model.states == ["confusion", 2]


def test_game_unit_schema():
    unit = UnitSummary(
        **_unit_summary_kwargs(
            id=1,
            species_id=5,
            name="Charmander",
            asset_folder="charmander",
            types=["Fire"],
            cost=100,
            base_stats={"hp": 39},
            weight=8.5,
            height=0.6,
        )
    )
    model = GameUnitSchema(
        id=1,
        game_id=2,
        unit_id=3,
        user_id=4,
        starting_x=1,
        starting_y=1,
        current_x=1,
        current_y=1,
        level=50,
        current_hp=39,
        current_stats={"hp": 39},
        stat_boosts={},
        status_effects=[],
        states=[],
        is_fainted=False,
        can_move=True,
        move_pp=[],
        unit=unit,
    )
    assert model.unit.name == "Charmander"
