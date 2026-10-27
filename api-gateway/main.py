import time
import asyncio
from collections import defaultdict
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from pydantic import BaseModel

app = FastAPI(title="API Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Service URLs ---
USER_SERVICE_URL = "http://user-service:8001"
ORDER_SERVICE_URL = "http://order-service:8002"

# --- JWT Config ---
SECRET_KEY = "your-super-secret-key-change-in-production"
ALGORITHM = "HS256"

# --- Rate Limiter (10 req/s per IP) ---
rate_limit_data: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 10  # requests per second

def check_rate_limit(client_ip: str) -> bool:
    now = time.time()
    window = 1.0  # 1 second window
    # Remove requests older than 1 second
    rate_limit_data[client_ip] = [t for t in rate_limit_data[client_ip] if now - t < window]
    if len(rate_limit_data[client_ip]) >= RATE_LIMIT:
        return False
    rate_limit_data[client_ip].append(now)
    return True

# --- JWT Verification ---
def verify_jwt(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

def get_token_from_header(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    return auth.split(" ")[1]

# --- Middleware: Rate Limiting ---
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Skip health check from rate limiting
    if request.url.path == "/health":
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={
                "error": "Too Many Requests",
                "detail": f"Rate limit exceeded: max {RATE_LIMIT} requests/second",
                "retry_after": "1 second",
            },
        )
    return await call_next(request)

# --- Helper ---
async def proxy_request(client: httpx.AsyncClient, method: str, url: str, request: Request, **kwargs):
    """Forward request to upstream service."""
    headers = dict(request.headers)
    headers.pop("host", None)
    try:
        body = await request.body()
        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            content=body,
            **kwargs,
        )
        return JSONResponse(content=response.json(), status_code=response.status_code)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"Service unavailable: {url}")

# ===========================
# GATEWAY ENDPOINTS
# ===========================

@app.get("/health")
def health():
    return {"status": "ok", "service": "api-gateway"}

# --- AUTH: Issue JWT (for demo/testing) ---
class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/auth/login")
def login(body: LoginRequest):
    """Demo login - issues JWT token for testing."""
    # Demo: accept any credentials
    if body.password != "secret":
        raise HTTPException(status_code=401, detail="Invalid credentials. Use password='secret'")

    import datetime
    payload = {
        "sub": body.username,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}

# ===========================
# ROUTING: /users → user-service
# ===========================

@app.api_route("/users", methods=["GET", "POST"])
async def route_users(request: Request):
    """Route /users to user-service (JWT protected)."""
    token = get_token_from_header(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization header. Get token at POST /auth/login")
    verify_jwt(token)

    async with httpx.AsyncClient() as client:
        return await proxy_request(client, request.method, f"{USER_SERVICE_URL}/users", request)

@app.api_route("/users/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def route_users_path(path: str, request: Request):
    """Route /users/* to user-service (JWT protected)."""
    token = get_token_from_header(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    verify_jwt(token)

    async with httpx.AsyncClient() as client:
        return await proxy_request(client, request.method, f"{USER_SERVICE_URL}/users/{path}", request)

# ===========================
# ROUTING: /orders → order-service
# ===========================

@app.api_route("/orders", methods=["GET", "POST"])
async def route_orders(request: Request):
    """Route /orders to order-service (JWT protected)."""
    token = get_token_from_header(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    verify_jwt(token)

    async with httpx.AsyncClient() as client:
        return await proxy_request(client, request.method, f"{ORDER_SERVICE_URL}/orders", request)

@app.api_route("/orders/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def route_orders_path(path: str, request: Request):
    """Route /orders/* to order-service (JWT protected)."""
    token = get_token_from_header(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    verify_jwt(token)

    async with httpx.AsyncClient() as client:
        return await proxy_request(client, request.method, f"{ORDER_SERVICE_URL}/orders/{path}", request)

# ===========================
# AGGREGATION: /dashboard
# ===========================

@app.get("/dashboard/{user_id}")
async def dashboard(user_id: str, request: Request):
    """
    Aggregation Pattern: Fetch user info + orders in parallel,
    combine into single response.
    """
    token = get_token_from_header(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    verify_jwt(token)

    start_time = time.time()

    async with httpx.AsyncClient(timeout=5.0) as client:
        # Fetch user and orders in PARALLEL
        user_task = client.get(f"{USER_SERVICE_URL}/internal/users/{user_id}")
        orders_task = client.get(f"{ORDER_SERVICE_URL}/internal/orders/by-user/{user_id}")

        try:
            user_resp, orders_resp = await asyncio.gather(user_task, orders_task)
        except httpx.ConnectError as e:
            raise HTTPException(status_code=503, detail=f"A downstream service is unavailable: {e}")

    if user_resp.status_code == 404:
        raise HTTPException(status_code=404, detail="User not found")

    user_data = user_resp.json()
    orders_data = orders_resp.json()

    total_spent = sum(o["price"] * o["quantity"] for o in orders_data)
    elapsed_ms = round((time.time() - start_time) * 1000, 2)

    return {
        "user": user_data,
        "orders": orders_data,
        "summary": {
            "total_orders": len(orders_data),
            "total_spent": total_spent,
        },
        "_meta": {
            "aggregated_from": ["user-service", "order-service"],
            "fetch_time_ms": elapsed_ms,
        },
    }
