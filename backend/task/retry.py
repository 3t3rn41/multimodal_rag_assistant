"""Transport retry classification shared by ingestion and resource cleanup."""

def transient_error(exc):
    import httpx
    from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError
    from urllib3.exceptions import HTTPError as UrllibHTTPError

    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, (ConnectionError, TimeoutError, httpx.TransportError,
                            UrllibHTTPError, RedisConnectionError, RedisTimeoutError)):
            return True
        status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
        if isinstance(status, int) and (status in {408, 425, 429} or status >= 500):
            return True
        if getattr(exc, "code", None) in {"SlowDown", "InternalError", "ServiceUnavailable", "RequestTimeout"}:
            return True
        exc = exc.__cause__ or exc.__context__
    return False
