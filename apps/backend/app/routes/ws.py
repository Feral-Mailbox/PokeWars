import asyncio
import logging

import redis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db.database import get_sessionmaker
from app.db.models import Game, GamePlayer, User
from app.dependencies import ban_is_active
from app.utils.session import decode_session_token

router = APIRouter()
logger = logging.getLogger("ws")

r = redis.Redis(host="redis", port=6379, decode_responses=True)


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


@router.websocket("/api/ws/game/{link}")
async def websocket_endpoint(websocket: WebSocket, link: str):
    user = _resolve_authenticated_user(websocket.cookies.get("session_user"))
    if user is None or not _user_is_game_participant(user.id, link):
        await websocket.close(code=4401, reason="Authentication required")
        return

    await websocket.accept()
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
        pubsub.close()


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
