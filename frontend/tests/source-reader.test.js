import {describe, expect, it} from 'vitest';
import {readFileSync} from 'node:fs';
import {renderSourceDocument, locateSourceRanges} from '../src/utils/source-reader';
import {numberedCitations, decorateCitationNumbers} from '../src/utils/citation-label';
import {createStreamRenderer} from '../src/utils/markdown';

function render(text, kind = 'markdown', format = 'md') {
 const compiled = renderSourceDocument([{id: 'body', kind, text, page: null}], format);
 return {compiled, doc: new DOMParser().parseFromString(compiled.html, 'text/html')};
}

it('renders Markdown headings, lists, tables, code and literal document citation markers', () => {
 const {doc} = render(readFileSync('../tests/fixtures/preview.md', 'utf8'));
 expect(doc.querySelector('h1')?.textContent).toBe('Markdown 标题');
 expect(doc.querySelectorAll('li')).toHaveLength(2);
 expect(doc.querySelector('table')).not.toBeNull();
 expect(doc.querySelector('blockquote')?.textContent).toContain('引用段落');
 expect(doc.querySelector('pre code')?.textContent).toContain('print("中文代码")');
 expect(doc.body.textContent).toContain('[chunk:original-document]');
 expect(doc.querySelector('[data-cite], script, iframe, [onerror], [srcset]')).toBeNull();
 expect([...doc.querySelectorAll('img')].map(image => image.alt)).toEqual(['图片替代文字', 'HTML 图片替代文字']);
 expect([...doc.querySelectorAll('img')].every(image => image.getAttribute('referrerpolicy') === 'no-referrer')).toBe(true);
 expect(doc.querySelector('a[href]')?.getAttribute('rel')).toBe('noopener noreferrer');
});

it('preserves HTTPS, embedded raster and SVG images as non-executable images', () => {
 const png = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=';
 const svg = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>');
 const {doc, compiled} = render(`![网络](https://example.invalid/image.png)\n![内嵌](${png})\n<img src="${svg}" onerror="alert(1)" srcset="https://example.invalid/extra.png 2x">`);
 expect([...doc.querySelectorAll('img')].map(image => image.getAttribute('src'))).toEqual(['https://example.invalid/image.png', png, svg]);
 expect(doc.querySelector('svg, script, [onerror], [srcset], [crossorigin]')).toBeNull();
 expect(compiled.html).toContain("default-src 'none'");
 expect(compiled.html).toContain('img-src https: data:');
});

it.each(['http://example.invalid/a.png', 'javascript:alert(1)', 'file:///tmp/a.png', 'blob:https://example.invalid/a',
 'data:text/html;base64,PHNjcmlwdD4=', 'https://name:password@example.invalid/a.png'])('does not expose unsupported image %s', src => {
 const {doc} = render(`<img src="${src}" alt="图片说明">`);
 expect(doc.querySelector('img')).toBeNull();
 expect(doc.body.textContent).toContain('图片说明（图片地址不受支持）');
});

it('keeps relative image explanations and safe manual links', () => {
 const {doc} = render('![本地图](./images/a.png) [附件](./a.pdf) [邮箱](mailto:test@example.invalid)');
 expect(doc.querySelector('img')).toBeNull();
 expect(doc.body.textContent).toContain('本地图（缺少配套图片）');
 expect(doc.querySelector('a')?.hasAttribute('href')).toBe(false);
 expect(doc.querySelector('a[href]')?.getAttribute('href')).toBe('mailto:test@example.invalid');
});

it.each([
 ['# 标题\n\n前文 **引用文字** 后文', '引用文字'],
 ['前文 [引用文字](https://example.invalid/引用文字) 后文', '引用文字'],
 ['| 引用文字 | 值 |\n| --- | --- |\n| 引用文字 | 42 |', '引用文字', true],
 ['| 字段 | 值 |\n| --- | --- |\n| --- | 42 |', '---', true],
 ['> 第一行\n> 引用文字\n', '引用文字'],
 ['- 第一项\n- 引用文字\n', '引用文字'],
 ['```python\npython\n引用文字\n```', '引用文字'],
 ['<p title="引用文字">引用文字 <strong>后文</strong></p>', '引用文字', true],
 ['# 标题\r\n\r\n**引用文字**\r\n\r\n引用文字\r\n', '引用文字', true],
])('maps visible Markdown text to its exact source occurrence: %s', (text, target, last = false) => {
 const {doc, compiled} = render(text);
 const start = last ? text.lastIndexOf(target) : text.indexOf(target);
 const before = doc.body.innerHTML;
 const ranges = locateSourceRanges(doc, compiled.runs, [{block_id: 'body', start, end: start + target.length}]);
 expect(ranges.length).toBeGreaterThan(0);
 expect(ranges.map(range => range.toString()).join('')).toBe(target);
 expect(doc.body.innerHTML).toBe(before);
});

it('keeps escaped duplicate table cells in their own column',()=>{
 const text='| 字段 | 值 |\n| --- | --- |\n| a\\|b | a\\|b |';
 const {doc,compiled}=render(text);
 const start=text.lastIndexOf('a\\|b');
 const ranges=locateSourceRanges(doc,compiled.runs,[{block_id:'body',start,end:start+4}]);
 expect(ranges.map(range=>range.toString()).join('')).toBe('a|b');
 expect(ranges.every(range=>range.startContainer.parentElement.closest('td')===doc.querySelector('td:last-child'))).toBe(true);
});

it('merges overlapping location ranges without wrapping text',()=>{
 const {doc,compiled}=render('abcdef','text','txt');
 const before=doc.body.innerHTML;
 const ranges=locateSourceRanges(doc,compiled.runs,[{block_id:'body',start:1,end:4},{block_id:'body',start:2,end:5}]);
 expect(ranges.map(range=>range.toString())).toEqual(['bcde']);
 expect(doc.body.innerHTML).toBe(before);
});

it('does not locate fenced language labels instead of code with the same text', () => {
 const text = '```python\npython\n```';
 const {doc, compiled} = render(text);
 expect(locateSourceRanges(doc, compiled.runs, [{block_id:'body', start:4, end:10}])).toHaveLength(0);
 expect(locateSourceRanges(doc, compiled.runs, [{block_id:'body', start:10, end:16}]).map(range=>range.toString())).toEqual(['python']);
});

it('locates decoded entities, emoji and partial UTF-16 ranges', () => {
 const text = '前😀 &amp; **中文引用** 后';
 const {doc, compiled} = render(text);
 const start = text.indexOf('😀');
 const ranges=locateSourceRanges(doc, compiled.runs, [{block_id:'body', start, end:text.indexOf(' 后')}]);
 expect(ranges.map(range => range.toString()).join('')).toBe('😀 & 中文引用');
 expect(locateSourceRanges(doc, compiled.runs, [{block_id:'body', start:text.indexOf('文引用'), end:text.indexOf('文引用')+2}]).map(range=>range.toString())).toEqual(['文引']);
});

it('renders document page, heading and table ranges without treating plain text as HTML', () => {
 const compiled = renderSourceDocument([
  {id:'heading',kind:'heading',text:'标题',page:3},
  {id:'text',kind:'paragraph',text:'中文😀 <script>alert(1)</script>\r\n下一行',page:3},
  {id:'table',kind:'table',text:'| 字段 | 值 |\n| --- | --- |\n| 中文 | 42 |',page:4},
 ], 'docx');
 const doc = new DOMParser().parseFromString(compiled.html,'text/html');
 const ranges=locateSourceRanges(doc,compiled.runs,[{block_id:'heading',start:0,end:2},{block_id:'text',start:0,end:4}]);
 expect(ranges.map(range=>range.toString())).toEqual(['标题','中文😀']);
 expect(doc.querySelector('table')).not.toBeNull();
 expect(doc.querySelector('script')).toBeNull();
 expect(doc.body.textContent).toContain('<script>alert(1)</script>\n下一行');
 expect([...doc.querySelectorAll('.source-page')].map(page=>page.textContent)).toEqual(['第 3 页','第 4 页']);
 expect(compiled.html).toContain('img-src data:');
});

it('keeps original TXT offsets after browser line-ending normalization',()=>{
 const text='第一段\r\n第二段😀引用';
 const {doc,compiled}=render(text,'text','txt');
 const start=text.indexOf('第二段');
 expect(locateSourceRanges(doc,compiled.runs,[{block_id:'body',start,end:text.length}]).map(range=>range.toString())).toEqual(['第二段😀引用']);
});

it.each(['pdf','docx','txt','md'])('returns inert %s location ranges without highlight styles or markers',format=>{
 const {doc,compiled}=render('正文😀内容',format==='md'?'markdown':'text',format);
 const before=doc.documentElement.outerHTML;
 const ranges=locateSourceRanges(doc,compiled.runs,[{block_id:'body',start:2,end:4}]);
 expect(ranges.map(range=>range.toString())).toEqual(['😀']);
 expect(doc.documentElement.outerHTML).toBe(before);
 expect(compiled.html).not.toMatch(/::highlight|source-highlight/);
 expect(doc.querySelector('mark')).toBeNull();
});

describe('answer citation numbering', () => {
 const citations = [{chunk_id:'b',doc_title:'B.pdf',page:2},{chunk_id:'a',doc_title:'A.md'},{chunk_id:'c',doc_title:'C.txt'}];
 const answer = '第一处 [chunk:a]\n\n第二处 [chunk:b] 和重复 [chunk:a]。';
 it('shares first-appearance numbering with the footer and appends extra trusted references', () => {
  expect(numberedCitations(answer,citations).map(entry=>[entry.citation.chunk_id,entry.number])).toEqual([['a',1],['b',2],['c',3]]);
 });
 it('renumbers cached stream blocks against the whole answer and suppresses untrusted references', () => {
  const stream = createStreamRenderer();
  stream('第一处 [chunk:a]\n\n第二处 ',true);
  const result = decorateCitationNumbers(stream(answer+'\n\n未知 [chunk:invented]\n\n尾部',true),answer,citations);
  const doc = new DOMParser().parseFromString(result,'text/html');
  expect([...doc.querySelectorAll('.cite-slot')].map(node=>node.textContent)).toEqual(['1','2','1']);
  expect(doc.querySelector('[data-cite="b"]')?.getAttribute('title')).toBe('B.pdf · 第2页');
  expect(doc.querySelector('[data-cite="invented"]')).toBeNull();
 });
});
