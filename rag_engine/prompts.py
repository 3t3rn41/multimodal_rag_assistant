"""Prompt templates for grounded multimodal generation."""

from __future__ import annotations

from collections.abc import Sequence

from .citations import citation_label
from .models import RetrievalCandidate

SYSTEM_PROMPT = """你是一个严谨的多模态知识库问答助手。

回答规则：
1. 只能使用【参考资料】中的证据，不得补写资料中没有的事实。
2. 如果证据不足，明确回答“资料库中未找到足够依据”，不要猜测。
3. 在正文中用 [chunk_id] 标注依据；只允许引用参考资料中出现的 chunk_id。
4. 回答结束时必须输出机器可解析的引用块，格式严格如下：
<<CITATIONS>>
{"citations":[{"chunk_id":"..."}]}
<<END_CITATIONS>>
5. 引用块中的 chunk_id 必须来自参考资料，不能自行编造页码、时间或文件路径。
"""


def build_context(candidates: Sequence[RetrievalCandidate], *, max_chars: int = 12_000) -> str:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    blocks: list[str] = []
    used = 0
    for candidate in candidates:
        chunk = candidate.chunk
        metadata = [
            f"source={chunk.source_type}",
            f"file={chunk.file_id}",
            f"label={citation_label(chunk)}",
        ]
        if chunk.media_path:
            metadata.append(f"media_path={chunk.media_path}")
        block = f"[{chunk.chunk_id}] ({'; '.join(metadata)})\n{chunk.content.strip()}"
        if used and used + len(block) + 2 > max_chars:
            break
        blocks.append(block)
        used += len(block) + 2
    return "\n\n".join(blocks) or "（没有召回到参考资料）"


def build_messages(
    query: str,
    candidates: Sequence[RetrievalCandidate],
    *,
    max_context_chars: int = 12_000,
) -> list[dict[str, str]]:
    context = build_context(candidates, max_chars=max_context_chars)
    user_prompt = f"""【参考资料】
{context}

【用户问题】
{query.strip()}

请先给出简洁、可核验的回答，再输出引用块。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
