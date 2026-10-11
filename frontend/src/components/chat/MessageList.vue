<template>
  <div class="chat-messages" ref="scroller" @scroll="onScroll">
    <div class="chat-messages-inner">
      <template v-if="loading">
        <div v-for="i in 3" :key="i" class="msg-skeleton">
          <div class="skeleton sk-avatar" />
          <div class="sk-lines">
            <div class="skeleton sk-line" style="width:72%" />
            <div class="skeleton sk-line" style="width:48%" />
          </div>
        </div>
      </template>

      <template v-else-if="items.length === 0">
        <slot name="empty" />
      </template>

      <template v-else>
        <template v-for="row in visualRows" :key="row.key">
          <!-- 连续过程条目：折叠为紧凑摘要行，点击在弹窗中查看详情 -->
          <div v-if="row.kind === 'chunk'" class="process-chunk">
            <div class="process-rail"><span class="pr-dot" /></div>
            <div class="process-stack">
              <button
                type="button"
                class="process-summary"
                :aria-label="'查看回答过程：' + chunkSummary(row)"
                @click="openChunk(row)"
              >
                <Icon name="graph" />
                <span class="ps-text">{{ chunkSummary(row) }}</span>
                <span v-if="chunkRunning(row)" class="badge accent pulse"><span class="bdot" />运行中</span>
                <Icon name="chevronRight" class="ps-chevron" />
              </button>
            </div>
          </div>

          <!-- 单条消息：用户 / 答案 / 错误 -->
          <ErrorBoundary v-else>
            <div class="msg" :class="row.item.type">
              <template v-if="row.item.type === 'user'">
                <div class="msg-avatar"><Icon name="user" /></div>
                <div class="msg-body">
                  <div class="msg-meta"><span>你</span><span v-if="row.item.created_time">{{ fmtTime(row.item.created_time) }}</span></div>
                  <div class="msg-text">{{ row.item.content }}</div>
                </div>
              </template>

              <template v-else-if="row.item.type === 'error'">
                <div class="msg-avatar"><Icon name="alert" /></div>
                <div class="msg-body">
                  <div class="error-item"><Icon name="alert" /><span>{{ row.item.message }}</span>
                    <button v-if="row.item.retryable" class="btn btn-ghost btn-sm" style="margin-left:auto" :disabled="busy" @click="emit('retry')">
                      <Icon name="refresh" />重试
                    </button>
                  </div>
                </div>
              </template>

              <template v-else-if="row.item.type === 'answer'">
                <div class="msg-avatar"><Icon name="spark" style="color:var(--accent)" /></div>
                <div class="msg-body">
                  <AnswerBlock
                    :item="row.item"
                    :can-regenerate="!busy && row.gidx === lastAnswerIdx"
                    @regenerate="emit('regenerate')"
                    @feedback="emit('feedback', $event)"
                    @show-process="() => openAnswerProcess(row)"
                    @show-citation="(payload) => openCitation(payload.chunkId, payload.citation)"
                  />
                </div>
              </template>
            </div>
          </ErrorBoundary>
        </template>
      </template>
    </div>

    <!-- 回答过程弹窗：摘要行与答案「查看过程」共用 -->
    <ProcessDialog
      :open="processDialog.open"
      :process-items="processDialog.items"
      :answer="processDialog.answer"
      @close="processDialog.open = false"
      @show-citation="(cite) => openCitation(cite.chunk_id, cite)"
    />
    <CitationDialog :open="citationDialog.open" :chunk-id="citationDialog.chunkId" :citation="citationDialog.citation"
      @close="citationDialog.open = false" />
  </div>
</template>

<script setup>
import { computed, ref, watch, nextTick, onMounted } from "vue";
import Icon from "../common/Icon.vue";
import AnswerBlock from "./AnswerBlock.vue";
import ProcessDialog from "./ProcessDialog.vue";
import CitationDialog from "./CitationDialog.vue";
import ErrorBoundary from "../common/ErrorBoundary.vue";
import { buildProcessRuns } from "../../utils/process-summary";
import { fmtTime } from "../../utils/format";

const props = defineProps({
  items: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  turn: { type: Number, default: 0 },
  sourcePanel: { type: Boolean, default: false },
});
const emit = defineEmits(["retry", "regenerate", "feedback", "show-citation"]);

const scroller = ref(null);
const shouldStick = ref(true);

const grouped = computed(() => props.items.filter(i => ["user","answer","error","stage"].includes(i.type)));
const processRuns = computed(() => buildProcessRuns(grouped.value));

// 过程类型：连续出现时合并为一段摘要
const PROCESS_TYPES = new Set(["stage"]);

const visualRows = computed(() => {
  const rows = [];
  let buf = [];
  grouped.value.forEach((item, idx) => {
    if (PROCESS_TYPES.has(item.type)) {
      buf.push(item);
    } else {
      if (buf.length) {
        rows.push({ kind: "chunk", items: buf, key: "chunk_" + buf[0]._key });
        buf = [];
      }
      rows.push({
        kind: "single",
        item,
        gidx: idx,
        key: item._key != null ? item._key : "row_" + idx,
      });
    }
  });
  if (buf.length) rows.push({ kind: "chunk", items: buf, key: "chunk_" + buf[0]._key });

  // 把摘要段关联到紧随其后的答案，弹窗可展示该答案的引用与统计
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    if (r.kind !== "chunk") continue;
    for (let j = i + 1; j < rows.length; j++) {
      if (rows[j].kind === "single" && rows[j].item.type === "answer") {
        r.answerGidx = rows[j].gidx;
        break;
      }
    }
  }
  return rows;
});

const lastAnswerIdx = computed(() => {
  let last = -1;
  grouped.value.forEach((it, idx) => {
    if (it.type === "answer") last = idx;
  });
  return last;
});

// 统一的过程弹窗状态
const processDialog = ref({ open: false, items: [], answer: {} });
const citationDialog = ref({ open: false, chunkId: null, citation: null });

function openCitation(chunkId, citation) {
  processDialog.value.open = false;
  if (props.sourcePanel) {
    emit("show-citation", { chunkId, citation: citation || null });
    return;
  }
  citationDialog.value = { open: true, chunkId, citation: citation || null };
}

function openProcess(items, answer) {
  processDialog.value = {
    open: true,
    items,
    answer: answer || {},
  };
}

function openChunk(row) {
  const items = row.answerGidx != null ? processRuns.value.get(row.answerGidx) || row.items : row.items;
  const answer = row.answerGidx != null ? grouped.value[row.answerGidx] : {};
  openProcess(items, answer);
}

function openAnswerProcess(row) {
  openProcess(processRuns.value.get(row.gidx) || [], row.item);
}

function chunkSummary(row) {
  const parts=row.items.map(i=>i.label||({retrieval:"检索资料",rerank:"重排候选",generation:"生成回答",citations:"校验引用"}[i.stage])).filter(Boolean);
  const count=row.answerGidx!=null ? grouped.value[row.answerGidx]?.citations?.length : 0;
  if(count) parts.push(`引用 ${count} 条`);
  return parts.length ? parts.join(" · ") : "回答过程";
}
function chunkRunning(row) {return row.items.some(i=>i.status==="running")}

function onScroll() {
  const el = scroller.value;
  if (!el) return;
  shouldStick.value = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
}

function scrollToBottom() {
  const el = scroller.value;
  if (el && shouldStick.value) el.scrollTop = el.scrollHeight;
}

/** 发送新消息时强制回到底部（无视用户是否上翻），并平滑滚动。 */
function forceScrollToBottom() {
  const el = scroller.value;
  if (!el) return;
  shouldStick.value = true;
  const reduced = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  el.scrollTo({ top: el.scrollHeight, behavior: reduced ? "auto" : "smooth" });
}

watch(
  () => props.items.map((x) => `${x.type}:${x.content?.length ?? 0}:${x.status ?? ""}`).join("|"),
  () => nextTick(scrollToBottom),
  { deep: false },
);

watch(() => props.turn, () => nextTick(forceScrollToBottom));

onMounted(() => nextTick(scrollToBottom));

</script>

<style scoped>
.process-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  background: color-mix(in oklab, var(--bg), white 40%);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  color: var(--ink-soft);
  text-align: left;
  transition: border-color var(--t-fast) var(--ease), background var(--t-fast) var(--ease);
}
.process-summary:hover {
  border-color: var(--line);
  background: color-mix(in oklab, var(--accent), transparent 94%);
}
.process-summary > svg:first-child {
  width: 13px;
  height: 13px;
  flex: none;
  color: var(--accent);
}
.process-summary .ps-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.process-summary .ps-chevron {
  margin-left: auto;
  width: 13px;
  height: 13px;
  flex: none;
  color: var(--ink-faint);
  transition: transform var(--t-fast) var(--ease);
}
.process-summary:hover .ps-chevron { transform: translateX(2px); }
.process-summary .badge { flex: none; }
</style>
