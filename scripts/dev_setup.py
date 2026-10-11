"""Dependency inspection, private launcher configuration, and local initialization."""

from __future__ import annotations

import argparse
import hashlib
import importlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
MODULE_NAMES = {
    "python-dotenv": "dotenv",
    "pydantic-settings": "pydantic_settings",
    "pymysql": "pymysql",
    "qdrant-client": "qdrant_client",
    "email-validator": "email_validator",
    "python-multipart": "python_multipart",
    "pymupdf": "pymupdf",
}


class SetupError(ValueError):
    """An actionable message that contains no credentials or connection strings."""


def dependency_status() -> dict:
    import tomllib

    with (ROOT / "pyproject.toml").open("rb") as stream:
        requirements = tomllib.load(stream)["project"]["optional-dependencies"]["app"]
    try:
        from packaging.requirements import Requirement
    except ImportError:
        Requirement = None

    missing = []
    for specification in requirements:
        requirement = Requirement(specification) if Requirement else None
        if requirement:
            name = requirement.name
        else:
            name = re.match(r"[\w.-]+", specification)[0]
        try:
            version = metadata.version(name)
        except metadata.PackageNotFoundError:
            missing.append(specification)
            continue
        if requirement and not requirement.specifier.contains(version):
            missing.append(f"{specification} (installed: {version})")
            continue
        module = MODULE_NAMES.get(name.lower(), name.lower().replace("-", "_"))
        try:
            importlib.import_module(module)
        except Exception as exc:
            missing.append(f"{name} (import failed: {type(exc).__name__})")
    return {"python": sys.version.split()[0], "missing": missing}


def read_environment(path: Path) -> dict[str, str]:
    from dotenv import dotenv_values

    if not path.is_file():
        raise SetupError("Project .env is missing. Fill in .env.example and create .env first.")
    return {
        name: value
        for name, value in dotenv_values(path, encoding="utf-8-sig").items()
        if value is not None
    }


def local_url(value: str, name: str, *, scheme: str = "http"):
    try:
        parts = urlsplit(value)
        port = parts.port or (80 if scheme == "http" else 6379)
    except ValueError:
        raise SetupError(f"{name} has an invalid port.") from None
    if (
        parts.scheme != scheme
        or parts.hostname not in {"127.0.0.1", "localhost"}
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or (scheme == "http" and parts.path not in {"", "/"})
        or parts.port == 0
    ):
        raise SetupError(f"{name} must use a local {scheme} address for start-dev.ps1.")
    return parts, port


def build_configuration(env, values: dict[str, str]) -> dict:
    backend, backend_port = local_url(env.app_backend_url, "APP_BACKEND_URL")
    frontend, frontend_port = local_url(env.public_base_url, "PUBLIC_BASE_URL")
    if env.app_env != "development":
        raise SetupError("start-dev.ps1 is a local development launcher; APP_ENV must be development.")
    for name, host in (("MYSQL_HOST", env.mysql_host), ("REDIS_HOST", env.redis_host)):
        if host not in {"127.0.0.1", "localhost"}:
            raise SetupError(f"{name} must point to the local Docker services.")
    for name in ("MYSQL_ROOT_PASSWORD", "MYSQL_PASSWORD", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY"):
        if not values.get(name, "").strip():
            raise SetupError(f"Set {name} in the project .env before starting.")

    for name, value in (
        ("CELERY_BROKER_URL", env.celery_broker_url),
        ("CELERY_RESULT_BACKEND", env.celery_result_backend),
    ):
        _, port = local_url(value, name, scheme="redis")
        if port != env.redis_port:
            raise SetupError(f"{name} must use REDIS_PORT from .env.")

    qdrant_url = values.get("RAG_QDRANT_URL") or f"http://{env.qdrant_host}:{env.qdrant_port}"
    _, qdrant_port = local_url(qdrant_url, "RAG_QDRANT_URL")
    if values.get("QDRANT_PORT") and env.qdrant_port != qdrant_port:
        raise SetupError("QDRANT_PORT and RAG_QDRANT_URL specify different ports.")
    if values.get("RAG_QDRANT_PATH"):
        raise SetupError("Clear RAG_QDRANT_PATH to use the Qdrant container with API and Worker.")
    if env.minio_secure:
        raise SetupError("The local MinIO container uses HTTP; MINIO_SECURE must be false.")
    _, minio_port = local_url(f"http://{env.minio_endpoint}", "MINIO_ENDPOINT")
    try:
        console_port = int(values.get("MINIO_CONSOLE_PORT") or "9001")
    except ValueError:
        raise SetupError("MINIO_CONSOLE_PORT must be an integer.") from None

    infrastructure_ports = [env.mysql_port, env.redis_port, qdrant_port, minio_port, console_port]
    all_ports = [*infrastructure_ports, backend_port, frontend_port]
    if any(not 1 <= port <= 65535 for port in all_ports):
        raise SetupError("Service ports must be between 1 and 65535.")
    if len(set(all_ports)) != len(all_ports):
        raise SetupError("Two project services specify the same local port in .env.")
    allowed_origins = {origin.strip().rstrip("/") for origin in env.app_cors_origins.split(",")}
    if env.public_base_url.rstrip("/") not in allowed_origins:
        raise SetupError("APP_CORS_ORIGINS must include PUBLIC_BASE_URL.")

    environment = {
        **values,
        "APP_BACKEND_URL": env.app_backend_url.rstrip("/"),
        "PUBLIC_BASE_URL": env.public_base_url.rstrip("/"),
        "MYSQL_PORT": str(env.mysql_port),
        "REDIS_PORT": str(env.redis_port),
        "RAG_QDRANT_URL": qdrant_url.rstrip("/"),
        "CELERY_BROKER_URL": env.celery_broker_url,
        "CELERY_RESULT_BACKEND": env.celery_result_backend,
        "MMRAG_QDRANT_PORT": str(qdrant_port),
        "MMRAG_MINIO_PORT": str(minio_port),
        "MMRAG_MINIO_CONSOLE_PORT": str(console_port),
        "MMRAG_BACKEND_PORT": str(backend_port),
        "MMRAG_FRONTEND_PORT": str(frontend_port),
    }
    # Hash settings for process reuse; persist only the hash, never this environment.
    fingerprint = hashlib.sha256(json.dumps(environment, sort_keys=True).encode()).hexdigest()
    return {
        "environment": environment,
        "fingerprint": fingerprint,
        "backend_url": environment["APP_BACKEND_URL"],
        "backend_host": backend.hostname,
        "backend_port": backend_port,
        "frontend_url": environment["PUBLIC_BASE_URL"],
        "frontend_port": frontend_port,
        "infrastructure_ports": infrastructure_ports,
        "worker_node": f"{env.celery_queue_prefix}@%h",
    }


def configuration() -> dict:
    values = read_environment(ROOT / ".env")
    os.environ.update(values)
    from backend.core.config import settings

    return build_configuration(settings.env, values)


def infrastructure_failures(timeout: float = 2) -> list[str]:
    """Probe infrastructure only; collect safe service names, never provider errors."""
    import httpx
    from redis import Redis
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    from backend.core.config import settings

    failures = []
    engine = create_engine(
        settings.build_database_url(), poolclass=NullPool,
        connect_args={"connect_timeout": max(1, int(timeout)), "read_timeout": timeout, "write_timeout": timeout},
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        failures.append("mysql")
    finally:
        engine.dispose()
    client = Redis.from_url(settings.redis_url, socket_connect_timeout=timeout, socket_timeout=timeout)
    try:
        client.ping()
    except Exception:
        failures.append("redis")
    finally:
        client.close()
    scheme = "https" if settings.env.minio_secure else "http"
    urls = {
        "minio": f"{scheme}://{settings.env.minio_endpoint}/minio/health/live",
        "qdrant": (os.getenv("RAG_QDRANT_URL") or f"http://{settings.env.qdrant_host}:{settings.env.qdrant_port}").rstrip("/") + "/readyz",
    }
    with httpx.Client(timeout=timeout, trust_env=False) as client:
        for name, url in urls.items():
            headers = {"api-key": os.environ["RAG_QDRANT_API_KEY"]} if name == "qdrant" and os.getenv("RAG_QDRANT_API_KEY") else {}
            try:
                client.get(url, headers=headers).raise_for_status()
            except Exception:
                failures.append(name)
    return failures


def wait_for_infrastructure(seconds: int) -> None:
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        failures = infrastructure_failures(timeout=max(0.1, min(2, remaining)))
        if not failures:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SetupError("Infrastructure readiness timed out: " + ", ".join(failures) + ".")
        print("Waiting for infrastructure: " + ", ".join(failures), flush=True)
        time.sleep(min(2, remaining))


def validate_compose_port() -> None:
    """The browser URL must use the published frontend port in complete deployment."""
    value = os.getenv("MMRAG_FRONTEND_PORT")
    if not value:
        return
    from backend.core.config import settings
    try:
        port = int(value)
        public = urlsplit(settings.env.public_base_url)
        public_port = public.port or (443 if public.scheme == "https" else 80)
    except ValueError:
        raise SetupError("MMRAG_FRONTEND_PORT must be a valid port.") from None
    if not 1 <= port <= 65535 or port != public_port:
        raise SetupError("MMRAG_FRONTEND_PORT must match PUBLIC_BASE_URL. Update both before starting Compose.")
    origins = {origin.strip().rstrip("/") for origin in settings.env.app_cors_origins.split(",")}
    if settings.env.public_base_url.rstrip("/") not in origins:
        raise SetupError("APP_CORS_ORIGINS must include PUBLIC_BASE_URL.")


def bootstrap(wait_seconds: int = 0) -> None:
    validate_compose_port()
    if wait_seconds:
        wait_for_infrastructure(wait_seconds)
    from backend.infrastructure.database.migrate import MigrationError, upgrade_database
    from backend.infrastructure.database.session import sync_engine
    from backend.infrastructure.storage import ensure_bucket, get_minio_client

    try:
        upgrade_database(sync_engine)
    except MigrationError as exc:
        raise SetupError(str(exc)) from None
    except SetupError:
        raise
    except Exception as exc:
        raise SetupError(
            f"Database initialization failed ({type(exc).__name__}). "
            "Check .env credentials against the existing MySQL volume. Data was preserved."
        ) from None
    finally:
        sync_engine.dispose()
    try:
        ensure_bucket(get_minio_client())
    except Exception as exc:
        raise SetupError(
            f"MinIO initialization failed ({type(exc).__name__}). Check .env and the MinIO logs."
        ) from None
    print("Database tables and MinIO bucket are ready.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "config", "bootstrap"))
    parser.add_argument("--wait-seconds", type=int, default=0)
    args = parser.parse_args()
    if args.wait_seconds < 0 or (args.command != "bootstrap" and args.wait_seconds):
        parser.error("--wait-seconds is a nonnegative bootstrap option.")
    try:
        if args.command == "check":
            print(json.dumps(dependency_status()))
        elif args.command == "config":
            # Captured privately by PowerShell; this output contains .env credentials.
            print(json.dumps(configuration()))
        else:
            bootstrap(args.wait_seconds)
    except SetupError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Setup failed ({type(exc).__name__}); check dependencies and .env.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
