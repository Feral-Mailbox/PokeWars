import asyncio
import logging

import redis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db.database import get_sessionmaker
from app.db.models import Game, GamePlayer, GameState, User
from app.dependencies import ban_is_active
from app.utils.session import decode_session_token

router = APIRouter()
logger = logging.getLogger("ws")

r = redis.Redis(host="redis", port=6379, decode_responses=True)

SPECTATOR_CONN_TTL_SECONDS = 60 * 60 * 12


def _resolve_authenticated_user(session_token: str | None) -> User | None:
    user_id = decode_session_token(session_token or "")
    if user_id is None:
        return None

    Session = get_sessionmaker()
    db = Session()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or ban_is_active(user):
            return None
        return user
    finally:
        db.close()


def _user_is_game_participant(user_id: int, link: str) -> bool:
    Session = get_sessionmaker()
    db = Session()
    try:
        game = db.query(Game).filter(Game.link == link).first()
        if not game:
            return False
        participant = (
            db.query(GamePlayer)
            .filter_by(game_id=game.id, player_id=user_id)
            .first()
        )
        return participant is not None
    finally:
        db.close()


def _game_exists(link: str) -> bool:
    Session = get_sessionmaker()
    db = Session()
    try:
        return db.query(Game.id).filter(Game.link == link).first() is not None
    finally:
        db.close()


def _spectator_conn_key(link: str, user_id: int) -> str:
    return f"game_spectator_conn:{link}:{user_id}"


def _register_spectator_connection(link: str, user_id: int) -> bool:
    """Return True when this is the first live spectator connection for the user."""
    key = _spectator_conn_key(link, user_id)
    count = int(r.incr(key))
    r.expire(key, SPECTATOR_CONN_TTL_SECONDS)
    return count == 1


def _unregister_spectator_connection(link: str, user_id: int) -> bool:
    """Return True when the user has no remaining spectator connections."""
    key = _spectator_conn_key(link, user_id)
    count = int(r.decr(key))
    if count <= 0:
        r.delete(key)
        return True
    return False


def _announce_spectator_system_log(link: str, message: str) -> None:
    from app.routes.games import publish_system_log_event

    Session = get_sessionmaker()
    db = Session()
    try:
        game = db.query(Game).filter(Game.link == link).first()
        if game is None:
            return
        state = db.query(GameState).filter(GameState.game_id == game.id).first()
        publish_system_log_event(link, message, state, db)
        db.commit()
    except Exception:
        logger.exception("Failed to publish spectator system log for game %s", link)
        db.rollback()
    finally:
        db.close()


@router.websocket("/api/ws/game/{link}")
async def websocket_endpoint(websocket: WebSocket, link: str):
    user = _resolve_authenticated_user(websocket.cookies.get("session_user"))
    if user is None:
        await websocket.close(code=4401, reason="Authentication required")
        return

    if not _game_exists(link):
        await websocket.close(code=4404, reason="Game not found")
        return

    is_participant = _user_is_game_participant(user.id, link)
    is_spectator = not is_participant
    spectator_registered = False

    await websocket.accept()

    if is_spectator:
        try:
            if _register_spectator_connection(link, user.id):
                _announce_spectator_system_log(
                    link, f"{user.username} is now spectating"
                )
            spectator_registered = True
        except Exception:
            logger.exception(
                "Failed to register spectator %s for game %s", user.id, link
            )

    pubsub = r.pubsub()
    pubsub.subscribe(f"game_updates:{link}")

    async def read_redis_messages():
        loop = asyncio.get_event_loop()
        while True:
            message = await loop.run_in_executor(None, pubsub.get_message, True, 1.0)
            if message and message["type"] == "message":
                await websocket.send_text(message["data"])

    try:
        await read_redis_messages()
    except WebSocketDisconnect:
        logger.info("Client disconnected from game %s", link)
    finally:
        try:
            pubsub.close()
        except Exception:
            pass
        if spectator_registered:
            try:
                if _unregister_spectator_connection(link, user.id):
                    _announce_spectator_system_log(
                        link, f"{user.username} stopped spectating"
                    )
            except Exception:
                logger.exception(
                    "Failed to unregister spectator %s for game %s", user.id, link
                )


@router.websocket("/api/ws/global")
async def global_ws(websocket: WebSocket):
    user = _resolve_authenticated_user(websocket.cookies.get("session_user"))
    if user is None:
        await websocket.close(code=4401, reason="Authentication required")
        return

    try:
        await websocket.accept()
        logger.info("Authenticated global WebSocket opened for user %s", user.id)
    except Exception:
        logger.exception("Global WebSocket accept failed")
        return

    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info("Global WebSocket disconnected for user %s", user.id)
