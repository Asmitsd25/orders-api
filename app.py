import base64
import time
import uuid
from collections import defaultdict, deque
from typing import Optional

from fastapi import FastAPI, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

# -----------------------------
# CORS
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

# -----------------------------
# Fixed catalog
# -----------------------------
TOTAL_ORDERS = 53

catalog = [
    {
        "id": i,
        "item": f"Product {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

# -----------------------------
# Idempotency
# -----------------------------
idempotency_store = {}

# -----------------------------
# Rate Limiting
# -----------------------------
WINDOW = 10
LIMIT = 16

client_requests = defaultdict(deque)


def check_rate_limit(client_id: str):
    now = time.time()

    dq = client_requests[client_id]

    while dq and dq[0] <= now - WINDOW:
        dq.popleft()

    if len(dq) >= LIMIT:
        retry_after = max(1, int(dq[0] + WINDOW - now))

        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={
                "Retry-After": str(retry_after)
            },
        )

    dq.append(now)
    return None


# -----------------------------
# Cursor helpers
# -----------------------------
def encode_cursor(index: int) -> str:
    return base64.urlsafe_b64encode(str(index).encode()).decode()


def decode_cursor(cursor: Optional[str]) -> int:
    if not cursor:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception:
        return 0


# -----------------------------
# POST /orders
# -----------------------------
@app.post("/orders", status_code=201)
def create_order(
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    client_id: str = Header("default", alias="X-Client-Id"),
):
    limited = check_rate_limit(client_id)
    if limited:
        return limited

    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid.uuid4()),
        "status": "created",
    }

    idempotency_store[idempotency_key] = order
    return order


# -----------------------------
# GET /orders
# -----------------------------
@app.get("/orders")
def list_orders(
    limit: int = 10,
    cursor: Optional[str] = None,
    client_id: str = Header("default", alias="X-Client-Id"),
):
    limited = check_rate_limit(client_id)
    if limited:
        return limited

    start = decode_cursor(cursor)

    items = catalog[start:start + limit]

    next_cursor = None
    if start + limit < len(catalog):
        next_cursor = encode_cursor(start + limit)

    return {
        "items": items,
        "next_cursor": next_cursor,
    }


@app.get("/")
def root():
    return {"status": "ok"}