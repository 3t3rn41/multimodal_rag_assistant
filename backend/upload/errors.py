"""Typed validation errors for current file uploads."""

from backend.core.errors import ServiceError


class EmptyFileError(ServiceError):
    def __init__(self):
        super().__init__("文件为空，请选择包含内容的文件。", 400)


class UnsupportedFormatError(ServiceError):
    """A format outside the current PDF/DOCX/TXT/MD application contract."""


class FileTooLargeError(ServiceError):
    def __init__(self, limit: int):
        super().__init__(f"文件过大（限制 {limit // 1024 // 1024} MiB）。", 413)
