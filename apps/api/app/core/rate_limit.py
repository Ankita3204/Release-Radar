"""Fixed-window rate limiting on Redis."""
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request
from redis.asyncio import Redis


async def allow(redis: Redis, key: str, limit: int, window_seconds: int) -> bool:
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    return count <= limit


def client_ip(request: Request) -> str:
    # request.client reflects X-Forwarded-For ONLY when uvicorn runs with
    # --proxy-headers and --forwarded-allow-ips set to the real proxy addresses.
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, limit: int, window_seconds: int) -> Callable[[Request], Awaitable[None]]:
    async def dependency(request: Request) -> None:
        redis: Redis = request.app.state.redis
        if not await allow(redis, f"rl:{name}:{client_ip(request)}", limit, window_seconds):
            raise HTTPException(status_code=429, detail="rate_limited", headers={"Retry-After": str(window_seconds)})

    return dependency
