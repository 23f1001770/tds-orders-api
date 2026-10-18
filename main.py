import os
import time
import uuid
import threading
from collections import defaultdict, deque

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 53
RATE_LIMIT = 16
WINDOW = 10.0

lock = threading.Lock()
idempotency = {}
rate_buckets = defaultdict(deque)


@app.post("/orders", status_code=201)
def create_order(idempotency_key: str = Header(..., alias="Idempotency-Key")):
    with lock:
        if idempotency_key not in idempotency:
            idempotency[idempotency_key] = {
                "id": str(uuid.uuid4()),
                "status": "created",
            }
        return idempotency[idempotency_key]


@app.get("/orders")
def list_orders(
    limit: int = Query(10, ge=1, le=100),
    cursor: str | None = None,
):
    start = int(cursor) if cursor else 1
    start = max(1, start)
    end = min(start + limit - 1, TOTAL_ORDERS)

    items = [{"id": i, "status": "created"} for i in range(start, end + 1)]
    next_cursor = str(end + 1) if end < TOTAL_ORDERS else None

    return {"items": items, "next_cursor": next_cursor}


@app.middleware("http")
async def client_rate_limit(request, call_next):
    if request.url.path in ("/orders",) and request.method == "GET":
        client_id = request.headers.get("X-Client-Id", "anonymous")
        now = time.monotonic()

        with lock:
            bucket = rate_buckets[client_id]
            while bucket and now - bucket[0] >= WINDOW:
                bucket.popleft()

            if len(bucket) >= RATE_LIMIT:
                retry_after = max(1, int(WINDOW - (now - bucket[0]) + 0.999))
                return __import__("starlette.responses").responses.JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers={"Retry-After": str(retry_after)},
                )

            bucket.append(now)

    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}
