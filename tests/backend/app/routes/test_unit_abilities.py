import pytest
from fastapi.testclient import TestClient

import app.db.models as models
from app.dependencies import get_current_user, get_db
from app.main import app
from app.routes.games import (
    HIDDEN_ABILITY_COST,
    ability_change_net_cost,
    attach_game_unit_loadout_fields,
    get_unit_ability_id,
    get_unit_ability_names,
    is_hidden_ability_for_unit,
    set_unit_ability_id,
    unit_can_learn_ability,
)


@pytest.fixture(scope="function")
def user(db):
    user = models.User(
        username="player1",
        email="player1@example.com",
        hashed_password="hashed",
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture(scope="function")
def client(db, user):
    def override_get_db():
        yield db

    def override_get_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_get_unit_ability_id_defaults_to_first_template_ability(db):
    unit_def = models.Unit(
        species_id=77,
        form_id=None,
        name="Pikachu",
        species="Mouse Pokémon",
        asset_folder="077_pikachu",
        types=["Electric"],
        base_stats={"hp": 35},
        level_up_moves=[],
        tm_moves=[],
        egg_moves=[],
        equipped_moves=[],
        ability_ids=[9, 31],
        hidden_ability=31,
        cost=400,
    )
    game_unit = models.GameUnit(
        game_id=1,
        unit_id=1,
        user_id=1,
        starting_x=0,
        starting_y=0,
        current_x=0,
        current_y=0,
        current_hp=35,
        current_stats={"hp": 35},
        unit=unit_def,
    )

    assert get_unit_ability_id(game_unit) == 9


def test_set_unit_ability_id_persists_selected_ability(db):
    static = models.Ability(id=9, name="Static", slug="static", generation=3)
    lightning_rod = models.Ability(
        id=31, name="Lightning Rod", slug="lightning_rod", generation=3
    )
    db.add_all([static, lightning_rod])
    db.commit()

    unit_def = models.Unit(
        species_id=77,
        form_id=None,
        name="Pikachu",
        species="Mouse Pokémon",
        asset_folder="077_pikachu",
        types=["Electric"],
        base_stats={"hp": 35},
        level_up_moves=[],
        tm_moves=[],
        egg_moves=[],
        equipped_moves=[],
        ability_ids=[9],
        hidden_ability=31,
        cost=400,
    )
    game_unit = models.GameUnit(
        game_id=1,
        unit_id=1,
        user_id=1,
        starting_x=0,
        starting_y=0,
        current_x=0,
        current_y=0,
        current_hp=35,
        current_stats={"hp": 35},
        unit=unit_def,
        flags={"ability_id": 9},
    )

    assert get_unit_ability_names(game_unit, db) == {"static"}

    set_unit_ability_id(game_unit, 31, db)
    db.commit()

    assert get_unit_ability_id(game_unit) == 31
    assert get_unit_ability_names(game_unit, db) == {"lightning rod"}

    attach_game_unit_loadout_fields(game_unit, db)
    assert game_unit.ability == "Lightning Rod"
    assert game_unit.ability_id == 31


def test_ability_change_net_cost_for_hidden_ability():
    unit_def = models.Unit(
        species_id=77,
        form_id=None,
        name="Pikachu",
        species="Mouse Pokémon",
        asset_folder="077_pikachu",
        types=["Electric"],
        base_stats={"hp": 35},
        level_up_moves=[],
        tm_moves=[],
        egg_moves=[],
        equipped_moves=[],
        ability_ids=[9],
        hidden_ability=31,
        cost=400,
    )

    assert ability_change_net_cost(unit_def, 9, 31) == HIDDEN_ABILITY_COST
    assert ability_change_net_cost(unit_def, 31, 9) == -HIDDEN_ABILITY_COST
    assert ability_change_net_cost(unit_def, 9, 9) == 0


def test_unit_can_learn_ability_allows_regular_and_hidden():
    unit_def = models.Unit(
        species_id=77,
        form_id=None,
        name="Pikachu",
        species="Mouse Pokémon",
        asset_folder="077_pikachu",
        types=["Electric"],
        base_stats={"hp": 35},
        level_up_moves=[],
        tm_moves=[],
        egg_moves=[],
        equipped_moves=[],
        ability_ids=[9],
        hidden_ability=31,
        cost=400,
    )

    assert unit_can_learn_ability(unit_def, 9)
    assert unit_can_learn_ability(unit_def, 31)
    assert not unit_can_learn_ability(unit_def, 99)


def test_change_unit_ability_endpoint_updates_cash(client, db, user):
    static = models.Ability(id=9, name="Static", slug="static", generation=3)
    lightning_rod = models.Ability(
        id=31, name="Lightning Rod", slug="lightning_rod", generation=3
    )
    unit_def = models.Unit(
        species_id=77,
        form_id=None,
        name="Pikachu",
        species="Mouse Pokémon",
        asset_folder="077_pikachu",
        types=["Electric"],
        base_stats={"hp": 35},
        level_up_moves=[],
        tm_moves=[],
        egg_moves=[],
        equipped_moves=[],
        ability_ids=[9],
        hidden_ability=31,
        cost=400,
    )
    game = models.Game(
        game_name="Ability Game",
        map_id=None,
        map_name="n/a",
        max_players=2,
        gamemode="Conquest",
        is_private=False,
        host_id=user.id,
        link="ability-game",
    )
    db.add_all([static, lightning_rod, unit_def, game])
    db.flush()

    state = models.GameState(game_id=game.id, status=models.GameStatus.preparation)
    player = models.GamePlayer(
        game_id=game.id,
        player_id=user.id,
        cash_remaining=300,
        game_units=[],
    )
    game_unit = models.GameUnit(
        game_id=game.id,
        unit_id=unit_def.id,
        user_id=user.id,
        starting_x=1,
        starting_y=1,
        current_x=1,
        current_y=1,
        current_hp=100,
        current_stats={"hp": 100},
        flags={"ability_id": 9},
    )
    db.add_all([state, player, game_unit])
    db.flush()
    player.game_units = [game_unit.id]
    db.commit()

    resp = client.post(
        f"/games/{game.link}/units/{game_unit.id}/ability",
        json={"ability_id": 31},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cash_remaining"] == 50
    assert data["unit"]["ability"] == "Lightning Rod"
    assert data["unit"]["ability_id"] == 31

    resp = client.post(
        f"/games/{game.link}/units/{game_unit.id}/ability",
        json={"ability_id": 9},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cash_remaining"] == 300
    assert data["unit"]["ability_id"] == 9


def test_change_unit_ability_rejects_insufficient_cash(client, db, user):
    static = models.Ability(id=9, name="Static", slug="static", generation=3)
    lightning_rod = models.Ability(
        id=31, name="Lightning Rod", slug="lightning_rod", generation=3
    )
    unit_def = models.Unit(
        species_id=77,
        form_id=None,
        name="Pikachu",
        species="Mouse Pokémon",
        asset_folder="077_pikachu",
        types=["Electric"],
        base_stats={"hp": 35},
        level_up_moves=[],
        tm_moves=[],
        egg_moves=[],
        equipped_moves=[],
        ability_ids=[9],
        hidden_ability=31,
        cost=400,
    )
    game = models.Game(
        game_name="Ability Game",
        map_id=None,
        map_name="n/a",
        max_players=2,
        gamemode="Conquest",
        is_private=False,
        host_id=user.id,
        link="ability-game-2",
    )
    db.add_all([static, lightning_rod, unit_def, game])
    db.flush()

    state = models.GameState(game_id=game.id, status=models.GameStatus.preparation)
    player = models.GamePlayer(
        game_id=game.id,
        player_id=user.id,
        cash_remaining=100,
        game_units=[],
    )
    game_unit = models.GameUnit(
        game_id=game.id,
        unit_id=unit_def.id,
        user_id=user.id,
        starting_x=1,
        starting_y=1,
        current_x=1,
        current_y=1,
        current_hp=100,
        current_stats={"hp": 100},
        flags={"ability_id": 9},
    )
    db.add_all([state, player, game_unit])
    db.commit()

    resp = client.post(
        f"/games/{game.link}/units/{game_unit.id}/ability",
        json={"ability_id": 31},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Not enough cash"
