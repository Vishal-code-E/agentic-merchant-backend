"""
Per-API-key rate limiting for /agent/* endpoints, backed by Redis (already
provisioned via settings.redis_url — see requirements.txt's comment noting
it was otherwise unused until now).

Fixed-window counter (INCR + EXPIRE), not a sliding-window log: two Redis
round trips instead of a ZSET's several, at the cost of allowing up to ~2x
the limit across a window boundary (a burst just before the window ends and
another just after both count as fresh). Accepted tradeoff for v1, not an
oversight — a ZSET-based sliding log is the upgrade path if this ever
matters more than the extra Redis load it costs.

Fails OPEN, not closed: if Redis is unreachable/misconfigured, a warning is
logged and the request proceeds unlimited rather than a side-car cache
outage taking down every /agent/* endpoint. This is a deliberate
availability-over-strictness tradeoff — see docs/ARCHITECTURE.md's Security
Model section. Short connect/socket timeouts keep that failure cheap instead
of stalling every request behind a slow-timing-out connection attempt.
"""
import logging

from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config.settings import get_settings
from app.services.agent_auth import hash_api_key

logger = logging.getLogger(__name__)

#: (max requests, window seconds) per logical endpoint name.
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "agent_catalog": (60, 60),
    "agent_checkout": (20, 60),
    "agent_chat_checkout": (10, 60),
}

_redis: Redis | None = None


def _get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
    return _redis


async def enforce_rate_limit(endpoint: str, api_key: str) -> None:
    """Raise 429 if this api_key has exceeded RATE_LIMITS[endpoint]; fail open on any Redis error."""
    limit, window_seconds = RATE_LIMITS[endpoint]
    redis_key = f"ratelimit:{endpoint}:{hash_api_key(api_key)}"

    try:
        redis_client = _get_redis()
        count = await redis_client.incr(redis_key)
        if count == 1:
            await redis_client.expire(redis_key, window_seconds)
        over_limit = count > limit
        ttl = await redis_client.ttl(redis_key) if over_limit else None
    except RedisError as e:
        logger.warning("Redis unreachable for rate limiting (%s) — failing open on %s.", e, endpoint)
        return

    if over_limit:
        retry_after = max(ttl, 1)
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded: {limit} requests per {window_seconds}s for this API key "
                f"on {endpoint}. Retry after {retry_after}s."
            ),
            headers={"Retry-After": str(retry_after)},
        )
