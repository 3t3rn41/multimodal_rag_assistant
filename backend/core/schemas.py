"""UTC at rest; timezone-bearing ISO 8601 at API boundaries."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, field_validator


class APIModel(BaseModel):
    @field_validator("*", mode="after")
    @classmethod
    def utc_dates(cls, value):
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class ValidationIssue(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ErrorBody(BaseModel):
    status: int
    message: str
    details: list[ValidationIssue] | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody
