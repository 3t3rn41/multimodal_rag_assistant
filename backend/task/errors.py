"""State conflicts for durable task scheduling."""

from backend.core.errors import ServiceError


class TaskConflictError(ServiceError):
    def __init__(self, message: str):
        super().__init__(message, 409)


class StaleIngestionTask(RuntimeError):
    """A reparse/delete/new task superseded the running task."""


class IngestionConfigurationError(ValueError):
    """Safe, actionable configuration failure."""


class EmptyDocumentError(ValueError):
    """No searchable text was extracted by the original parser or fallback."""


class InvalidTextEncodingError(ValueError):
    """An original text document cannot be decoded with supported encodings."""
