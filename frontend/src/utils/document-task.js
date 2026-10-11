import { parseStatusMeta, isParsedDone } from "./format";

const STAGES = {
  PARSING: "解析文件",
  SLICING: "生成切片",
  EMBEDDING: "向量化",
  INDEXING: "向量入库",
  RETRYING: "服务重试中",
};

/** 只有真实后台任务才自动轮询，后台任务根据持久化状态轮询。 */
export function isDocumentProcessing(doc) {
  const task = doc?.meta?.task_status;
  if (task === "SUCCESS" || task === "FAILED") return false;
  return ["PENDING", "PROCESSING"].includes(task) ||
    ["pending", "parsing"].includes(doc?.status);
}

export function documentTaskView(doc = {}) {
  const meta = doc.meta || {};
  const active = isDocumentProcessing(doc);
  const failed = meta.task_status === "FAILED" || doc.status === "failed";
  const requiresReindex = meta.requires_reindex === true;
  const success = !requiresReindex && (meta.task_status === "SUCCESS" || isParsedDone(doc.status));
  const rawProgress = Number(meta.task_progress);
  const progress = Number.isFinite(rawProgress) ? Math.max(0, Math.min(100, rawProgress)) : 0;
  let state = parseStatusMeta(doc.status);
  if (requiresReindex) state = { text: "需重新处理", cls: "warn" };
  else if (failed) state = { text: "处理失败", cls: "err" };
  else if (success) state = { text: "已完成", cls: "ok" };
  else if (active) state = {
    text: meta.task_stage === "RETRYING" ? STAGES.RETRYING : meta.task_status === "PENDING" || doc.status === "pending"
      ? "排队中" : STAGES[meta.task_stage] || "处理中",
    cls: "accent pulse",
  };
  return {
    ...state,
    active,
    failed,
    requiresReindex,
    progress: success ? 100 : progress,
    error: requiresReindex ? "此文件使用旧向量模型，请重新处理以接入系统 Jina 检索。" : failed ? meta.error || meta.task_error || "处理失败，请查看后台日志后重试。" : null,
    canReparse: !active && (requiresReindex || failed || success || doc.status === "pending"),
    reparseLabel: requiresReindex ? "重新处理" : failed ? "重试处理" : "重新解析",
    stage: STAGES[meta.task_stage] || null,
  };
}
