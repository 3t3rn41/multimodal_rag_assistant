"""The shared Jina contract for API and worker; credentials stay in .env."""

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import replace

from backend.core.errors import ServiceError
from backend.core.security.model_endpoints import validate_endpoint
from ingestion.api_embeddings import MultimodalEmbeddingAPIConfig
from rag_engine.rerank import JinaRerankConfig

EMBEDDING_MODEL = "jina-embeddings-v5-omni-small"
EMBEDDING_URL = "https://api.jina.ai/v1/embeddings"
EMBEDDING_DIMENSIONS = 1024
RERANK_MODEL = "jina-reranker-v3"
RERANK_URL = "https://api.jina.ai/v1/rerank"
VECTOR_COLLECTION = "jina_v5_omni_small_1024"
VECTOR_NAME = "dense"


class JinaConfigurationError(ServiceError):
    """Safe explanation; never include a supplied credential or URL."""

    def __init__(self, message: str):
        super().__init__(message, 503)


PLACEHOLDERS = {
    "fill_me",
    "replace_me",
    "changeme",
    "change-me",
    "your_api_key",
    "your-api-key",
    "your_model",
    "your-model",
}


def is_configured(value: str | None) -> bool:
    cleaned = (value or "").strip().strip("\"'")
    return bool(
        cleaned and cleaned.lower() not in PLACEHOLDERS and not cleaned.startswith("${")
    )


def _key(values, name):
    specific = values.get(name, "")
    return specific if is_configured(specific) else values.get("JINA_API_KEY", "")


def jina_profile(env: Mapping[str, str] | None = None) -> dict:
    """Non-secret indexing identity, identical for all users."""
    values = os.environ if env is None else env
    expected = {
        "RAG_EMBEDDING_MODEL": EMBEDDING_MODEL,
        "RAG_EMBEDDING_DIMENSIONS": str(EMBEDDING_DIMENSIONS),
        "RAG_EMBEDDING_PASSAGE_TASK": "retrieval.passage",
        "RAG_EMBEDDING_QUERY_TASK": "retrieval.query",
        "RAG_RERANK_MODEL": RERANK_MODEL,
        "RAG_QDRANT_COLLECTION": VECTOR_COLLECTION,
        "RAG_QDRANT_VECTOR_NAME": VECTOR_NAME,
    }
    if any(
        str(values.get(name, default) or default).strip() != default
        for name, default in expected.items()
    ):
        raise JinaConfigurationError(
            "系统模型配置不符合团队规范。请在 .env 使用约定的 Jina 模型、"
            "1024 维、dense 向量和 jina_v5_omni_small_1024 集合。"
        )
    if values.get("RAG_RERANK_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        raise JinaConfigurationError(
            "请在 .env 设置 RAG_RERANK_ENABLED=true；网页问答必须启用 Jina 精排。"
        )
    urls = {}
    for name, default in (
        ("RAG_EMBEDDING_API_URL", EMBEDDING_URL),
        ("RAG_RERANK_API_URL", RERANK_URL),
    ):
        url = (values.get(name) or default).strip().rstrip("/")
        try:
            urls[name] = validate_endpoint(url, env=values)
        except ServiceError as exc:
            raise JinaConfigurationError(f"{name} 配置无效：{exc}") from None
    identity = {
        "embedding_url": urls["RAG_EMBEDDING_API_URL"],
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
    }
    space = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[
        :20
    ]
    return {
        **identity,
        "embedding_space": space,
        "vector_collection": VECTOR_COLLECTION,
        "vector_name": VECTOR_NAME,
        "rerank_model": RERANK_MODEL,
        "rerank_url": urls["RAG_RERANK_API_URL"],
        "configuration_source": "environment",
    }


def embedding_configuration(
    env: Mapping[str, str] | None = None,
) -> MultimodalEmbeddingAPIConfig:
    values = dict(os.environ if env is None else env)
    profile = jina_profile(values)
    key = _key(values, "RAG_EMBEDDING_API_KEY")
    if not is_configured(key):
        raise JinaConfigurationError(
            "系统 Jina Embedding 未配置。请在项目 .env 填写 JINA_API_KEY 并重启后端和 Worker。"
        )
    values.update(
        RAG_EMBEDDING_API_KEY=key,
        RAG_EMBEDDING_API_URL=profile["embedding_url"],
        RAG_EMBEDDING_MODEL=EMBEDDING_MODEL,
        RAG_EMBEDDING_DIMENSIONS="1024",
    )
    try:
        return MultimodalEmbeddingAPIConfig.from_env(values)
    except (ValueError, TypeError):
        raise JinaConfigurationError(
            "Jina 向量配置无效，请检查 .env 中的超时及重试参数。"
        ) from None


def rerank_configuration(env: Mapping[str, str] | None = None) -> JinaRerankConfig:
    values = dict(os.environ if env is None else env)
    profile = jina_profile(values)
    key = _key(values, "RAG_RERANK_API_KEY")
    if not is_configured(key):
        raise JinaConfigurationError(
            "系统 Jina Rerank 未配置。请在项目 .env 填写 JINA_API_KEY 并重启后端和 Worker。"
        )
    values.update(
        RAG_RERANK_API_KEY=key,
        RAG_RERANK_API_URL=profile["rerank_url"],
        RAG_RERANK_MODEL=RERANK_MODEL,
    )
    try:
        return JinaRerankConfig.from_env(values)
    except (ValueError, TypeError):
        raise JinaConfigurationError(
            "Jina 精排配置无效，请检查 .env 中的超时及重试参数。"
        ) from None


def embedding_snapshot(user_id: int) -> dict:
    return {"user_id": user_id, **jina_profile()}


def embedding_from_snapshot(snapshot: dict) -> MultimodalEmbeddingAPIConfig:
    profile = jina_profile()
    names = (
        "embedding_space",
        "vector_collection",
        "embedding_url",
        "embedding_model",
        "embedding_dimensions",
    )
    if snapshot.get("configuration_source") != "environment" or any(
        snapshot.get(name) != profile[name] for name in names
    ):
        raise JinaConfigurationError(
            "该任务使用旧模型配置。请在知识库重新处理文件，使用系统统一的 Jina 向量模型。"
        )
    # Celery owns indexing retries. Interactive queries retain HTTP backoff.
    return replace(embedding_configuration(), max_retries=0)


def configuration_status(env: Mapping[str, str] | None = None) -> dict:
    values = os.environ if env is None else env
    embedding = is_configured(_key(values, "RAG_EMBEDDING_API_KEY"))
    rerank = is_configured(_key(values, "RAG_RERANK_API_KEY"))
    missing = []
    if not embedding:
        missing.append("JINA_API_KEY（Embedding）")
    if not rerank:
        missing.append("JINA_API_KEY（Rerank）")
    try:
        jina_profile(values)
        if embedding:
            embedding_configuration(values)
        if rerank:
            rerank_configuration(values)
    except JinaConfigurationError as exc:
        missing.append(str(exc))
    return {
        "configured": not missing,
        "configuration_source": "environment",
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "embedding_configured": embedding,
        "rerank_model": RERANK_MODEL,
        "rerank_configured": rerank,
        "vector_collection": VECTOR_COLLECTION,
        "missing": missing,
        "remote_services_verified": False,
    }
