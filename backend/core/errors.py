"""Expected failures with safe messages; never carry provider responses or secrets."""


class ServiceError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code
