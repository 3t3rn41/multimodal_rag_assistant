"""Redis namespace and the current document queue for ingestion workers."""

from celery import Celery
from kombu import Queue

from backend.core.config import settings
from backend.infrastructure.database import register_models

register_models()

QUEUE_PREFIX = getattr(settings.env, "celery_queue_prefix", "mmrag")
DOCUMENT_QUEUE = f"{QUEUE_PREFIX}.documents"
BROKER_URL = settings.env.celery_broker_url
RESULT_BACKEND = settings.env.celery_result_backend

celery_app = Celery(
    "multimodal_rag_assistant", broker=BROKER_URL, backend=RESULT_BACKEND
)
celery_app.conf.update(
    imports=("backend.task.worker", "backend.cleanup.worker"),
    task_default_queue=DOCUMENT_QUEUE,
    task_queues=(Queue(DOCUMENT_QUEUE),),
    task_routes={"mmrag.ingest_document": {"queue": DOCUMENT_QUEUE}, "mmrag.cleanup_resources": {"queue": DOCUMENT_QUEUE}},
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=5,
    broker_transport_options={
        "visibility_timeout": 3600,
        "global_keyprefix": f"{QUEUE_PREFIX}:",
        "socket_connect_timeout": 5,
        "socket_timeout": 5,
    },
    result_backend_transport_options={"global_keyprefix": f"{QUEUE_PREFIX}:"},
    result_expires=86400,
    timezone="UTC",
    enable_utc=True,
)
