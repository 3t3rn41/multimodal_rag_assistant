"""Qdrant connections and deletion of explicit owned point IDs."""

import os

from backend.core.config import settings


def get_client(*, timeout=30):
    from qdrant_client import QdrantClient

    local_path = os.getenv("RAG_QDRANT_PATH", "").strip()
    if local_path:
        return QdrantClient(path=local_path)
    return QdrantClient(
        url=os.getenv("RAG_QDRANT_URL", "").strip()
        or f"http://{settings.env.qdrant_host}:{settings.env.qdrant_port}",
        api_key=os.getenv("RAG_QDRANT_API_KEY", "").strip() or None,
        timeout=timeout,
    )


def delete_points(ids: list[str], collection: str | None = None) -> None:
    """Delete only point IDs derived from this document's canonical rows."""
    if not ids:
        return
    from qdrant_client.models import PointIdsList

    client = get_client(timeout=5)
    try:
        target = collection or os.getenv("RAG_QDRANT_COLLECTION", "jina_v5_omni_small_1024")
        if not client.collection_exists(target):
            return
        client.delete(
            target,
            points_selector=PointIdsList(points=ids),
            wait=True,
        )
    finally:
        client.close()
