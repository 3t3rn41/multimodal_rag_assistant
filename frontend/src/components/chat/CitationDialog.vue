<template>
 <Teleport to="body" :disabled="panel">
  <section v-if="open" :class="panel?'citation-panel':'citation-overlay'" @click.self="emit('close')">
   <div ref="dialog" :class="panel?'citation-panel-card':'citation-dialog'" :role="panel?'region':'dialog'" :aria-modal="panel?undefined:true" aria-label="来源原文" tabindex="-1">
    <header class="modal-head"><span class="modal-title"><Icon name="citation"/>{{ panel?'Sources':'来源原文' }}</span><button class="btn-icon" title="关闭来源" aria-label="关闭来源面板" @click="emit('close')"><Icon name="x"/></button></header>
    <EmptyState v-if="chunkId==null" title="选择一条引用" description="点击回答中的引用编号，查看对应原文位置。" icon="citation"/>
    <div v-else class="citation-body">
     <h3>{{ source?.file_name||citation?.doc_title||'文档' }}</h3>
     <div class="citation-meta">
      <span v-if="page" class="badge">第 {{ page }} 页</span>
      <span v-if="source?.time_start!=null" class="badge">{{ source.time_start }}–{{ source.time_end }} 秒</span>
      <a v-if="originalUrl" :href="originalUrl" class="btn btn-ghost btn-sm" target="_blank" rel="noopener noreferrer"><Icon name="external"/>打开原文件</a>
      <button v-if="!loading" class="btn-icon" title="重新加载来源" @click="loadSource(true)"><Icon name="refresh"/></button>
     </div>
     <div v-if="loading" class="citation-loading" role="status" aria-label="正在加载引用"><div class="skeleton"/><div class="skeleton"/><div class="skeleton"/></div>
     <div v-else-if="error" class="error-item" role="alert"><span>{{ error }}</span><button class="btn btn-ghost btn-sm" @click="loadSource(true)">重新加载</button></div>
     <SourceReader v-else-if="source" :source="source" :chunk-id="String(chunkId)" :ranges="ranges" :content="content"/>
    </div>
   </div>
  </section>
 </Teleport>
</template>
<script setup lang="ts">
import {ref, shallowRef, computed, watch, onBeforeUnmount} from 'vue';
import Icon from '../common/Icon.vue';
import EmptyState from '../common/EmptyState.vue';
import SourceReader from './SourceReader.vue';
import {http, apiReadErrorMessage, isCanceledRequest, isUnavailableResource} from '../../api/http';
import {safePreviewUrl, pdfPageUrl} from '../../utils/citation';
import {useOverlayFocus} from '../../composables/useOverlayFocus';
import type {Citation} from '../../types/workbench';
import type {ChunkSource} from '../../types/source';

const props = withDefaults(defineProps<{open:boolean;chunkId?:string|number|null;citation?:Citation|null;panel?:boolean}>(), {chunkId:null,citation:null,panel:false});
const emit = defineEmits<{close:[]}>();
const dialog = ref<HTMLElement|null>(null);
const source = shallowRef<ChunkSource|null>(null);
const loading = ref(false), error = ref<string|null>(null);
const cache = new Map<string, ChunkSource>();
let sequence = 0, controller: AbortController|null = null;

const ranges = computed(() => source.value?.locations[String(props.chunkId)] || []);
const content = computed(() => source.value?.contents[String(props.chunkId)] || '');
const page = computed(() => {
 const current = source.value;
 if (!current) return null;
 const located = ranges.value.map(range => current.blocks.find(block => block.id === range.block_id)).find(block => block?.page);
 return located?.page ?? (current.chunk_id === String(props.chunkId) ? current.page : null);
});
const originalUrl = computed(() => {
 if (!source.value) return null;
 const url = safePreviewUrl(source.value.original_url);
 return source.value.file_type === 'pdf' ? pdfPageUrl(url, page.value) : url;
});
useOverlayFocus(computed(() => props.open&&!props.panel), dialog, () => emit('close'));

async function loadSource(force = false) {
 if (!props.open || props.chunkId == null) return;
 controller?.abort(); controller = null;
 const request = ++sequence;
 const id = String(props.chunkId);
 error.value = null;
 if (!force) {
  const saved = Array.from(cache.values()).find(item => Object.hasOwn(item.locations, id));
  if (saved) {source.value = saved; loading.value = false; return;}
 }
 const pending = new AbortController(); controller = pending;
 loading.value = true; source.value = null;
 try {
  const {data} = await http.get<ChunkSource>('/chunks/'+encodeURIComponent(id)+'/source', {signal:pending.signal});
  if (request !== sequence || !props.open) return;
  cache.set(data.file_id+':'+data.generation, data);
  source.value = data;
 } catch (err) {
  if (request !== sequence || !props.open || isCanceledRequest(err)) return;
  if (isUnavailableResource(err)) {
   cache.clear();
   error.value = '来源已删除或无法查看';
  } else error.value = apiReadErrorMessage(err, '来源读取失败，请稍后重试。');
 } finally {
  if (request === sequence) {loading.value = false; controller = null;}
 }
}
function clearSource() {
 sequence++; controller?.abort(); controller = null;
 source.value = null; cache.clear(); error.value = null; loading.value = false;
}
function clearAccount() {clearSource(); emit('close');}
watch(() => [props.open, props.chunkId], () => {
 if (props.open && props.chunkId != null) loadSource(); else clearSource();
}, {immediate:true});
window.addEventListener('mmrag-account-cleared', clearAccount);
onBeforeUnmount(() => {clearSource(); window.removeEventListener('mmrag-account-cleared', clearAccount);});
</script>
<style scoped>
.citation-overlay{position:fixed;inset:0;z-index:var(--z-dialog);background:rgb(36 38 34 / .25);display:grid;place-items:center;padding:20px}
.citation-dialog{width:min(100%,860px);height:min(760px,90dvh);display:flex;flex-direction:column;min-height:0;background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.citation-panel,.citation-panel-card{height:100%;display:flex;flex-direction:column;min-height:0;background:var(--surface)}
.citation-panel-card{width:100%}.modal-title{display:flex;align-items:center;gap:9px;font-size:15px}.modal-title svg{width:17px;height:17px;color:var(--ink-mute)}
.citation-body{padding:20px;min-height:0;flex:1;display:flex;flex-direction:column}.citation-body h3{font-size:16px;line-height:1.6;overflow-wrap:anywhere;margin-bottom:12px;flex-shrink:0}
.citation-meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:16px;flex-shrink:0}.citation-meta>.btn-icon{margin-left:auto}
.citation-loading{display:flex;flex-direction:column;gap:10px}.citation-loading .skeleton{height:14px}.citation-loading .skeleton:last-child{width:70%}
</style>
