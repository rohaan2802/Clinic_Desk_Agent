"""Admission, concurrency, and spend controls for public paid-model use."""
from collections import defaultdict, deque
from threading import Lock
from time import time

from fastapi import HTTPException, Request

from app.config import settings

_lock = Lock()
_hits: dict[str, deque] = defaultdict(deque)
_concurrent = 0
_spend_usd = 0.0


def client_key(request: Request) -> str:
    forwarded = request.headers.get('x-forwarded-for', '')
    if forwarded:
        return forwarded.split(',')[0].strip()[:80]
    return (request.client.host if request.client else 'unknown')[:80]


def admit(request: Request) -> None:
    global _concurrent
    key = client_key(request)
    now = time()
    with _lock:
        if _spend_usd >= settings.max_spend_usd > 0:
            raise HTTPException(429, 'Estimated model spend cap reached for this process')
        window = _hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= settings.rate_limit_per_minute:
            raise HTTPException(429, 'Rate limit exceeded. Try again in a minute.')
        if _concurrent >= settings.max_concurrent_runs:
            raise HTTPException(429, 'ClinicDesk is at its concurrency limit')
        window.append(now)
        _concurrent += 1


def release() -> None:
    global _concurrent
    with _lock:
        _concurrent = max(0, _concurrent - 1)


def add_spend(amount: float | None) -> None:
    global _spend_usd
    if amount is None:
        return
    with _lock:
        _spend_usd += max(0.0, amount)


def snapshot() -> dict:
    with _lock:
        return {
            'concurrent': _concurrent,
            'spend_usd': round(_spend_usd, 6),
            'max_spend_usd': settings.max_spend_usd,
        }


def reset_for_tests() -> None:
    """Clear rate / concurrency / spend counters between unit tests."""
    global _concurrent, _spend_usd
    with _lock:
        _hits.clear()
        _concurrent = 0
        _spend_usd = 0.0
