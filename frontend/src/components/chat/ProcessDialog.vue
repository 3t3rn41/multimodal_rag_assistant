<template>
 <Teleport to="body">
  <div v-if="open" class="pd-overlay" @click.self="emit('close')">
   <section ref="dialogEl" class="pd-card" role="dialog" aria-modal="true" aria-label="回答过程" tabindex="-1">
    <header class="pd-head"><Icon name="graph"/>回答过程<div class="pd-actions"><button class="btn btn-ghost btn-sm" @click="exportMd">导出</button><button class="btn-icon" title="关闭" aria-label="关闭回答过程" @click="emit('close')"><Icon name="x"/></button></div></header>
    <nav class="pd-tabs" aria-label="回答过程页签"><button v-for="item in tabs" :key="item.key" class="pd-tab" :class="{active:tab===item.key}" @click="tab=item.key"><Icon :name="item.icon"/>{{item.label}}<span class="pd-tab-count">{{item.count}}</span></button></nav>
    <div ref="bodyEl" class="pd-body">
     <div v-if="tab==='process'" class="pd-pane"><ol v-if="steps.length" class="pd-timeline"><li v-for="step in steps" :key="step.stage" class="pd-step" :class="step.status"><Icon :name="step.status==='running'?'loader':step.status==='error'?'alert':step.status==='aborted'?'x':'check'"/><div class="pd-step-txt"><span class="pd-step-label">{{step.label}}</span><span class="pd-step-detail">{{step.detail}}</span></div></li></ol><p v-else class="pd-empty">这条历史回答没有记录处理步骤。</p></div>
     <div v-else-if="tab==='citations'" class="pd-pane"><button v-for="entry in citations" :key="entry.citation.chunk_id" class="cite-card btn btn-ghost" @click="emit('show-citation',entry.citation)"><span class="idx">{{entry.number}}</span><span>{{entry.citation.doc_title||entry.citation.file_name||'资料'}}<span v-if="entry.citation.page"> · 第 {{entry.citation.page}} 页</span></span></button><p v-if="!citations.length" class="pd-empty">没有引用来源。</p></div>
     <div v-else class="pd-pane"><dl class="pd-stats"><div v-for="row in rows" :key="row.label" class="pd-stat"><dt>{{row.label}}</dt><dd>{{row.value}}</dd></div></dl></div>
    </div>
   </section>
  </div>
 </Teleport>
</template>
<script setup>
import {computed,ref,watch,nextTick} from 'vue';
import Icon from '../common/Icon.vue';
import {downloadText} from '../../utils/download';
import {statsRows} from '../../utils/process-summary';
import {numberedCitations} from '../../utils/citation-label';
import {useOverlayFocus} from '../../composables/useOverlayFocus';
const props=defineProps({open:{type:Boolean,default:false},processItems:{type:Array,default:()=>[]},answer:{type:Object,default:()=>({})}});
const emit=defineEmits(['close','show-citation']);
const tab=ref('process'),dialogEl=ref(null),bodyEl=ref(null);
const labels={retrieval:'检索资料',rerank:'重排候选',generation:'生成回答',citations:'校验引用'};
const steps=computed(()=>props.processItems.filter(i=>i.type==='stage'&&labels[i.stage]).map(i=>({...i,label:labels[i.stage],detail:[i.count!=null?`${i.count} 条`:null,i.duration_ms!=null?`${(i.duration_ms/1000).toFixed(2)} 秒`:null,i.status==='running'?'进行中':i.status==='error'?'未完成':i.status==='aborted'?'已停止':null].filter(Boolean).join(' · ')})));
const citations=computed(()=>numberedCitations(props.answer.content||'',props.answer.citations||[])),rows=computed(()=>statsRows(props.answer));
const tabs=computed(()=>[{key:'process',label:'处理过程',icon:'graph',count:steps.value.length},{key:'citations',label:'引用来源',icon:'citation',count:citations.value.length},{key:'stats',label:'统计',icon:'graph',count:rows.value.length}]);
useOverlayFocus(computed(()=>props.open),dialogEl,()=>emit('close'));
watch(()=>props.open,()=>{if(!props.open)return;tab.value='process';nextTick(()=>{if(bodyEl.value)bodyEl.value.scrollTop=0})},{immediate:true});
function exportMd(){const lines=['# 回答过程','',...steps.value.map(s=>`- ${s.label}：${s.detail||s.status}`),'','## 引用来源',...citations.value.map(({citation:c,number})=>`- ${number}. ${c.doc_title||c.file_name||'资料'} [${c.chunk_id}]`),'','## 统计',...rows.value.map(r=>`- ${r.label}：${r.value}`)];downloadText(lines.join('\n'),`process-${Date.now()}.md`)}
</script>
<style scoped>
.pd-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  /* rgba 兜底在前：不支持 color-mix 的浏览器仍能渲染遮罩 */
  background: rgba(0, 0, 0, 0.55);
  background: color-mix(in oklab, #000, transparent 55%);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  /* 极矮视口下兜底可滚，避免内容滞留在视口外 */
  overflow-y: auto;
}
.pd-card {
  width: 100%;
  max-width: 720px;
  max-height: 82vh;
  /* flex 项的自动最小高度=内容高度，会击穿 max-height（内容较长时
     卡片长到几千 px、顶部冲出视口盖住导航栏）。显式 min-height:0 放行上限 */
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 14px;
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.25);
}
.pd-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
  font-weight: 600;
}
.pd-head svg { width: 15px; height: 15px; color: var(--accent); }
.pd-actions { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.pd-tabs {
  display: flex;
  gap: 2px;
  border-bottom: 1px solid var(--line);
  padding: 0 10px;
  overflow-x: auto;
}
.pd-tab {
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 10px 14px;
  color: var(--ink-mute);
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  background: none;
  transition: all var(--t-fast) var(--ease);
  display: flex;
  align-items: center;
  gap: 7px;
  cursor: pointer;
  white-space: nowrap;
}
.pd-tab svg { width: 13px; height: 13px; }
.pd-tab:hover { color: var(--ink); }
.pd-tab.active { color: var(--accent-ink); border-bottom-color: var(--accent); font-weight: 600; }
.pd-tab-count {
  min-width: 16px;
  height: 16px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--line-soft);
  color: var(--ink-soft);
  font-family: var(--font-mono);
  font-size: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.pd-tab.active .pd-tab-count { background: var(--accent-soft); color: var(--accent-ink); }
.pd-body {
  padding: 0 16px 18px;
  overflow-y: auto;
  /* 同理：列向 flex 子项不设 min-height:0 就无法收缩到容器内，
     较长的处理记录会把内容顶出卡片 */
  min-height: 0;
}
.pd-pane { display: grid; gap: 16px; padding-top: 14px; }
.pd-timeline { list-style: none; margin: 0; padding: 0; display: grid; gap: 0; }
.pd-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 0;
  position: relative;
}
.pd-step:not(:last-child)::after {
  content: "";
  position: absolute;
  left: 7px;
  top: 26px;
  bottom: -6px;
  width: 1px;
  background: var(--line);
}
.pd-step > svg {
  width: 15px;
  height: 15px;
  flex: none;
  color: var(--ink-soft);
  margin-top: 1px;
  background: var(--surface);
  z-index: 1;
}
.pd-step.running > svg { color: var(--accent); }
.pd-step-txt { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.pd-step-label { font-size: 12.5px; font-weight: 600; }
.pd-step-detail { font-size: 11.5px; color: var(--ink-soft); line-height: 1.45; }
.pd-stats { margin: 0; display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.pd-stat {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--line-soft);
  border-radius: 8px;
}
.pd-stat dt { font-size: 11.5px; color: var(--ink-soft); }
.pd-stat dd { margin: 0; font-size: 12px; font-family: var(--font-mono); }
.pd-empty {
  padding: 18px 14px;
  border: 1px dashed var(--line);
  border-radius: 8px;
  text-align: center;
  font-size: 12px;
  color: var(--ink-faint);
}

</style>
