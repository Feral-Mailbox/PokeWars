import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

app = FastAPI()

origins = [os.getenv("CORS_ORIGIN", "http://localhost:5173")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routes import auth, games, maps, user, ws

app.include_router(auth.router)
app.include_router(games.router)
app.include_router(maps.router)
app.include_router(user.router)
app.include_router(ws.router)