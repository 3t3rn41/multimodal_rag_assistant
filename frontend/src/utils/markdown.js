import { marked } from "marked";
import DOMPurify from "dompurify";

// 引用使用团队 Chunk 的字符串标识（例如 12:g1:document:0001）。
// 限制标识字符，避免把属性、HTML 或普通 Markdown 链接当作引用。
const CITATION_RE = /\[chunk:\s*([A-Za-z0-9][A-Za-z0-9_.:-]*)\s*\]/g;

export function citationId(raw) {
  return String(raw);
}

const CODE_BLOCK_RENDERER = new marked.Renderer();
CODE_BLOCK_RENDERER.code = ({ text, lang }) => {
  const langTag = lang ? `<span class="cb-lang">${escapeHtml(lang)}</span>` : "";
  return (
    `<div class="code-block">` +
    `<div class="cb-head">${langTag}<span class="cb-spacer"></span>` +
    `<button type="button" class="cb-copy">复制</button>` +
    `<button type="button" class="cb-expand">展开</button></div>` +
    `<pre><code>${escapeHtml(text)}</code></pre></div>`
  );
};

/** HTML 转义（用于代码内容 / 语言标签）。 */
export function escapeHtml(s = "") {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** 提取答案文本中的引用 id 序列（保持出现顺序，去重）。 */
export function extractCitations(text = "") {
  const ids = [];
  const seen = new Set();
  for (const m of text.matchAll(CITATION_RE)) {
    const id = citationId(m[1]);
    if (!seen.has(id)) {
      seen.add(id);
      ids.push(id);
    }
  }
  return ids;
}

/** 把 [chunk:N] 替换为角标占位 span（消毒后仍保留 data-cite）。 */
function prepareMarkdown(text = "") {
  const ids = extractCitations(text).map(String);
  return text.replace(CITATION_RE, (_, id) => {
    const label = ids.indexOf(id) + 1;
    return `<sup class="cite-slot" data-cite="${escapeHtml(id)}" role="button" tabindex="0" aria-label="查看引用 ${label}">${label}</sup>`;
  });
}

/** Markdown → 安全 HTML：先插引用占位，marked 渲染后 DOMPurify 消毒。 */
function renderMarkdown(text = "") {
  const html = marked.parse(prepareMarkdown(text), { async: false, renderer: CODE_BLOCK_RENDERER });
  return DOMPurify.sanitize(html, { ADD_ATTR: ["data-cite"] });
}

/** 把纯文本（无 markdown）转安全 HTML（保留换行）。 */
function renderPlain(text = "") {
  return DOMPurify.sanitize(text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"))
    .replace(/\n/g, "<br>");
}

/**
 * 流式文本切分：把"已稳定"的 Markdown 前缀与"未完成"的尾部切开。
 * 稳定前缀以最后一个空行（\n\n）为界；若代码块未闭合，则退到代码块起点，
 * 避免把半截代码块交给 Markdown 渲染造成闪烁/重排。
 */
function splitStreamText(text = "") {
  const fenceCount = (text.match(/```/g) || []).length;
  if (fenceCount % 2 === 1) {
    const fence = text.lastIndexOf("```");
    return { stable: text.slice(0, fence), tail: text.slice(fence) };
  }
  const para = text.lastIndexOf("\n\n");
  if (para === -1) return { stable: "", tail: text };
  if (text.slice(para).trim() === "") return { stable: text.slice(0, para), tail: "" };
  return { stable: text.slice(0, para), tail: text.slice(para) };
}

/**
 * 流式增量渲染器：流式期间只把"新增的稳定块"交给 Markdown 渲染并缓存，
 * 尾部始终以纯文本预览展示（不做 Markdown 解析），结束后一次性全量渲染。
 * 复杂度从"每 chunk 全量重解析（O(n²)）"降为"每块只解析一次（O(n)）"。
 */
export function createStreamRenderer(renderBlock = renderMarkdown) {
  let stableRendered = 0;
  let stableHtml = "";

  return function renderStreamHtml(text = "", streaming = true) {
    if (!streaming) {
      stableRendered = 0;
      stableHtml = "";
      return renderMarkdown(text);
    }
    const { stable, tail } = splitStreamText(text);
    // 重试/清空导致前缀回退时重置缓存
    if (stable.length < stableRendered) {
      stableRendered = 0;
      stableHtml = "";
    }
    // 上一帧的尾部（含空行分隔）现在进入了稳定前缀，渲染前去掉前导换行
    const delta = stable.slice(stableRendered).replace(/^\n+/, "");
    if (delta) stableHtml += renderBlock(delta);
    stableRendered = stable.length;
    return stableHtml + (tail ? `<span class="stream-preview">${renderPlain(tail)}</span>` : "");
  };
}
