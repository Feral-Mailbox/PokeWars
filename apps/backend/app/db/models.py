from dotenv import load_dotenv
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, Enum, Table, create_engine
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from sqlalchemy.sql import func
import enum
import os

Base = declarative_base()

# Enums for friend status and tournament status
class FriendStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"

class TournamentStatus(str, enum.Enum):
    upcoming = "upcoming"
    ongoing = "ongoing"
    completed = "completed"

# Users table
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    avatar = Column(String, default="default.png")
    elo = Column(Integer, default=1000)
    currency = Column(Integer, default=0)

# Friendships
class Friend(Base):
    __tablename__ = "friends"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    friend_user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(Enum(FriendStatus), default=FriendStatus.pending)

# Matches
class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)
    player1_id = Column(Integer, ForeignKey("users.id"))
    player2_id = Column(Integer, ForeignKey("users.id"))
    winner_id = Column(Integer, ForeignKey("users.id"))
    turns = Column(Integer)
    replay_log = Column(JSON)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

# Units
class Unit(Base):
    __tablename__ = "units"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    stats = Column(JSON, nullable=False)
    typing = Column(String)
    cost = Column(Integer, default=0)

# User-Unlocked Units
class UserUnit(Base):
    __tablename__ = "user_units"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    unit_id = Column(Integer, ForeignKey("units.id"))
    loadout_info = Column(JSON)

# Tournaments
class Tournament(Base):
    __tablename__ = "tournaments"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    start_time = Column(DateTime(timezone=True))
    bracket_info = Column(JSON)
    participants = Column(JSON)
    status = Column(Enum(TournamentStatus), default=TournamentStatus.upcoming)

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
