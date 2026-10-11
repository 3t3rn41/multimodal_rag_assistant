"""Shared model endpoint policy for Member A's application adapters."""

import ipaddress
import socket
from collections.abc import Mapping
from urllib.parse import urlsplit

from backend.core.config import settings
from backend.core.errors import ServiceError


def validate_endpoint(url: str, *, resolve=False, env: Mapping[str, str] | None = None):
    try:
        parts = urlsplit(url)
        host, port = parts.hostname, parts.port
    except ValueError:
        raise ServiceError("模型地址格式不正确。") from None
    if (
        not host
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or "\\" in url
        or any(ord(c) < 33 for c in url)
    ):
        raise ServiceError("模型地址不能包含账号、密码、查询参数或片段。")
    allow_local = (
        settings.env.model_allow_localhost
        if env is None
        else (env.get("MODEL_ALLOW_LOCALHOST", "false").lower() in {"1", "true", "yes"})
    )
    app_env = settings.env.app_env if env is None else env.get("APP_ENV", "development")
    local = (
        allow_local
        and app_env != "production"
        and host in {"localhost", "127.0.0.1", "::1"}
    )
    if local:
        if parts.scheme not in {"http", "https"}:
            raise ServiceError("测试地址必须使用 HTTP 或 HTTPS。")
        return url.rstrip("/")
    if parts.scheme != "https" or port not in {None, 443}:
        raise ServiceError("模型服务地址必须使用 HTTPS 和默认 443 端口。")
    if host.lower().rstrip(".") == "localhost" or host.lower().rstrip(".").endswith(
        ".localhost"
    ):
        raise ServiceError("模型服务必须使用公网地址，不支持本机或内网地址。")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (not address.is_global or address.is_multicast):
        raise ServiceError("模型服务必须使用公网地址，不支持本机或内网地址。")
    if resolve:
        try:
            addresses = socket.getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
            if not addresses or any(
                not ipaddress.ip_address(row[4][0]).is_global
                or ipaddress.ip_address(row[4][0]).is_multicast
                for row in addresses
            ):
                raise ServiceError("模型服务解析到了非公网地址，已拒绝连接。")
        except OSError:
            raise ServiceError("模型服务域名暂时无法解析，请稍后重试。", 503) from None
    return url.rstrip("/")
