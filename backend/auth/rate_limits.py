"""Shared, atomic Redis limits. Identifiers are HMACs, never raw emails or IPs."""

import hashlib
import hmac

from backend.core.config import settings
from backend.core.errors import ServiceError
from backend.infrastructure.redis import async_client

_INCREMENT = "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n"


async def check_limit(kind: str, identifier: str, maximum: int, seconds: int):
    digest = hmac.new(
        settings.env.secret_key.encode(), identifier.encode(), hashlib.sha256
    ).hexdigest()
    key = f"{settings.env.celery_queue_prefix}:auth:{kind}:{digest}"
    client = async_client(
        settings.redis_url, socket_timeout=3, socket_connect_timeout=3
    )
    try:
        count = await client.eval(_INCREMENT, 1, key, seconds)
    except Exception:  # noqa: BLE001 - fail closed on any limiter failure
        raise ServiceError("登录服务暂时不可用，请确认 Redis 已启动。", 503) from None
    finally:
        await client.aclose()
    if count > maximum:
        raise ServiceError("操作过于频繁，请稍后重试。", 429)
