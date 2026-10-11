"""Provider protocols at member A's boundary; member B's embedder stays unchanged."""

from __future__ import annotations

import math
from collections.abc import Mapping

import httpx

from ingestion.api_embeddings import (
    ApiMultimodalEmbedder,
    EmbeddingAPIError,
    HttpxJsonTransport,
    JsonTransport,
    MultimodalEmbeddingAPIConfig,
)
from ingestion.retry import RetryPolicy


class ModelProviderError(EmbeddingAPIError):
    """Safe explanation plus an HTTP status for Celery's existing retry policy."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def provider_http_error(exc: httpx.HTTPError) -> ModelProviderError:
    """Never include upstream bodies, request headers, URLs, or keys in errors."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        explanations = {
            400: "模型服务拒绝请求，请核对模型名称、接口格式和支持的向量维度。",
            401: "模型密钥验证失败，请确认密钥有效且属于当前服务地址。",
            402: "模型账户余额不足，请在模型平台检查余额。",
            403: "模型服务拒绝访问，请检查模型权限、账户状态和余额。",
            404: "模型或接口不存在，请核对服务地址和模型名称。",
            422: "模型服务未接受请求参数，请核对接口格式与模型配置。",
            429: "模型服务限流或额度不足，请检查平台额度，稍后重试。",
        }
        if 300 <= status < 400:
            explanation = (
                "模型地址发生重定向，为避免密钥转发已停止连接，请填写最终接口地址。"
            )
        elif status >= 500:
            explanation = "模型服务暂时出错，请稍后重试。"
        else:
            explanation = explanations.get(status, "模型服务未接受请求，请核对配置。")
        return ModelProviderError(
            f"连接失败（HTTP {status}）：{explanation}", status_code=status
        )
    if isinstance(exc, httpx.TimeoutException):
        return ModelProviderError("模型服务请求超时，请检查网络或稍后重试。")
    return ModelProviderError("无法连接模型服务，请检查网络、HTTPS 证书和服务地址。")


def _vectors(response: Mapping, expected: int, dimensions: int | None) -> list[dict]:
    data = response.get("data")
    if not isinstance(data, list) or len(data) != expected:
        raise ModelProviderError("向量服务返回的切片数量不匹配，请核对接口格式。")
    rows = {}
    for fallback, item in enumerate(data):
        if not isinstance(item, Mapping):
            raise ModelProviderError("向量服务返回格式无效，请核对接口地址。")
        index, vector = item.get("index", fallback), item.get("embedding")
        if (
            type(index) is not int
            or not 0 <= index < expected
            or index in rows
            or not isinstance(vector, list)
            or not vector
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in vector
            )
        ):
            raise ModelProviderError("向量服务返回的数据无效，请核对接口格式。")
        if dimensions is not None and len(vector) != dimensions:
            raise ModelProviderError(
                f"向量服务返回 {len(vector)} 维，与设置的 {dimensions} 维不一致。"
                "请检查系统 .env 配置并重新处理文档。"
            )
        rows[index] = {"index": index, "embedding": vector}
    if len({len(row["embedding"]) for row in rows.values()}) != 1:
        raise ModelProviderError("向量服务返回的维度不一致，请核对模型配置。")
    return [rows[index] for index in range(expected)]


class EmbeddingProtocolTransport:
    """Validate Jina responses and redact transport errors at A's boundary."""

    def __init__(
        self,
        config: MultimodalEmbeddingAPIConfig,
        transport: JsonTransport | None = None,
    ):
        self.config = config
        self.transport = transport or HttpxJsonTransport(
            policy=RetryPolicy(config.max_retries, config.retry_backoff_seconds)
        )

    def _post(self, url, *, headers, payload, timeout):
        try:
            response = self.transport.post_json(
                url, headers=headers, payload=payload, timeout=timeout
            )
        except (httpx.HTTPError, EmbeddingAPIError) as exc:
            cause, seen = exc, set()
            while cause is not None and id(cause) not in seen:
                seen.add(id(cause))
                if isinstance(cause, httpx.HTTPError):
                    raise provider_http_error(cause) from cause
                cause = cause.__cause__ or cause.__context__
            raise ModelProviderError(
                "向量服务连接失败或返回格式无效，请检查配置。"
            ) from None
        if not isinstance(response, Mapping):
            raise ModelProviderError("向量服务返回格式无效，请检查接口地址。")
        return response

    def post_json(self, url, *, headers, payload, timeout):
        inputs = payload.get("input")
        if not isinstance(inputs, list) or not inputs:
            raise ModelProviderError("向量输入不能为空。")
        response = self._post(url, headers=headers, payload=payload, timeout=timeout)
        return {"data": _vectors(response, len(inputs), self.config.dimensions)}


def build_embedder(
    config: MultimodalEmbeddingAPIConfig,
    *,
    transport: JsonTransport | None = None,
) -> ApiMultimodalEmbedder:
    return ApiMultimodalEmbedder(
        config, transport=EmbeddingProtocolTransport(config, transport)
    )
