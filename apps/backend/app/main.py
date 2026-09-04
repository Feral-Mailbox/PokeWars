import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import sessionmaker
from app.startup import run_startup_tasks
from app.db.database import get_sessionmaker
from app.db.models import Game, GameState, GameStatus

scheduler = BackgroundScheduler()
_background_lock_fd = None


def acquire_background_leader_lock() -> bool:
    """
    Only one uvicorn worker in this container should run migrations + APScheduler.

    Uses a non-blocking exclusive flock so multi-worker startups do not race Alembic
    or duplicate turn-timer jobs.
    """
    global _background_lock_fd
    if os.getenv("SKIP_STARTUP_TASKS") == "1" or os.getenv("PYTEST_CURRENT_TEST"):
        # Tests still exercise lifespan; treat the test process as leader unless
        # a caller patches this function.
        return True

    path = os.getenv("BACKGROUND_LOCK_PATH", "/tmp/poketactics-background.lock")
    try:
        fd = open(path, "w", encoding="utf-8")
    except OSError as exc:
        print(f"Background lock unavailable ({exc}); skipping scheduler/startup on this worker")
        return False

    try:
        import fcntl

        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fd.close()
        return False
    except OSError as exc:
        fd.close()
        print(f"Background lock failed ({exc}); skipping scheduler/startup on this worker")
        return False

    _background_lock_fd = fd
    return True


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


def expire_pending_invitations():
    """Expire timed-out game invitations and announce them in lobby chat."""
    try:
        Session = get_sessionmaker()
        db = Session()
        try:
            from app.routes.invitations import expire_due_invitations

            expire_due_invitations(db)
        except Exception as e:
            print(f"Error expiring invitations: {e}")
        finally:
            db.close()
    except Exception as e:
        print(f"Error connecting to database in invitation expiry: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown of background scheduler."""
    is_leader = acquire_background_leader_lock()

    if is_leader:
        try:
            scheduler.add_job(check_and_advance_turns, "interval", seconds=5)
            scheduler.add_job(expire_pending_invitations, "interval", seconds=15)
            scheduler.start()
            print("Background scheduler started")
        except Exception as e:
            print(f"Failed to start scheduler: {e}")

        run_startup_tasks()
    else:
        print("Follower uvicorn worker: skipping migrations and background scheduler")
    
    yield
    
    # Shutdown
    if is_leader:
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

from app.routes import auth, games, maps, moves, user, units, ws, moderation, admin, items, abilities, invitations, announcements

app.include_router(auth.router)
app.include_router(games.router)
app.include_router(maps.router)
app.include_router(moves.router)
app.include_router(items.router)
app.include_router(abilities.router)
app.include_router(user.router)
app.include_router(invitations.router)
app.include_router(announcements.router)
app.include_router(units.router)
app.include_router(ws.router)
app.include_router(moderation.router)
app.include_router(admin.router)
