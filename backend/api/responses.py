"""Explicit media types for non-JSON HTTP contracts."""

from fastapi.responses import PlainTextResponse


class MarkdownResponse(PlainTextResponse):
    media_type = "text/markdown"
