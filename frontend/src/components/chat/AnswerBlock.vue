<template>
  <div class="answer-block">
    <div class="ab-head">
      <Icon name="spark" style="color:var(--accent)" />
      <span>回答</span>
      <span v-if="item.streaming" class="badge accent pulse"><span class="bdot" />生成中</span>
      <div class="ab-actions">
        <button class="btn-icon" title="查看过程" @click="emit('show-process')"><Icon name="graph" /></button>
        <button class="btn-icon" title="复制回答" :disabled="!item.content" @click="copyAnswer"><Icon name="copy" /></button>
        <button v-if="canRegenerate" class="btn-icon" title="重新生成" :disabled="item.streaming" @click="emit('regenerate')">
          <Icon name="refresh" />
        </button>
        <button class="btn-icon" :class="{ on: item.feedback === 'up' }" title="有帮助" :disabled="item.streaming || !item.messageId" @click="feedback('up')">
          <Icon name="thumbUp" />
        </button>
        <button class="btn-icon" :class="{ on: item.feedback === 'down' }" title="没帮助" :disabled="item.streaming || !item.messageId" @click="feedback('down')">
          <Icon name="thumbDown" />
        </button>
      </div>
    </div>
    <div class="ab-body" @click="onBodyClick" @keydown="onBodyKeydown" v-html="html"></div>
    <div v-if="item.citations?.length" class="answer-sources" aria-label="回答引用">
      <button v-for="entry in citations" :key="entry.citation.chunk_id" class="btn btn-ghost btn-sm"
        @click="showCitation(entry.citation.chunk_id)">
        <span class="cite-number">{{ entry.number }}</span>{{ citationLabel(entry.citation) }}
      </button>
    </div>
    <div v-if="showCursor" class="cursor-line"><span class="cursor" /></div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount } from "vue";
import Icon from "../common/Icon.vue";
import { createStreamRenderer, citationId } from "../../utils/markdown";
import { toast } from "../../utils/toast";
import { citationLabel, numberedCitations, decorateCitationNumbers } from "../../utils/citation-label";

const props = defineProps({
  item: { type: Object, required: true },
  canRegenerate: { type: Boolean, default: false },
});
const emit = defineEmits(["regenerate", "feedback", "show-process", "show-citation"]);
const citations = computed(() => numberedCitations(props.item.content || "", props.item.citations || []));

const html = ref("");
const streamRender = createStreamRenderer();
let raf = 0;

/** 流式期间增量渲染稳定块 + 纯文本尾部；结束后一次性全量渲染。 */
function scheduleRender() {
  if (raf) cancelAnimationFrame(raf);
  raf = requestAnimationFrame(() => {
    raf = 0;
    html.value = decorateCitationNumbers(streamRender(props.item.content || "", props.item.streaming === true), props.item.content || "", props.item.citations || []);
  });
}

watch(() => props.item.content, scheduleRender, { immediate: true });
watch(() => props.item.citations, scheduleRender, { deep: true });
watch(() => props.item.streaming, (streaming) => {
  if (!streaming) scheduleRender();
});
onBeforeUnmount(() => {
  if (raf) cancelAnimationFrame(raf);
});

const showCursor = computed(() => props.item.streaming);

function onBodyClick(e) {
  const el = e.target.closest?.(".cite-slot, .cb-copy, .cb-expand");
  if (!el) return;
  if (el.classList.contains("cite-slot")) {
    showCitation(el.dataset.cite);
    return;
  }
  if (el.classList.contains("cb-copy")) {
    const code = el.closest(".code-block")?.querySelector("pre code")?.textContent || "";
    navigator.clipboard
      .writeText(code)
      .then(() => toast("代码已复制", "success"))
      .catch(() => toast("复制失败，请手动复制", "error"));
    return;
  }
  if (el.classList.contains("cb-expand")) {
    const block = el.closest(".code-block");
    if (!block) return;
    const expanded = block.classList.toggle("expanded");
    el.textContent = expanded ? "收起" : "展开";
  }
}

function showCitation(raw) {
  if (raw == null || raw === "") return;
  const citation = props.item.citations?.find(cite => String(cite.chunk_id) === citationId(raw));
  if (citation) emit("show-citation", { chunkId: citationId(raw), citation });
}

function onBodyKeydown(e) {
  if (!["Enter", " "].includes(e.key) || !e.target.closest?.(".cite-slot")) return;
  e.preventDefault();
  showCitation(e.target.closest(".cite-slot").dataset.cite);
}

async function copyAnswer() {
  const text = props.item.content || "";
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    toast("回答已复制", "success");
  } catch {
    toast("复制失败，请手动选择复制", "error");
  }
}

function feedback(kind) {
  if (props.item.streaming) return;
  const next = props.item.feedback === kind ? null : kind;
  emit("feedback", { messageId: props.item.messageId, kind: next });
}
</script>

<style scoped>
.answer-sources { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 14px; padding-top: 10px; border-top: 1px solid var(--line-soft); }
.answer-sources button { max-width: 100%; overflow-wrap: anywhere; text-align: left; }
.cite-number { display:inline-flex; align-items:center; justify-content:center; flex:none; width:20px; height:20px; border-radius:50%; background:var(--accent-soft); color:var(--accent-ink); font-size:11px; }
.answer-block :deep(.code-block .cb-head) {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--panel-line);
}
.answer-block :deep(.code-block .cb-lang) {
  font-family: var(--font-mono); font-size: 11px; color: var(--ink-faint);
}
.answer-block :deep(.code-block .cb-spacer) { flex: 1; }
.answer-block :deep(.code-block .cb-head button) {
  background: transparent; border: none; cursor: pointer;
  font-size: 11px; color: var(--ink-soft); padding: 2px 6px; border-radius: 4px;
}
.answer-block :deep(.code-block .cb-head button:hover) {
  background: color-mix(in oklab, var(--ink), transparent 92%); color: var(--ink);
}
.answer-block :deep(.code-block pre) {
  margin: 0; border: none; border-radius: 0;
  max-height: 320px; overflow: auto;
}
.answer-block :deep(.code-block.expanded pre) { max-height: none; }
.cursor {
  display: inline-block;
  width: 2px; height: 1.1em;
  background: var(--accent);
  animation: none;
}
</style>
