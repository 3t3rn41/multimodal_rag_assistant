"""统一错误格式与全局异常处理器。

设计：
- 所有错误都收敛成同一种 JSON 结构 `{"error": {status, message, details?}}`，
  前端只需按一种约定解析，不用分别处理 FastAPI 默认的多种错误体。
- 未知异常（500）对外只回"服务器内部错误"，真实堆栈写进日志，避免泄露内部细节。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.core.errors import ServiceError
from backend.core.schemas import ErrorEnvelope

logger = logging.getLogger("multimodal_rag.api")


def _error_body(status_code: int, message: str, details=None) -> dict:
    body = {"error": {"status": status_code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return body


def register_exception_handlers(app: FastAPI) -> None:
    """把统一错误处理挂到 app 上。"""

    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError):
        return JSONResponse(
            status_code=exc.status_code, content=_error_body(exc.status_code, str(exc))
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.status_code, str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        # 用字面量 422：starlette 新版弃用了 HTTP_422_UNPROCESSABLE_ENTITY 常量名
        return JSONResponse(
            status_code=422,
            content=_error_body(
                422,
                "请求参数校验失败",
                [
                    {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                    for e in exc.errors()
                ],
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("未处理异常: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(
                status.HTTP_500_INTERNAL_SERVER_ERROR, "服务器内部错误"
            ),
        )


def register_error_openapi(app: FastAPI, *, sse_models=()) -> None:
    """Describe the JSON handlers and the existing SSE data without changing I/O."""
    original = app.openapi

    def openapi():
        schema = original()
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for model in (ErrorEnvelope, *sse_models):
            model_schema = model.model_json_schema(
                ref_template="#/components/schemas/{model}"
            )
            components.update(model_schema.pop("$defs", {}))
            components[model.__name__] = model_schema
        error_content = {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ErrorEnvelope"}
            }
        }
        for path in schema["paths"].values():
            for method, operation in path.items():
                if method not in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "head",
                    "options",
                }:
                    continue
                responses = operation.setdefault("responses", {})
                for code, response in responses.items():
                    if code.isdigit() and int(code) >= 400:
                        response["content"] = error_content
                responses["default"] = {
                    "description": "HTTP 错误统一返回 JSON；SSE 开始后的故障通过 error 事件返回。",
                    "content": error_content,
                }
        schema["paths"]["/api/chat"]["post"]["x-sse-events"] = {
            model.model_fields["event"].annotation.__args__[0]: {
                "$ref": f"#/components/schemas/{model.__name__}"
            }
            for model in sse_models
        }
        return schema

    app.openapi = openapi
