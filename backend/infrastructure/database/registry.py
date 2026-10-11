"""The sole infrastructure entry point that discovers domain-owned ORM models."""

from importlib import import_module

from .base import Base


def register_models():
    for module in (
        "backend.auth.models",
        "backend.upload.models",
        "backend.knowledge.models",
        "backend.chat.models",
        "backend.task.models",
        "backend.cleanup.models",
    ):
        import_module(module)
    return Base.metadata
