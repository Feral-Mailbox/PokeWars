from dotenv import load_dotenv
from fastapi import Request, HTTPException
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, Enum, Boolean, Table, create_engine
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from sqlalchemy.sql import func
import enum

Base = declarative_base()

# ======================
# ENUMS
# ======================
class FriendStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"

class TournamentStatus(str, enum.Enum):
    upcoming = "upcoming"
    ongoing = "ongoing"
    completed = "completed"

class GameStatus(str, enum.Enum):
    open = "open" 
    closed = "closed"
    preparation = "preparation"
    in_progress = "in_progress"
    completed = "completed"

class GameMode(str, enum.Enum):
    conquest = "Conquest"
    war = "War"
    capture_the_flag = "Capture The Flag"

# ======================
# USER
# ======================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    avatar = Column(String, default="default.png")
    elo = Column(Integer, default=1000)
    currency = Column(Integer, default=0)
    
    maps = relationship("Map", back_populates="creator")
    game_states = relationship("GamePlayer", back_populates="player")
    game_units = relationship("GameUnit", back_populates="owner")

# ======================
# FRIENDS
# ======================
class Friend(Base):
    __tablename__ = "friends"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    friend_user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(Enum(FriendStatus), default=FriendStatus.pending)

# ======================
# GAMES
# ======================
class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True)
    game_name = Column(String, nullable=False)
    map_id = Column(Integer, ForeignKey("maps.id"), nullable=False)
    map_name = Column(String, nullable=False)
    max_players = Column(Integer, default=2)
    gamemode = Column(Enum(GameMode), default=GameMode.conquest, nullable=False)
    starting_cash = Column(Integer, nullable=True)
    cash_per_turn = Column(Integer, nullable=True)
    max_turns = Column(Integer, nullable=True)
    unit_limit = Column(Integer, nullable=True)
    is_private = Column(Boolean, default=True)
    host_id = Column(Integer, ForeignKey("users.id"))
    link = Column(String, unique=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    map = relationship("Map", back_populates="games")
    player_states = relationship("GamePlayer", back_populates="game")
    game_units = relationship("GameUnit", back_populates="game")


# ======================
# GAME STATE
# ======================
class GameState(Base):
    __tablename__ = "game_status"

    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), unique=True)
    current_turn = Column(Integer)
    status = Column(Enum(GameStatus), default=GameStatus.open, nullable=False)
    players = Column(MutableList.as_mutable(JSON), nullable=False, default=list)
    winner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    replay_log = Column(MutableList.as_mutable(JSON), nullable=True, default=list)

    # Relationships
    game = relationship("Game")
    winner = relationship("User")

# ======================
# GAME PLAYER STATE
# ======================
class GamePlayer(Base):
    __tablename__ = "game_players"

    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"))
    player_id = Column(Integer, ForeignKey("users.id"))
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    cash_remaining = Column(Integer, default=0)
    game_units = Column(MutableList.as_mutable(JSON), default=list)
    is_ready = Column(Boolean, default=False, nullable=True)

    game = relationship("Game", back_populates="player_states")
    player = relationship("User", back_populates="game_states")


# ======================
# MAPS
# ======================
class Map(Base):
    __tablename__ = "maps"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_official = Column(Boolean, default=False, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    tileset_names = Column(JSON, nullable=False, default=list)
    tile_data = Column(JSON, nullable=False)
    allowed_modes = Column(JSON, nullable=False, default=list)
    allowed_player_counts = Column(JSON, nullable=False, default=[2])
    preview_image = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    creator = relationship("User", back_populates="maps")
    games = relationship("Game", back_populates="map")

# ======================
# UNITS
# ======================
class Unit(Base):
    __tablename__ = "units"

    id = Column(Integer, primary_key=True)
    species_id = Column(Integer, nullable=False)
    form_id = Column(Integer, nullable=True)
    name = Column(String, nullable=False)
    species = Column(String, nullable=False)
    asset_folder = Column(String, nullable=False)
    types = Column(JSON, nullable=False)
    base_stats = Column(JSON, nullable=False)
    move_ids = Column(JSON, nullable=False, default=list)
    ability_ids = Column(JSON, nullable=False, default=list)
    cost = Column(Integer, default=0)
    evolution_cost = Column(JSON, nullable=True, default=0)
    evolves_into = Column(JSON, nullable=True)
    is_legendary = Column(Boolean, default=False)
    description = Column(String, nullable=True)
    portrait_credits = Column(JSON, nullable=False, default=list)
    sprite_credits = Column(JSON, nullable=False, default=list)

    game_units = relationship("GameUnit", back_populates="unit")

# ======================
# GAME UNIT
# ======================
class GameUnit(Base):
    __tablename__ = "game_units"

    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"))
    unit_id = Column(Integer, ForeignKey("units.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)
    current_hp = Column(Integer, nullable=False)
    stat_boosts = Column(JSON, default=dict)  # e.g., { "attack": 1, "speed": -2 }
    status_effects = Column(JSON, default=list)  # e.g., ["poison", "paralysis"]
    is_fainted = Column(Boolean, default=False)

    game = relationship("Game", back_populates="game_units")
    unit = relationship("Unit", back_populates="game_units")
    owner = relationship("User", back_populates="game_units")

# ======================
# TEMPORARY STATE
# ======================
class TemporaryState(Base):
    __tablename__ = "temporary_states"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)  # e.g. "airborne"
    description = Column(String, nullable=True)

    default_duration = Column(Integer, nullable=True)

    vulnerable_to = Column(MutableList.as_mutable(JSON), default=list)

    immune_to_damage = Column(Boolean, default=False)
    immune_to_status = Column(Boolean, default=False)
    disables_targeting = Column(Boolean, default=False)
    can_collide = Column(Boolean, default=False)

# ======================
# USER-UNIT RELATION
# ======================
class UserUnit(Base):
    __tablename__ = "user_units"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    unit_id = Column(Integer, ForeignKey("units.id"))
    loadout_info = Column(JSON)

# ======================
# MOVES
# ======================
class Move(Base):
    __tablename__ = "moves"

    id = Column(Integer, primary_key=True)
    
    # Core move details
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    type = Column(String, nullable=False)
    category = Column(String, nullable=False)

    # Gameplay mechanics
    power = Column(Integer, nullable=True)
    accuracy = Column(Integer, nullable=True)
    pp = Column(Integer, nullable=True)

    # Move effects
    makes_contact = Column(Boolean, nullable=True, default=False)
    affected_by_protect = Column(Boolean, nullable=True, default=False)
    affected_by_magic_coat = Column(Boolean, nullable=True, default=False)
    affected_by_snatch = Column(Boolean, nullable=True, default=False)
    affected_by_mirror_move = Column(Boolean, nullable=True, default=False)
    affected_by_kings_rock = Column(Boolean, nullable=True, default=False)

    # Tactical attributes
    range = Column(String, nullable=True)
    targeting = Column(String, nullable=True, default="enemy")
    cooldown = Column(Integer, nullable=True)

    # Special effects
    effects = Column(MutableList.as_mutable(JSON), default=list)  # e.g. ["burn", "lower_defense"]

    def __repr__(self):
        return f"<Move(name={self.name}, type={self.type}, power={self.power})>"

# ======================
# ABILITIES
# ======================
class Ability(Base):
    __tablename__ = "abilities"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    effect = Column(JSON, nullable=True)

# ======================
# TOURNAMENT
# ======================
class Tournament(Base):
    __tablename__ = "tournaments"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    start_time = Column(DateTime(timezone=True))
    bracket_info = Column(JSON)
    participants = Column(JSON)
    status = Column(Enum(TournamentStatus), default=TournamentStatus.upcoming)
