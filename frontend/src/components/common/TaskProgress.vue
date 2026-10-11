<template>
 <details v-if="meta?.task_id" class="task-details">
  <summary>处理详情<span v-if="meta.retry_count"> · 已重试 {{ meta.retry_count }} 次</span></summary>
  <ol class="task-timeline"><li v-for="stage in stages" :key="stage.key" :class="{'task-stage-failed':meta.failed_stage===stage.key}">
   <span>{{ stage.label }} · {{ statusLabel(metrics[stage.key]?.status) }}</span>
   <small v-if="metrics[stage.key]">{{ duration(metrics[stage.key]) }} · {{ count(metrics[stage.key]?.completed) }}/{{ count(metrics[stage.key]?.total) }}</small>
  </li></ol>
  <p v-if="!meta.stage_metrics">暂无阶段统计</p>
  <p v-if="meta.failed_stage">最近失败阶段：{{ failedStageLabel }}</p>
  <p v-if="meta.task_started_at">开始：{{ fmtTime(meta.task_started_at) }}</p>
  <p v-if="meta.task_completed_at">结束：{{ fmtTime(meta.task_completed_at) }}</p>
  <p v-if="meta.indexing_report" class="indexing-report">总数 {{ meta.indexing_report.total }} · 跳过 {{ meta.indexing_report.skipped }} · 向量化 {{ meta.indexing_report.embedded }} · 入库 {{ meta.indexing_report.upserted }}</p>
 </details>
</template>
<script setup lang="ts">
import { computed } from 'vue';
import { fmtTime } from '../../utils/format';
import type { DocumentMeta, StageMetric } from '../../types/workbench';

const props = defineProps<{ meta?: DocumentMeta | null }>();
const stages = [
 { key: 'PARSING', label: '解析文件' },
 { key: 'SLICING', label: '生成切片' },
 { key: 'EMBEDDING', label: '向量化' },
 { key: 'INDEXING', label: '向量入库' },
];
const metrics = computed(() => props.meta?.stage_metrics || {});
const failedStageLabel = computed(() => stages.find(stage => stage.key === props.meta?.failed_stage)?.label || props.meta?.failed_stage);
const labels: Record<string, string> = {
 PROCESSING: '处理中', SUCCESS: '完成', FAILED: '失败', RETRYING: '重试中', PENDING: '等待',
};
function statusLabel(value?: string) {
 return value ? labels[value] || value : '未开始';
}
function count(value?: number | null) {
 return typeof value === 'number' ? value : '—';
}
function duration(metric: StageMetric) {
 let elapsed = metric.elapsed_ms;
 if (typeof elapsed !== 'number') return '耗时未知';
 if (metric.active_since) {
  const started = Date.parse(metric.active_since);
  if (Number.isFinite(started)) elapsed += Math.max(0, Date.now() - started);
 }
 return (elapsed / 1000).toFixed(1) + ' 秒';
}
</script>
<style scoped>
.task-details{margin-top:8px;font-size:11px;line-height:1.7;color:var(--ink-mute);min-width:190px}.task-details summary{cursor:pointer}.task-timeline{padding:8px 0 0 16px;margin:0}.task-timeline li{padding:3px 0}.task-timeline small{display:block;font-size:10px}.task-stage-failed{color:var(--err)}.task-details p{margin:6px 0 0}.indexing-report{max-width:240px;white-space:normal}
</style>
