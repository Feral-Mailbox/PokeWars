from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import redis
import threading

router = APIRouter()

r = redis.Redis(host="redis", port=6379, decode_responses=True)

@router.websocket("/api/ws/game/{link}")
async def websocket_endpoint(websocket: WebSocket, link: str):
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
        print(f"[WS] Client disconnected from game {link}")
        pubsub.close()

@router.websocket("/api/ws/global")
async def global_ws(websocket: WebSocket):
    try:
        await websocket.accept()
        print("[+] WebSocket opened")
    except Exception as e:
        print("WebSocket error:", str(e))
        return

    try:
        while True:
            await asyncio.sleep(1)  # Passive loop, keep alive
    except WebSocketDisconnect:
        print("[-] WebSocket disconnected")

