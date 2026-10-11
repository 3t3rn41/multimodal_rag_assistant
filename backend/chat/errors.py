"""Safe operational errors for chat orchestration."""


class ChatServiceError(RuntimeError):
    """Operational error containing only a safe, user-facing explanation."""

    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code
