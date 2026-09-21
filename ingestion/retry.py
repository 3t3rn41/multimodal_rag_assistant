"""Small bounded retry policy shared by hosted API transports."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Retry count and exponential backoff for transient API failures."""

    max_retries: int = 3
    backoff_seconds: float = 0.5

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.backoff_seconds < 0 or not _is_finite(self.backoff_seconds):
            raise ValueError("backoff_seconds must be finite and non-negative")


def retry_call(
    operation: Callable[[], T],
    *,
    policy: RetryPolicy,
    is_retryable: Callable[[Exception], bool],
    sleeper: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``operation`` and retry only failures marked transient."""

    for attempt in range(policy.max_retries + 1):
        try:
            return operation()
        except Exception as exc:
            if attempt >= policy.max_retries or not is_retryable(exc):
                raise
            sleeper(policy.backoff_seconds * (2**attempt))
    raise AssertionError("retry loop must return or raise")


def _is_finite(value: float) -> bool:
    return value == value and abs(value) != float("inf")
