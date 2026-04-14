"""Minimal Life Shield API - Auth only (no DB models)"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import secrets
import json

app = FastAPI(title="The Life Shield API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://the-life-shield.vercel.app", "https://thelifeshield.net", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store (for demo)
USERS = {}
TOKENS = {}

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    terms_accepted: bool
    service_disclosure_accepted: bool
    croa_disclosure_accepted: bool

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

@app.get("/health")
def health():
    return {"status": "healthy", "service": "The Life Shield", "version": "1.0.0"}

@app.get("/api/docs", include_in_schema=False)
def docs():
    return {"message": "API is running"}

@app.post("/api/v1/auth/register")
def register(req: RegisterRequest):
    if req.email in USERS:
        return {"error": "User exists", "code": "USER_EXISTS"}, 400
    
    user_id = secrets.token_urlsafe(16)
    USERS[req.email] = {
        "id": user_id,
        "email": req.email,
        "first_name": req.first_name,
        "last_name": req.last_name,
        "password": req.password,  # TODO: hash this
    }
    
    access_token = secrets.token_urlsafe(32)
    TOKENS[access_token] = {
        "user_id": user_id,
        "email": req.email,
    }
    
    return {
        "success": True,
        "user": {
            "id": user_id,
            "email": req.email,
            "first_name": req.first_name,
            "last_name": req.last_name,
        },
        "access_token": access_token,
        "token_type": "bearer",
    }

@app.post("/api/v1/auth/login")
def login(req: LoginRequest):
    if req.email not in USERS:
        return {"error": "User not found", "code": "USER_NOT_FOUND"}, 404
    
    user = USERS[req.email]
    if user["password"] != req.password:  # TODO: use bcrypt
        return {"error": "Invalid password", "code": "INVALID_PASSWORD"}, 401
    
    access_token = secrets.token_urlsafe(32)
    TOKENS[access_token] = {
        "user_id": user["id"],
        "email": req.email,
    }
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
        },
    }

@app.get("/api/v1/auth/me")
def me(authorization: str = None):
    if not authorization or not authorization.startswith("Bearer "):
        return {"error": "Unauthorized"}, 401
    
    token = authorization.replace("Bearer ", "")
    if token not in TOKENS:
        return {"error": "Invalid token"}, 401
    
    token_data = TOKENS[token]
    user = USERS.get(token_data["email"])
    
    return {
        "id": user["id"],
        "email": user["email"],
        "first_name": user["first_name"],
        "last_name": user["last_name"],
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
