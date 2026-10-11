"""URL 下载、SSRF 防护与 arXiv PDF 链接识别。

- arXiv 链接自动拼 PDF 下载 URL
- 防 SSRF：仅 http/https，禁内网/回环/保留 IP
- 超时 30s，> 50MB 拒绝
- 抓取结果标注来源 URL + 抓取时间
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

MAX_FETCH_BYTES = 50 * 1024 * 1024  # PRD §5.1：文件 > 50MB 拒绝
TIMEOUT = 30.0
MAX_REDIRECTS = 5  # 跟随重定向上限（每跳重新做 SSRF 校验）


class FetchError(ValueError):
    """抓取失败（不支持的协议、超时、过大等）。"""


class SSRFError(FetchError):
    """SSRF 防护拦截（内网/回环地址）。"""


class FetchTooLargeError(FetchError):
    """The URL response exceeds the existing 50 MiB download limit."""


def is_arxiv_url(url: str) -> bool:
    return "arxiv.org" in (urlparse(url).netloc.lower())


def _arxiv_to_pdf(url: str) -> str:
    """arxiv.org/abs/2401.00001 -> arxiv.org/pdf/2401.00001。"""
    if "/abs/" in urlparse(url).path:
        return url.replace("/abs/", "/pdf/", 1)
    return url


def _is_safe_host(host: str) -> bool:
    """禁止内网/回环/保留 IP（防 SSRF）。

    注意：getaddrinfo 解析后到实际连接之间存在 TOCTOU 窗口（DNS rebinding），
    生产环境应在连接层校验 IP。M1 用解析校验已足够防御直连内网 IP 的常见攻击。
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False  # 解析失败，拒绝
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
            or ip.is_multicast
        ):
            return False
    return True


def fetch(url: str) -> tuple[bytes, str, str, dict]:
    """抓取 URL，返回 (content, content_type, filename, meta)。

    - arXiv 链接：下载 PDF
    - 其他 URL：下载响应；上传服务只接受 PDF 内容
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError(f"仅支持 http/https，不支持 {parsed.scheme}")
    if not parsed.hostname:
        raise FetchError("无效的 URL：缺少主机名")
    if not _is_safe_host(parsed.hostname):
        raise SSRFError(f"拒绝访问内网地址：{parsed.hostname}")

    fetch_url = _arxiv_to_pdf(url) if is_arxiv_url(url) else url

    # 手动跟随重定向：httpx 自动 follow 不会重新校验目标地址，
    # 攻击者可用 302 跳到内网绕过 SSRF 防护，必须每跳重新校验。
    with httpx.Client(timeout=TIMEOUT, follow_redirects=False) as client:
        current = fetch_url
        content_type = ""
        content = b""
        for _hop in range(MAX_REDIRECTS + 1):
            with client.stream("GET", current) as resp:
                if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get(
                    "location"
                ):
                    current = str(httpx.URL(current).join(resp.headers["location"]))
                    next_parsed = urlparse(current)
                    if next_parsed.scheme not in ("http", "https"):
                        raise FetchError(f"重定向目标协议不支持：{next_parsed.scheme}")
                    if not next_parsed.hostname or not _is_safe_host(
                        next_parsed.hostname
                    ):
                        raise SSRFError(
                            f"拒绝访问内网地址（重定向）：{next_parsed.hostname}"
                        )
                    continue
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes(chunk_size=65536):
                    total += len(chunk)
                    if total > MAX_FETCH_BYTES:
                        raise FetchTooLargeError(
                            f"文件过大（限制 {MAX_FETCH_BYTES // 1024 // 1024} MiB）。"
                        )
                    chunks.append(chunk)
                content = b"".join(chunks)
                break
        else:
            raise FetchError(f"重定向次数超过 {MAX_REDIRECTS} 次上限")

    # 推断文件名
    if is_arxiv_url(url):
        arxiv_id = urlparse(url).path.rstrip("/").split("/")[-1]
        filename = f"{arxiv_id}.pdf"
    else:
        filename = parsed.path.rstrip("/").split("/")[-1] or "page"
        if "." not in filename:
            filename += ".html"

    meta = {
        "source_url": url,
        "fetched_at": datetime.now(UTC).isoformat(),
        "content_type": content_type,
    }
    logger.info("抓取 %s -> %s (%d bytes)", url, filename, len(content))
    return content, content_type, filename, meta
