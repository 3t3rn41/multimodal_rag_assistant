"""请求日志中间件：记录每个请求的方法、路径、状态码与耗时。

用 `@app.middleware("http")` 实现：在请求进入路由前记开始时间，
响应返回后算耗时并打日志；健康检查路径噪音大，单独降级为 debug。
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request

logger = logging.getLogger("multimodal_rag.api")

_NOISY_PATHS = {"/health", "/ready"}


def register_logging_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        line = f"{request.method} {request.url.path} -> {response.status_code} ({elapsed_ms:.1f}ms)"
        if request.url.path in _NOISY_PATHS:
            logger.debug(line)
        else:
            logger.info(line)
        return response
