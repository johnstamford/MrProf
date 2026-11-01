"""F13-min: tiny in-memory per-IP sliding-window rate limit for writes.

Interim protection for the 2-day opening, not a production WAF: a single
process keeps per-(IP, minute) POST counts. Generous default (2000/min)
so local dev and the test suite never trip it; the opening deployment
sets a low cap (e.g. 60) via RATE_LIMIT_PER_MIN. Reads are unlimited.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

_hits: dict[tuple[str, str], list[float]] = defaultdict(list)


def reset_rate_limits() -> None:
    _hits.clear()


def limit_per_min() -> int:
    try:
        return max(1, int(os.environ.get("RATE_LIMIT_PER_MIN", "2000")))
    except ValueError:
        return 2000


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "POST":
            limit = limit_per_min()
            bucket = str(int(time.time() // 60))
            ip = (request.client.host if request.client else "unknown")
            key = (ip, bucket)
            now = time.monotonic()
            window = [t for t in _hits[key] if now - t < 60]
            if len(window) >= limit:
                return JSONResponse({"error": "rate_limited", "message": "too many requests — wait a minute and retry"}, status_code=429)
            window.append(now)
            _hits[key] = window
        return await call_next(request)
