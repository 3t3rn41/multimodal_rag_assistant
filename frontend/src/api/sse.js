// SSE 消费：POST /chat 返回 text/event-stream，EventSource 只支持 GET，
// 所以用 fetch + ReadableStream 手动解析。解析逻辑是纯函数，便于单测。
import { csrfHeaders } from "./csrf";

/**
 * 增量解析 SSE 缓冲，返回 { frames, rest }。
 * 一个 SSE 事件以空行（\n\n）分隔，字段形如 `event: x` / `data: {...}`。
 */
function extractFrames(buffer) {
  const frames = [];
  let rest = buffer;
  let idx;
  while ((idx = searchBoundary(rest)) !== -1) {
    const raw = rest.slice(0, idx.boundaryStart);
    rest = rest.slice(idx.boundaryEnd);
    const frame = parseOne(raw);
    if (frame) frames.push(frame);
  }
  return { frames, rest };
}

function searchBoundary(text) {
  const a = text.indexOf("\n\n");
  const b = text.indexOf("\r\n\r\n");
  if (a === -1) return b === -1 ? -1 : { boundaryStart: b, boundaryEnd: b + 4 };
  if (b === -1) return { boundaryStart: a, boundaryEnd: a + 2 };
  return a < b ? { boundaryStart: a, boundaryEnd: a + 2 } : { boundaryStart: b, boundaryEnd: b + 4 };
}

function parseOne(raw) {
  let data = "";
  for (const line of raw.split(/\r?\n/)) {
    if (line.startsWith("data:")) {
      data += (data ? "\n" : "") + line.slice(5).trimStart();
    }
  }
  if (!data) return null;
  try {
    return JSON.parse(data);
  } catch {
    return null; // 脏帧静默丢弃，不让单条坏数据打断整流
  }
}

/**
 * 发起 SSE POST 请求并逐事件回调。
 * data 行是扁平的事件 payload（事件类型在 payload.event 字段）。
 * Session cookies and CSRF headers use the same policy as the JSON API client.
 */
export async function sseStream(url, body, onEvent, signal) {
  let resp;
  try {
    resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...csrfHeaders() },
      credentials: "same-origin",
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if (e.name === "AbortError") return;
    onEvent("error", { message: "无法连接后端：" + e.message });
    return;
  }

  if (!resp.ok) {
    if (resp.status === 401 && typeof window !== "undefined") window.dispatchEvent(new Event("mmrag-session-expired"));
    let detail = `HTTP ${resp.status}`;
    try {
      const body2 = await resp.json();
      if (body2?.detail) {
        if (typeof body2.detail === "string") detail = body2.detail;
        else if (Array.isArray(body2.detail) && body2.detail[0]?.msg) detail = String(body2.detail[0].msg);
        else detail = JSON.stringify(body2.detail);
      }
      if (body2?.error?.message) detail = body2.error.message;
    } catch {
      /* 忽略解析失败，用状态码兜底 */
    }
    onEvent("error", { message: detail });
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { frames, rest } = extractFrames(buffer);
      buffer = rest;
      for (const f of frames) onEvent(f.event || "message", f);
    }
    // 冲刷 decoder 剩余字节（多字节字符被拆到最后一个 chunk 时也能完整解析）
    buffer += decoder.decode();
    // 冲刷末尾（防御无边界结尾）
    for (const f of extractFrames(buffer + "\n\n").frames) onEvent(f.event || "message", f);
  } catch (e) {
    if (e.name !== "AbortError") onEvent("error", { message: "流读取中断：" + e.message });
  }
}
