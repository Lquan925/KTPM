# KTPM - Microservices Assignment

## Architecture

```
[Client]
   │
   ▼
[API Gateway :8000]  ← JWT verify + Rate limit (10 req/s)
   │         │
   ▼         ▼
[User    [Order      [MinIO :9000]
Service   Service     (Object Storage)
 :8001]    :8002]
```

## Features

| Pattern | Implementation |
|---|---|
| **Routing** | `/users` → user-service, `/orders` → order-service |
| **Offloading** | JWT verification + Rate limiting 10 req/s at gateway |
| **Aggregation** | `GET /dashboard/{user_id}` combines user + orders |
| **Valet Key** | `GET /users/{id}/avatar-upload-url` → pre-signed URL (5 min) |
| **Latency** | `python latency_test.py` measures gateway vs direct |

## Quick Start

### Prerequisites
- Docker Desktop running

### Run all services
```bash
docker-compose up --build -d
```

### Test the system

**1. Get JWT Token:**
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret"}'
```

**2. Get users (via gateway):**
```bash
curl http://localhost:8000/users \
  -H "Authorization: Bearer <your_token>"
```

**3. Get dashboard (aggregation):**
```bash
curl http://localhost:8000/dashboard/user1 \
  -H "Authorization: Bearer <your_token>"
```

**4. Get pre-signed upload URL (Valet Key):**
```bash
curl http://localhost:8000/users/user1/avatar-upload-url \
  -H "Authorization: Bearer <your_token>"
```

**5. Measure latency:**
```bash
pip install httpx
python latency_test.py
```

## Service URLs

| Service | URL | Docs |
|---|---|---|
| API Gateway | http://localhost:8000 | http://localhost:8000/docs |
| User Service (direct) | http://localhost:8001 | http://localhost:8001/docs |
| Order Service (direct) | http://localhost:8002 | http://localhost:8002/docs |
| MinIO Console | http://localhost:9001 | admin / password123 |
