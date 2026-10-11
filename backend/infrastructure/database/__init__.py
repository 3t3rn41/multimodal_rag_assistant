"""Database primitives; business models are registered explicitly at entry points."""

from .base import Base
from .registry import register_models

__all__ = ["Base", "register_models"]
