from fastapi import FastAPI
from app.routes import auth, user

app = FastAPI()
app.include_router(auth.router)
app.include_router(user.router)