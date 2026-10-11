import DOMPurify from 'dompurify';
import {marked} from 'marked';
import {escapeHtml} from './markdown';
import type {SourceBlock, SourceRange} from '../types/source';

interface Projection {text: string; offset: number; positions?: number[]; consumed?: number}
interface Segment {start: number; end: number; sourceStart: number; sourceEnd: number}
interface SourceRun {id: string; blockId: string; segments: Segment[]}
export interface RenderedSource {id: string; html: string; runs: SourceRun[]}
interface Token {
  type: string; raw: string; text?: string; tokens?: Token[]; items?: Token[];
  depth?: number; ordered?: boolean; start?: number; href?: string; title?: string | null;
  header?: Cell[]; rows?: Cell[][];
}
interface Cell {text: string; tokens: Token[]}

const TAGS = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'br', 'hr', 'strong', 'em', 'del',
  'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a', 'img', 'span', 'section'];
const ATTRIBUTES = ['href', 'src', 'title', 'alt', 'start', 'colspan', 'rowspan', 'data-source-run', 'data-source-block'];

function imageSource(value: string): string | null {
  if (/^data:image\/[a-z0-9.+-]+(?:;[^,]*)?,/i.test(value)) return value;
  try {
    const url = new URL(value);
    if (url.protocol === 'https:' && !url.username && !url.password) return url.href;
  } catch { /* Relative images require separately uploaded attachments. */ }
  return null;
}

function sourceIndex(origin: Projection, index: number): number {
  return origin.positions?.[index] ?? origin.offset + index;
}

function slice(origin: Projection, start: number, end = origin.text.length): Projection {
  return {text: origin.text.slice(start, end), offset: origin.offset + start, positions: origin.positions?.slice(start, end)};
}

// Marked removes quote/list prefixes and normalizes line breaks. Align only inside
// the containing token, in source order; never search the whole document for words.
function project(text: string, origin: Projection, from = 0): Projection | null {
  const exact = origin.text.indexOf(text, from);
  if (exact >= 0) return {...slice(origin, exact, exact + text.length), consumed: exact + text.length};
  const positions: number[] = [];
  let cursor = from;
  for (let index = 0; index < text.length; index++) {
    const character = text[index];
    while (cursor < origin.text.length && origin.text[cursor] !== character &&
      !(character === ' ' && /\s/.test(origin.text[cursor]))) cursor++;
    if (cursor >= origin.text.length) return null;
    positions.push(sourceIndex(origin, cursor++));
  }
  return {text, offset: 0, positions, consumed: cursor};
}

function escaped(text: string): string {
  return escapeHtml(text);
}

function normalizedLines(text: string): Projection {
  if (!text.includes('\r')) return {text, offset: 0};
  const positions: number[] = [];
  let normalized = '';
  for (let index = 0; index < text.length; index++) {
    positions.push(index);
    normalized += text[index] === '\r' ? '\n' : text[index];
    if (text[index] === '\r' && text[index + 1] === '\n') index++;
  }
  return {text: normalized, offset: 0, positions};
}

export function renderSourceDocument(blocks: SourceBlock[], fileType: string): RenderedSource {
  const nonce = crypto.randomUUID();
  const runs: SourceRun[] = [];
  const allowImages = fileType === 'md';
  let blockId = '';

  function mappedText(text: string, origin: Projection | null, entities = false): string {
    const segments: Segment[] = [];
    let visible = '';
    function append(value: string, start: number, end: number) {
      const outputStart = visible.length;
      visible += value;
      if (!origin || !value) return;
      const sourceStart = sourceIndex(origin, start);
      const sourceEnd = sourceIndex(origin, end - 1) + 1;
      const previous = segments[segments.length - 1];
      if (previous && previous.sourceEnd === sourceStart && end - start === value.length &&
        previous.end - previous.start === previous.sourceEnd - previous.sourceStart) {
        previous.end = visible.length;
        previous.sourceEnd = sourceEnd;
      } else segments.push({start: outputStart, end: visible.length, sourceStart, sourceEnd});
    }
    const entity = /&(?:#[xX][\da-fA-F]+|#\d+|[a-zA-Z][\w]+);/g;
    let cursor = 0;
    for (const match of entities ? text.matchAll(entity) : []) {
      for (; cursor < match.index!; cursor++) append(text[cursor], cursor, cursor + 1);
      const decoder = document.createElement('textarea');
      decoder.innerHTML = match[0];
      append(decoder.value, cursor, cursor + match[0].length);
      cursor += match[0].length;
    }
    for (; cursor < text.length; cursor++) append(text[cursor], cursor, cursor + 1);
    const id = `${nonce}-${runs.length}`;
    runs.push({id, blockId, segments});
    return `<span data-source-run="${id}">${escaped(visible)}</span>`;
  }

  function rawHtml(raw: string, origin: Projection | null): string {
    let result = '';
    for (const match of raw.matchAll(/<!--[\s\S]*?-->|<[^>]*>|[^<]+|</g)) {
      const part = match[0];
      if (part.startsWith('<')) {
        result += part.replace(/\sdata-source-(?:run|block)(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?/gi, '');
      } else result += mappedText(part, origin ? slice(origin, match.index!, match.index! + part.length) : null, true);
    }
    return result;
  }

  function renderTokens(tokens: Token[], origin: Projection | null): string {
    let cursor = 0;
    return tokens.map(token => {
      const mapped = origin ? project(token.raw, origin, cursor) : null;
      cursor = mapped?.consumed ?? cursor;
      return renderToken(token, mapped);
    }).join('');
  }

  function renderToken(token: Token, origin: Projection | null): string {
    const text = token.text ?? token.raw;
    const inner = origin ? project(text, origin) : null;
    const children = () => renderTokens(token.tokens || [], inner);
    switch (token.type) {
      case 'space': return '';
      case 'hr': return '<hr>';
      case 'br': return '<br>';
      case 'heading': return `<h${token.depth}>${children()}</h${token.depth}>`;
      case 'paragraph': return `<p>${children()}</p>`;
      case 'text': return token.tokens ? children() : mappedText(text, inner, true);
      case 'escape': return mappedText(text, origin ? slice(origin, token.raw.length - text.length) : null);
      case 'strong': return `<strong>${children()}</strong>`;
      case 'em': return `<em>${children()}</em>`;
      case 'del': return `<del>${children()}</del>`;
      case 'codespan': return `<code>${mappedText(text, inner)}</code>`;
      case 'code': {
        const fenced = /^\s*(?:`{3,}|~{3,})/.test(token.raw);
        const body = origin && fenced ? slice(origin, token.raw.indexOf('\n') + 1) : origin;
        return `<pre><code>${mappedText(text, body ? project(text, body) : null)}</code></pre>`;
      }
      case 'blockquote': return `<blockquote>${children()}</blockquote>`;
      case 'list': {
        const tag = token.ordered ? 'ol' : 'ul';
        return `<${tag}${token.ordered ? ` start="${Number(token.start) || 1}"` : ''}>${renderTokens(token.items || [], origin)}</${tag}>`;
      }
      case 'list_item': return `<li>${children()}</li>`;
      case 'link': return `<a href="${escaped(token.href || '')}"${token.title ? ` title="${escaped(token.title)}"` : ''}>${children()}</a>`;
      case 'image': {
        const href = token.href || '';
        const src = allowImages ? imageSource(href) : null;
        if (src) return `<img src="${escaped(src)}" alt="${escaped(text || '图片')}"${token.title ? ` title="${escaped(token.title)}"` : ''}>`;
        const relative = href && !/^[a-z][a-z0-9+.-]*:/i.test(href);
        return mappedText(text || '图片', inner) + (relative ? '（缺少配套图片）' : '（图片地址不受支持）');
      }
      case 'html': return rawHtml(token.raw, origin);
      case 'table': {
        const lines = token.raw.split('\n');
        let offset = 0;
        const lineStarts = lines.map(line => {const start = offset; offset += line.length + 1; return start;});
        function row(cells: Cell[], header: boolean, lineIndex: number) {
          const lineStart = lineStarts[lineIndex] || 0;
          const lineOrigin = origin ? slice(origin, lineStart, lineStart + (lines[lineIndex]?.length || 0)) : null;
          let cellCursor = 0;
          return '<tr>' + cells.map(cell => {
            const cellOrigin = lineOrigin ? project(cell.text, lineOrigin, cellCursor) : null;
            cellCursor = cellOrigin?.consumed ?? cellCursor;
            const tag = header ? 'th' : 'td';
            return `<${tag}>${renderTokens(cell.tokens, cellOrigin)}</${tag}>`;
          }).join('') + '</tr>';
        }
        return `<table><thead>${row(token.header || [], true, 0)}</thead><tbody>${(token.rows || []).map((cells, index) => row(cells, false, index + 2)).join('')}</tbody></table>`;
      }
      default: return mappedText(text, inner);
    }
  }

  let previousPage: number | null = null;
  const body = blocks.map(block => {
    blockId = block.id;
    const origin = normalizedLines(block.text);
    let page = '';
    if (block.page && block.page !== previousPage) page = `<p class="source-page">第 ${block.page} 页</p>`;
    previousPage = block.page;
    let content: string;
    if (block.kind === 'markdown' || block.kind === 'table') {
      content = renderTokens(marked.lexer(origin.text, {gfm: true}) as unknown as Token[], origin);
    } else {
      const tag = block.kind === 'heading' ? 'h2' : 'p';
      content = `<${tag}>${mappedText(origin.text, origin)}</${tag}>`;
    }
    return `${page}<section data-source-block="${escaped(block.id)}">${content}</section>`;
  }).join('');

  const markup = DOMPurify.sanitize(body, {
    ALLOWED_TAGS: TAGS, ALLOWED_ATTR: [...ATTRIBUTES, 'class'], ALLOW_DATA_ATTR: false,
    FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'style', 'link', 'meta', 'base', 'form', 'input', 'button'],
    FORBID_ATTR: ['srcset', 'style'],
  });
  const clean = document.implementation.createHTMLDocument('来源正文');
  clean.body.innerHTML = markup;
  const runIds = new Set(runs.map(run => run.id));
  for (const element of clean.body.querySelectorAll<HTMLElement>('[data-source-run]')) {
    if (!runIds.has(element.dataset.sourceRun || '')) element.removeAttribute('data-source-run');
  }
  for (const image of clean.body.querySelectorAll('img')) {
    const original = (image.getAttribute('src') || '').trim();
    const src = allowImages ? imageSource(original) : null;
    const alt = image.getAttribute('alt') || '图片';
    if (src) {
      image.src = src;
      image.alt = alt;
      image.setAttribute('referrerpolicy', 'no-referrer');
      image.setAttribute('decoding', 'async');
    } else {
      const relative = original && !/^[a-z][a-z0-9+.-]*:/i.test(original);
      image.replaceWith(clean.createTextNode(alt + (relative ? '（缺少配套图片）' : '（图片地址不受支持）')));
    }
  }
  for (const link of clean.body.querySelectorAll('a[href]')) {
    const href = link.getAttribute('href') || '';
    if (href.startsWith('#')) continue;
    try {
      if (!['http:', 'https:', 'mailto:'].includes(new URL(href).protocol)) throw new Error('Unsupported link');
      link.setAttribute('target', '_blank');
      link.setAttribute('rel', 'noopener noreferrer');
    } catch {link.removeAttribute('href');}
  }
  const images = allowImages ? 'https: data:' : 'data:';
  const html = `<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${images}; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><style>
    html{overflow-anchor:none}body{margin:0;padding:8px 4px 32px;background:#fff;color:#242622;font-family:system-ui,sans-serif;font-size:15px;line-height:1.85;overflow-wrap:anywhere}
    section>p{white-space:pre-wrap;margin:0 0 16px}h1,h2,h3,h4,h5,h6{line-height:1.45;margin:1.2em 0 .6em}h1{font-size:24px}h2{font-size:20px}h3{font-size:17px}
    .source-page{font-size:12px;color:#747b70;border-top:1px solid #e7e9e3;padding-top:12px;margin:16px 0}ul,ol{padding-left:26px}li{margin:5px 0}li p{margin:0}
    img{display:block;max-width:100%;height:auto;margin:12px 0}pre{padding:12px;background:#f4f5f1;border-radius:6px;overflow:auto;white-space:pre}code{font-family:ui-monospace,monospace;font-size:.9em}
    p code{background:#f4f5f1;padding:2px 4px}table{display:block;max-width:100%;overflow:auto;border-collapse:collapse}th,td{border:1px solid #dce0d8;padding:6px 10px}
    blockquote{margin:16px 0;padding-left:14px;border-left:3px solid #b65536;color:#56604f}a{color:#a9482b}hr{border:0;border-top:1px solid #dce0d8}
  </style></head><body data-source-document="${nonce}">${clean.body.innerHTML}</body></html>`;
  return {id: nonce, html, runs};
}

export function locateSourceRanges(doc: Document, runs: SourceRun[], locations: SourceRange[]): Range[] {
  const selected = new Map<string, SourceRange[]>();
  for (const location of locations) {
    if (location.end <= location.start) continue;
    const list = selected.get(location.block_id) || [];
    list.push(location);
    selected.set(location.block_id, list);
  }
  const elements = new Map(Array.from(doc.querySelectorAll<HTMLElement>('[data-source-run]')).map(element => [element.dataset.sourceRun, element]));
  const ranges: Range[] = [];
  for (const run of runs) {
    const node = elements.get(run.id)?.firstChild;
    if (!node || node.nodeType !== 3) continue;
    const intervals: {start: number; end: number}[] = [];
    for (const location of selected.get(run.blockId) || []) {
      let start = Infinity, end = -1;
      for (const segment of run.segments) {
        const from = Math.max(location.start, segment.sourceStart), to = Math.min(location.end, segment.sourceEnd);
        if (to <= from) continue;
        const linear = segment.end - segment.start === segment.sourceEnd - segment.sourceStart;
        start = Math.min(start, linear ? segment.start + from - segment.sourceStart : segment.start);
        end = Math.max(end, linear ? segment.start + to - segment.sourceStart : segment.end);
      }
      if (end <= start || end > (node.textContent || '').length) continue;
      intervals.push({start, end});
    }
    const merged: {start: number; end: number}[] = [];
    for (const interval of intervals.sort((left, right) => left.start - right.start)) {
      const previous = merged[merged.length - 1];
      if (previous && interval.start <= previous.end) previous.end = Math.max(previous.end, interval.end);
      else merged.push({...interval});
    }
    for (const interval of merged) {
      const range = doc.createRange();
      range.setStart(node, interval.start);
      range.setEnd(node, interval.end);
      ranges.push(range);
    }
  }
  return ranges;
}
