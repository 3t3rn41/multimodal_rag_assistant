"""应用及模型读取环境配置，算法参数由 ingestion / rag_engine 管理。

所有进程读取当前仓库 .env；文件中的设置优先于已有进程环境。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ENV_FILE, override=True, encoding="utf-8-sig")


class EnvSettings(BaseSettings):
    """从环境变量 / .env 读取的敏感与连接配置。字段名与 .env.example 对应。"""

    model_config = SettingsConfigDict(
        # All variables, including B/C settings, are loaded into the environment above.
        env_file=None,
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    # Member A: isolated local application defaults.
    app_title: str = "Multimodal RAG Assistant"
    app_stage: str = "pdf-rag"
    app_cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"
    app_env: Literal["development", "production"] = "development"
    app_backend_url: str = "http://127.0.0.1:8001"
    public_base_url: str = "http://127.0.0.1:5174"
    auth_cookie_secure: bool = False
    auth_session_days: int = 7
    auth_token_minutes: int = 30
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_security: Literal["starttls", "ssl"] = "starttls"
    model_allow_localhost: bool = False
    redis_db: int = 0
    minio_bucket: str = "raw-files"
    celery_broker_url: str = ""
    celery_result_backend: str = ""
    celery_queue_prefix: str = "mmrag"
    minio_public_endpoint: str = ""
    minio_secure: bool = False
    minio_public_secure: bool | None = None
    # MySQL
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3308
    mysql_user: str = "mmrag"
    mysql_password: str = ""
    mysql_database: str = "multimodal_rag_assistant"

    # Redis
    redis_host: str = "127.0.0.1"
    redis_port: int = 6378

    # Qdrant（向量库）
    qdrant_host: str = "127.0.0.1"
    qdrant_port: int = 6333

    # MinIO（对象存储）
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"

    # 会话令牌与安全功能使用的部署密钥；不能提交到仓库。
    secret_key: str = "change-me-in-production"

    @model_validator(mode="after")
    def validate_deployment(self):
        if not self.celery_broker_url:
            self.celery_broker_url = f"redis://{self.redis_host}:{self.redis_port}/1"
        if not self.celery_result_backend:
            self.celery_result_backend = f"redis://{self.redis_host}:{self.redis_port}/2"
        if not self.minio_public_endpoint:
            self.minio_public_endpoint = self.minio_endpoint
        public = urlsplit(self.public_base_url)
        if (
            public.scheme not in {"http", "https"}
            or not public.hostname
            or public.username
            or public.query
            or public.fragment
            or public.path not in {"", "/"}
        ):
            raise ValueError("PUBLIC_BASE_URL 必须是网站根地址。")
        if (
            not 1 <= self.auth_session_days <= 30
            or not 5 <= self.auth_token_minutes <= 60
        ):
            raise ValueError("会话或邮件令牌有效期超出范围。")
        if self.app_env == "production":
            if not self.auth_cookie_secure or public.scheme != "https":
                raise ValueError("生产环境必须使用 HTTPS 和安全 Cookie。")
            if (
                len(self.secret_key) < 32
                or self.secret_key == "change-me-in-production"
            ):
                raise ValueError("生产环境必须设置至少 32 字符的随机 SECRET_KEY。")
            if not all(
                (self.smtp_host, self.smtp_from, self.smtp_user, self.smtp_password)
            ):
                raise ValueError("生产环境必须填写真实 SMTP 发信配置。")
            if self.model_allow_localhost:
                raise ValueError("生产环境不能启用本地模型测试地址。")
            origins = [v.strip() for v in self.app_cors_origins.split(",") if v.strip()]
            if not origins or any(urlsplit(v).scheme != "https" for v in origins):
                raise ValueError("生产环境 APP_CORS_ORIGINS 必须是明确的 HTTPS 地址。")
        return self


class Settings:
    """连接配置门面：API / Celery / 迁移共享同一份环境设置。"""

    def __init__(self) -> None:
        self.env = EnvSettings()

    def build_database_url(self, driver: str = "pymysql") -> str:
        from sqlalchemy.engine import URL

        e = self.env
        return URL.create(
            f"mysql+{driver}",
            username=e.mysql_user,
            password=e.mysql_password,
            host=e.mysql_host,
            port=e.mysql_port,
            database=e.mysql_database,
        ).render_as_string(hide_password=False)

    @property
    def redis_url(self) -> str:
        return (
            f"redis://{self.env.redis_host}:{self.env.redis_port}/{self.env.redis_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
