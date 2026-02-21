import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import sessionmaker
from app.db.database import get_sessionmaker
from app.db.models import Game, GameState, GameStatus

scheduler = BackgroundScheduler()

def check_and_advance_turns():
    """Periodically check all active games and advance turns if deadlines have passed."""
    try:
        Session = get_sessionmaker()
        db = Session()
        try:
            # Import here to avoid circular imports
            from app.routes.games import advance_if_expired
            
            games = db.query(Game).join(GameState).filter(
                GameState.status == GameStatus.in_progress
            ).all()
            
            for game in games:
                game_state = db.query(GameState).filter_by(game_id=game.id).first()
                if game_state:
                    advance_if_expired(game, game_state, db)
        except Exception as e:
            print(f"Error in turn advancement: {e}")
        finally:
            db.close()
    except Exception as e:
        print(f"Error connecting to database in turn check: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown of background scheduler."""
    # Startup
    try:
        scheduler.add_job(check_and_advance_turns, "interval", seconds=5)
        scheduler.start()
        print("Background scheduler started")
    except Exception as e:
        print(f"Failed to start scheduler: {e}")
    
    yield
    
    # Shutdown
    try:
        scheduler.shutdown()
        print("Background scheduler stopped")
    except Exception:
        pass

app = FastAPI(lifespan=lifespan)

origins = [os.getenv("CORS_ORIGIN", "http://localhost:5173")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routes import auth, games, maps, moves, user, units, ws

app.include_router(auth.router)
app.include_router(games.router)
app.include_router(maps.router)
app.include_router(moves.router)
app.include_router(user.router)
app.include_router(units.router)
app.include_router(ws.router)