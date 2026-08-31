import asyncio
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()
TOKEN = "acceptance-secret-token"

class Login(BaseModel):
    username: str
    password: str

@app.post("/login")
async def login(data: Login):
    if data.username != "tester" or data.password != "test-password":
        raise HTTPException(401, "invalid credentials")
    return {"data": {"access_token": TOKEN}}

@app.get("/me")
async def me(authorization: str = Header(default="")):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "invalid token")
    return {"data": {"username": "tester", "email": "tester@example.test"}}

@app.get("/slow")
async def slow(authorization: str = Header(default="")):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "invalid token")
    await asyncio.sleep(12)
    return {"data": {"completed": True}}
