import pytest
import sqlalchemy.exc
from sqlalchemy import create_engine, exc
from sqlalchemy.orm import sessionmaker
from app.db.models import (
    Base, User, Friend, Game, GameState, GamePlayer, Map, Unit, GameUnit,
    Move, Ability, Tournament, UserUnit, TemporaryState,
    FriendStatus, GameStatus, GameMode, TournamentStatus
)

@pytest.fixture(scope="module")
def db_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    session = TestingSession()
    yield session
    session.close()

# --- ENUMS ---
def test_enum_values():
    assert FriendStatus.pending == "pending"
    assert GameStatus.open == "open"
    assert GameMode.conquest == "Conquest"
    assert TournamentStatus.upcoming == "upcoming"

# --- USER + FRIEND ---
def test_create_user(db_session):
    user = User(username="ash", email="ash@example.com", hashed_password="hashed_pw")
    db_session.add(user)
    db_session.commit()
    assert user.avatar == "default.png"
    assert user.elo == 1000

def test_friend_relationship(db_session):
    u1 = User(username="red", email="red@example.com", hashed_password="pw")
    u2 = User(username="green", email="green@example.com", hashed_password="pw")
    f = Friend(user_id=1, friend_user_id=2, status=FriendStatus.accepted)
    db_session.add_all([u1, u2, f])
    db_session.commit()
    assert f.status == FriendStatus.accepted

# --- MAP + GAME ---
def test_create_map(db_session):
    user = User(username="brock", email="brock@example.com", hashed_password="pw")
    test_map = Map(
        name="Test Map", creator=user,
        width=10, height=10,
        tileset_names=["grass"], tile_data=[[0]*10]*10,
        allowed_modes=["Conquest"], allowed_player_counts=[2],
    )
    db_session.add_all([user, test_map])
    db_session.commit()
    assert test_map.creator.username == "brock"

def test_create_game(db_session):
    host = User(username="misty", email="misty@example.com", hashed_password="pw")
    test_map = Map(name="Lake", creator=host, width=5, height=5,
        tileset_names=["water"], tile_data=[[0]*5]*5,
        allowed_modes=["War"], allowed_player_counts=[2])
    game = Game(
        game_name="Test Game", map=test_map, host_id=1,
        gamemode=GameMode.war, map_name="Lake", link="abc123"
    )
    db_session.add_all([host, test_map, game])
    db_session.commit()
    assert game.map.name == "Lake"

# --- GAME STATE / PLAYER ---
def test_game_state_creation(db_session):
    state = GameState(game_id=1, current_turn=1, players=[1, 2])
    db_session.add(state)
    db_session.commit()
    assert state.status == GameStatus.open

def test_game_player_relationship(db_session):
    gp = GamePlayer(game_id=1, player_id=1, is_ready=True)
    db_session.add(gp)
    db_session.commit()
    assert gp.is_ready

# --- UNIT + GAME UNIT ---
def test_unit_model(db_session):
    unit = Unit(
        species_id=1, name="Pikachu", species="Mouse", asset_folder="pikachu",
        types=["Electric"], base_stats={"hp": 35}, move_ids=[], ability_ids=[],
        cost=300
    )
    db_session.add(unit)
    db_session.commit()
    assert unit.name == "Pikachu"
    assert not unit.is_legendary

def test_game_unit_model(db_session):
    gu = GameUnit(game_id=1, unit_id=1, user_id=1, x=2, y=3, current_hp=35)
    db_session.add(gu)
    db_session.commit()
    assert gu.stat_boosts == {}

# --- MOVE / ABILITY / TOURNAMENT / ETC ---
def test_move_repr(db_session):
    move = Move(name="Thunder", type="Electric", category="Special", power=110, accuracy=70, pp=10)
    db_session.add(move)
    db_session.commit()
    assert "Thunder" in repr(move)

def test_ability_model(db_session):
    ab = Ability(name="Levitate", description="Immune to ground moves")
    db_session.add(ab)
    db_session.commit()
    assert ab.name == "Levitate"

def test_tournament_model(db_session):
    t = Tournament(name="Grand Finals", bracket_info={}, participants=[])
    db_session.add(t)
    db_session.commit()
    assert t.status == TournamentStatus.upcoming

def test_user_unit(db_session):
    uu = UserUnit(user_id=1, unit_id=1, loadout_info={"held_item": "berry"})
    db_session.add(uu)
    db_session.commit()
    assert uu.loadout_info["held_item"] == "berry"

def test_temp_state_model(db_session):
    ts = TemporaryState(name="airborne", description="Flying", immune_to_damage=True)
    db_session.add(ts)
    db_session.commit()
    assert ts.immune_to_damage

# --- FAILURE CASE ---
def test_unique_username_constraint(db_session):
    user1 = User(username="blue", email="blue1@example.com", hashed_password="pw")
    db_session.add(user1)
    db_session.commit()

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        user2 = User(username="blue", email="blue2@example.com", hashed_password="pw")
        db_session.add(user2)
        db_session.commit()

    db_session.rollback()


