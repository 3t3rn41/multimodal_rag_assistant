"""Redis connections and distributed leases; key ownership is supplied by callers."""


def distributed_lock(url, key, *, timeout):
    from redis import Redis

    return Redis.from_url(url, socket_connect_timeout=5, socket_timeout=5).lock(key, timeout=timeout, blocking=False)


def async_client(url, **options):
    from redis.asyncio import Redis

    return Redis.from_url(url, **options)
