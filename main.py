@app.middleware("http")
async def client_rate_limit(request: Request, call_next):
    client_id = request.headers.get("X-Client-Id")

    if request.url.path == "/orders" and request.method in ("GET", "POST") and client_id:
        now = time.monotonic()

        with lock:
            bucket = rate_buckets[client_id]

            while bucket and now - bucket[0] >= WINDOW:
                bucket.popleft()

            if len(bucket) >= RATE_LIMIT:
                retry_after = max(
                    1, int(WINDOW - (now - bucket[0]) + 0.999)
                )
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers={
                        "Retry-After": str(retry_after),
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "*",
                        "Access-Control-Allow-Headers": "*",
                    },
                )

            bucket.append(now)

    response = await call_next(request)
    if response.status_code == 429 and "Retry-After" not in response.headers:
        response.headers["Retry-After"] = "10"
    return response 
