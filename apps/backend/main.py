from fastapi import FastAPI
import os

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SESSION_SECRET")

app = FastAPI()
