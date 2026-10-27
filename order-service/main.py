from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uuid

app = FastAPI(title="Order Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-memory DB (demo) ---
orders_db = {
    "ord1": {"id": "ord1", "user_id": "user1", "product": "Laptop", "quantity": 1, "price": 25000000, "status": "completed"},
    "ord2": {"id": "ord2", "user_id": "user1", "product": "Mouse", "quantity": 2, "price": 500000, "status": "pending"},
    "ord3": {"id": "ord3", "user_id": "user2", "product": "Keyboard", "quantity": 1, "price": 1200000, "status": "completed"},
}

# --- Models ---
class Order(BaseModel):
    user_id: str
    product: str
    quantity: int
    price: float

class OrderResponse(BaseModel):
    id: str
    user_id: str
    product: str
    quantity: int
    price: float
    status: str

# --- Endpoints ---
@app.get("/health")
def health():
    return {"status": "ok", "service": "order-service"}

@app.get("/orders", response_model=list[OrderResponse])
def list_orders():
    return list(orders_db.values())

@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str):
    order = orders_db.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.post("/orders", response_model=OrderResponse, status_code=201)
def create_order(order: Order):
    order_id = "ord" + str(uuid.uuid4())[:6]
    new_order = {
        "id": order_id,
        "user_id": order.user_id,
        "product": order.product,
        "quantity": order.quantity,
        "price": order.price,
        "status": "pending",
    }
    orders_db[order_id] = new_order
    return new_order

@app.get("/internal/orders/by-user/{user_id}")
def get_orders_by_user(user_id: str):
    """Internal endpoint for aggregation."""
    user_orders = [o for o in orders_db.values() if o["user_id"] == user_id]
    return user_orders
