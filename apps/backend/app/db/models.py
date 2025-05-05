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
    in_progress = "in_progress"
    completed = "completed"

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
    map_name = Column(String, nullable=False)
    max_players = Column(Integer, default=2)
    host_id = Column(Integer, ForeignKey("users.id"))
    winner_id = Column(Integer, ForeignKey("users.id"))
    turns = Column(Integer)
    replay_log = Column(JSON)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    host = relationship("User", back_populates="hosted_matches", foreign_keys=[host_id])
    players = relationship("User", secondary=game_players_association, back_populates="games")

# ======================
# UNITS
# ======================
class Unit(Base):
    __tablename__ = "units"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    stats = Column(JSON, nullable=False)
    typing = Column(String)
    cost = Column(Integer, default=0)

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