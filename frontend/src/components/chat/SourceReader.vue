<template>
 <div class="source-reader">
  <div v-if="!located" class="source-fallback" role="status"><p>暂未定位到全文，以下为可信引用原文。</p><pre>{{ content }}</pre></div>
  <iframe v-if="source.blocks.length" ref="frame" :srcdoc="rendered.html" sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" referrerpolicy="no-referrer" title="来源正文" class="source-document-frame" @load="frameLoaded"/>
 </div>
</template>
<script setup lang="ts">
import {ref, shallowRef, watch, onBeforeUnmount} from 'vue';
import {renderSourceDocument, locateSourceRanges} from '../../utils/source-reader';
import type {RenderedSource} from '../../utils/source-reader';
import type {ChunkSource, SourceRange} from '../../types/source';

const props = defineProps<{source: ChunkSource; chunkId: string; ranges: SourceRange[]; content: string}>();
const frame = ref<HTMLIFrameElement | null>(null);
const rendered = shallowRef<RenderedSource>({id: '', html: '', runs: []});
const locationRanges = shallowRef<Range[]>([]);
const located = ref(true);
let readerDocument: Document | null = null;
let userScrolled = false, automaticUntil = 0;
let detach: (() => void) | null = null;
let observer: ResizeObserver | null = null;
let waiting: ReturnType<typeof setTimeout> | null = null;

function release() {
 if (waiting) clearTimeout(waiting); waiting = null;
 detach?.(); detach = null;
 observer?.disconnect(); observer = null;
 readerDocument = null;
 locationRanges.value = [];
}
function position() {
 if (userScrolled || !readerDocument || !locationRanges.value.length) return;
 const range = locationRanges.value[0];
 const rect = typeof range.getBoundingClientRect === 'function' ? range.getBoundingClientRect() : null;
 const view = readerDocument.defaultView;
 if (!rect || !view) return;
 automaticUntil = Date.now() + 150;
 view.scrollTo({top: Math.max(0, view.scrollY + rect.top - 48), behavior: 'instant'});
}
function selectCitation() {
 userScrolled = false;
 located.value = props.ranges.length > 0;
 if (!readerDocument) return;
 locationRanges.value = locateSourceRanges(readerDocument, rendered.value.runs, props.ranges);
 located.value = locationRanges.value.length > 0;
 position();
}
function frameLoaded() {
 const doc = frame.value?.contentDocument;
 if (!doc?.body || doc.body.dataset.sourceDocument !== rendered.value.id || doc.readyState === 'loading') return;
 if (readerDocument === doc) return;
 release();
 readerDocument = doc;
 const view = doc.defaultView;
 if (!view) return;
 const manual = () => {userScrolled = true;};
 const key = (event: KeyboardEvent) => {if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key)) manual();};
 const scrolled = () => {if (Date.now() > automaticUntil) manual();};
 view.addEventListener('wheel', manual, {passive: true});
 view.addEventListener('touchstart', manual, {passive: true});
 view.addEventListener('pointerdown', manual);
 view.addEventListener('keydown', key);
 view.addEventListener('scroll', scrolled, {passive: true});
 const images = Array.from(doc.querySelectorAll('img'));
 const failed = (event: Event) => {
  const image = event.target as HTMLImageElement;
  image.replaceWith(doc.createTextNode(image.alt || '图片'));
  position();
 };
 for (const image of images) {
  image.addEventListener('load', position); image.addEventListener('error', failed);
  if (image.complete && !image.naturalWidth) image.replaceWith(doc.createTextNode(image.alt || '图片'));
 }
 detach = () => {
  view.removeEventListener('wheel', manual); view.removeEventListener('touchstart', manual);
  view.removeEventListener('pointerdown', manual); view.removeEventListener('keydown', key); view.removeEventListener('scroll', scrolled);
  for (const image of images) {image.removeEventListener('load', position); image.removeEventListener('error', failed);}
 };
 if (typeof ResizeObserver !== 'undefined' && frame.value) {
  observer = new ResizeObserver(position);
  observer.observe(frame.value);
 }
 selectCitation();
}
function waitForDocument() {
 if (waiting) clearTimeout(waiting); waiting = null;
 if (!frame.value) return;
 frameLoaded();
 if (!readerDocument) waiting = setTimeout(waitForDocument, 20);
}
watch(() => props.source, source => {
 release();
 rendered.value = renderSourceDocument(source.blocks, source.file_type);
 located.value = props.ranges.length > 0;
}, {immediate: true});
watch(() => [props.chunkId, props.ranges], selectCitation);
watch([frame, rendered], waitForDocument, {flush: 'post'});
onBeforeUnmount(release);
</script>
<style scoped>
.source-reader{flex:1;min-height:0;display:flex;flex-direction:column;gap:12px}
.source-document-frame{flex:1;min-height:0;width:100%;height:100%;border:0;background:var(--surface)}
.source-fallback{max-height:50%;overflow:auto;flex-shrink:0;font-size:13px;line-height:1.8}.source-fallback p{color:var(--ink-mute);margin-bottom:8px}.source-fallback pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;background:var(--accent-soft);padding:12px;border-radius:6px}
</style>
