from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import boto3
from botocore.client import Config
import os
import time
import uuid

app = FastAPI(title="User Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-memory DB (demo) ---
users_db = {
    "user1": {"id": "user1", "name": "Nguyen Van A", "email": "a@example.com", "avatar": None},
    "user2": {"id": "user2", "name": "Tran Thi B", "email": "b@example.com", "avatar": None},
}

# --- MinIO config ---
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "password123")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "avatars")

def get_minio_client():
    return boto3.client(
        "s3",
        endpoint_url=f"http://{MINIO_ENDPOINT}",
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )

# --- Models ---
class User(BaseModel):
    name: str
    email: str

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    avatar: Optional[str] = None

# --- Endpoints ---
@app.get("/health")
def health():
    return {"status": "ok", "service": "user-service"}

@app.get("/users", response_model=list[UserResponse])
def list_users():
    return list(users_db.values())

@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: str):
    user = users_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/users", response_model=UserResponse, status_code=201)
def create_user(user: User):
    user_id = str(uuid.uuid4())[:8]
    new_user = {"id": user_id, "name": user.name, "email": user.email, "avatar": None}
    users_db[user_id] = new_user
    return new_user

@app.get("/users/{user_id}/avatar-upload-url")
def get_avatar_upload_url(user_id: str):
    """
    Valet Key Pattern: Generate a pre-signed URL for direct upload to MinIO.
    URL expires in 5 minutes (300 seconds).
    """
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")

    client = get_minio_client()
    object_key = f"avatars/{user_id}/{uuid.uuid4()}.jpg"

    # Ensure bucket exists
    try:
        client.head_bucket(Bucket=MINIO_BUCKET)
    except Exception:
        client.create_bucket(Bucket=MINIO_BUCKET)

    # Generate pre-signed URL (5 minutes = 300 seconds)
    presigned_url = client.generate_presigned_url(
        "put_object",
        Params={"Bucket": MINIO_BUCKET, "Key": object_key, "ContentType": "image/jpeg"},
        ExpiresIn=300,
    )

    return {
        "user_id": user_id,
        "upload_url": presigned_url,
        "object_key": object_key,
        "expires_in_seconds": 300,
        "note": "Use HTTP PUT to upload your image directly to this URL. URL expires in 5 minutes.",
    }

@app.patch("/users/{user_id}/avatar")
def update_avatar(user_id: str, body: dict):
    """Update user avatar after upload."""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    users_db[user_id]["avatar"] = body.get("object_key")
    return {"message": "Avatar updated", "user": users_db[user_id]}

@app.get("/internal/users/{user_id}")
def get_user_internal(user_id: str):
    """Internal endpoint for aggregation (no auth required between services)."""
    user = users_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
