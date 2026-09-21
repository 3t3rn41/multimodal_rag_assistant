"""OpenAI-compatible streaming chat adapter for multiple model vendors."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


class ChatModel(Protocol):
    async def stream(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]: ...


@dataclass(frozen=True, slots=True)
class OpenAICompatibleConfig:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = 90.0

    @classmethod
    def from_env(cls) -> "OpenAICompatibleConfig":
        api_key = os.getenv("RAG_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        model = os.getenv("RAG_LLM_MODEL") or os.getenv("OPENAI_MODEL")
        if not api_key:
            raise RuntimeError("RAG_LLM_API_KEY or OPENAI_API_KEY is required")
        if not model:
            raise RuntimeError("RAG_LLM_MODEL or OPENAI_MODEL is required")
        return cls(
            api_key=api_key,
            model=model,
            base_url=os.getenv("RAG_LLM_BASE_URL", "https://api.openai.com/v1"),
        )


class OpenAICompatibleChatModel:
    """Stream ``/chat/completions`` from an OpenAI-compatible API."""

    def __init__(self, config: OpenAICompatibleConfig) -> None:
        self.config = config

    async def stream(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "OpenAICompatibleChatModel requires httpx; install "
                "multimodal-rag-assistant[llm]"
            ) from exc
        endpoint = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": list(messages),
            "temperature": temperature,
            "stream": True,
        }
        timeout = httpx.Timeout(self.config.timeout_seconds, connect=20.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = _extract_delta(event)
                    if delta:
                        yield delta


def _extract_delta(event: Mapping[str, Any]) -> str:
    choices = event.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    delta = choices[0].get("delta", {})
    content = delta.get("content", "") if isinstance(delta, Mapping) else ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, Mapping) and isinstance(part.get("text"), str)
        )
    return ""


async def collect_stream(
    model: ChatModel,
    messages: Sequence[Mapping[str, Any]],
    *,
    temperature: float = 0.0,
) -> str:
    parts: list[str] = []
    async for delta in model.stream(messages, temperature=temperature):
        parts.append(delta)
    return "".join(parts)
