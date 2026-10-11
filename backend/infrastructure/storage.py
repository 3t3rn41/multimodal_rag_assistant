"""MinIO 对象存储封装。

存上传的原始文件（PDF/Word/...）。bucket 名由 MINIO_BUCKET 指定。
file_key 规则：docs/{owner_id}/{doc_id}/{原始文件名}，按用户隔离便于后续配额/导出。"""

from __future__ import annotations

from datetime import timedelta
from io import BytesIO

from minio import Minio

from backend.core.config import settings

BUCKET = settings.env.minio_bucket


def get_minio_client(*, timeout: float | None = None) -> Minio:
    """构造 MinIO 客户端，地址和凭据来自当前项目 .env。"""
    options = {}
    if timeout is not None:
        from urllib3 import PoolManager, Timeout
        options["http_client"] = PoolManager(timeout=Timeout(connect=5, read=timeout), retries=False)
    return Minio(
        settings.env.minio_endpoint,
        access_key=settings.env.minio_access_key,
        secret_key=settings.env.minio_secret_key,
        secure=settings.env.minio_secure,
        **options,
    )


def ensure_bucket(client: Minio) -> None:
    """bucket 不存在则创建。幂等。"""
    if not client.bucket_exists(BUCKET):
        client.make_bucket(BUCKET)


def upload_bytes(
    client: Minio, file_key: str, content: bytes, content_type: str
) -> None:
    """上传字节流到 MinIO。"""
    client.put_object(
        BUCKET,
        file_key,
        BytesIO(content),
        length=len(content),
        content_type=content_type,
    )


def download_bytes(client: Minio, file_key: str, *, bucket: str | None = None) -> bytes:
    """下载文件全部内容。"""
    obj = client.get_object(bucket or BUCKET, file_key)
    try:
        return obj.read()
    finally:
        try:
            obj.close()
        finally:
            obj.release_conn()


def delete_object(client: Minio, file_key: str, *, bucket: str | None = None) -> None:
    """删除对象（文档删除时清理原始文件）。"""
    from minio.error import S3Error
    try:
        client.remove_object(bucket or BUCKET, file_key)
    except S3Error as exc:
        if exc.code not in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
            raise


def preview_url(storage_path):
    env = settings.env
    public = Minio(
        env.minio_public_endpoint,
        access_key=env.minio_access_key,
        secret_key=env.minio_secret_key,
        secure=env.minio_public_secure
        if env.minio_public_secure is not None
        else env.minio_secure,
        region="us-east-1",
    )
    return public.presigned_get_object(
        env.minio_bucket,
        storage_path,
        expires=timedelta(minutes=15),
        response_headers={"response-content-disposition": "inline"},
    )
