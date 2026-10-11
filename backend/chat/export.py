"""Markdown export using only saved, trusted citation metadata."""

import math

from backend.chat.models import MessageRole


def citation_label(citation):
    name = citation.get("doc_title") or citation.get("file_name") or "文档"
    page = citation.get("page")
    if isinstance(page, int) and page > 0:
        return f"{name} · 第{page}页"
    start, end = citation.get("time_start"), citation.get("time_end")
    if (
        citation.get("source_type") in {"audio", "video"}
        and all(
            isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
            for value in (start, end)
        )
        and end >= start
    ):

        def clock(value):
            return f"{int(value) // 60:02d}:{int(value) % 60:02d}"

        return f"{name} · {clock(start)}-{clock(end)}"
    return str(name)


def export_markdown(conversation, messages):
    lines = [
        f"# {conversation.title or f'会话 {conversation.id}'}",
        "",
        f"> 模式：{conversation.mode.value} · 状态：{conversation.status.value} · "
        f"创建时间：{conversation.created_time:%Y-%m-%d %H:%M} UTC",
        "",
    ]
    for message in messages:
        if message.role not in {MessageRole.USER, MessageRole.ASSISTANT}:
            continue
        content = message.content or ""
        references = [
            c for c in (message.refs or []) if isinstance(c, dict) and c.get("chunk_id")
        ]
        if message.role == MessageRole.ASSISTANT:
            for citation in references:
                content = content.replace(
                    f"[chunk:{citation['chunk_id']}]", f"[{citation_label(citation)}]"
                )
        lines += [
            "## 提问" if message.role == MessageRole.USER else "## 回答",
            "",
            content,
            "",
        ]
        if message.role == MessageRole.ASSISTANT and references:
            lines += ["### 引用来源", ""]
            for citation in references:
                lines.append(
                    f"- {citation_label(citation)}（chunk_id: `{citation['chunk_id']}`）"
                )
                preview = citation.get("preview")
                if isinstance(preview, str) and preview.strip():
                    lines.extend(f"  > {line}" for line in preview[:500].splitlines())
            lines.append("")
    return "\n".join(lines)
