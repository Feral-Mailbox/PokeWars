from dotenv import load_dotenv
from fastapi import Request, HTTPException
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, Enum, Boolean, Table, create_engine
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from sqlalchemy.sql import func
import enum
import os

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
    in_progress = "in_progress"
    completed = "completed"

class GameMode(str, enum.Enum):
    conquest = "Conquest"
    war = "War"
    capture_the_flag = "Capture The Flag"

# ======================
# JOIN TABLE
# ======================
game_players_association = Table(
    "game_players",
    Base.metadata,
    Column("game_id", Integer, ForeignKey("games.id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("joined_at", DateTime(timezone=True), server_default=func.now())
)

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
    
    hosted_matches = relationship("Game", back_populates="host", foreign_keys="Game.host_id")
    games = relationship("Game", secondary=game_players_association, back_populates="players")
    maps = relationship("Map", back_populates="creator")

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
    status = Column(Enum(GameStatus), default=GameStatus.open, nullable=False)
    is_private = Column(Boolean, default=True)
    game_name = Column(String, nullable=False)
    map_id = Column(Integer, ForeignKey("maps.id"), nullable=False)
    map_name = Column(String, nullable=False)
    max_players = Column(Integer, default=2)
    host_id = Column(Integer, ForeignKey("users.id"))
    winner_id = Column(Integer, ForeignKey("users.id"))
    gamemode = Column(Enum(GameMode), default=GameMode.conquest, nullable=False)
    current_turn = Column(Integer)
    starting_cash = Column(Integer, nullable=True)
    cash_per_turn = Column(Integer, nullable=True)
    max_turns = Column(Integer, nullable=True)
    unit_limit = Column(Integer, nullable=True)
    replay_log = Column(JSON)
    link = Column(String, unique=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    host = relationship("User", back_populates="hosted_matches", foreign_keys=[host_id])
    players = relationship("User", secondary=game_players_association, back_populates="games")
    map = relationship("Map", back_populates="games")

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
    name = Column(String, unique=True, nullable=False)
    type = Column(String, nullable=False)
    category = Column(String, nullable=False)
    power = Column(Integer, nullable=True)
    accuracy = Column(Integer, nullable=True)
    pp = Column(Integer, nullable=True)
    description = Column(String, nullable=True)

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

# ======================
# DB INIT
# =====================
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)