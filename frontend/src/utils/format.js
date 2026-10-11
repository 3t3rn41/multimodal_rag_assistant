/** 时间/数字/状态格式化工具。 */

export function fmtPercent(value) {
  const number = Number(value);
  return `${(Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : 0).toFixed(2)}%`;
}

export function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const now = Date.now();
  const diff = now - d.getTime();
  const pad = (n) => String(n).padStart(2, "0");
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000 && new Date(now).getDate() === d.getDate()) {
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} 天前`;
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function fmtBytes(n) {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export function fmtNumber(n) {
  if (n == null) return "—";
  return n.toLocaleString("zh-CN");
}

/** 解析状态 → 徽章文案/类别（queue/parsing/done/failed）。
 *  后端 ParseStatus 枚举为 done；状态只使用后端当前枚举。 */
export function parseStatusMeta(status) {
  const map = {
    pending: { text: "排队中", cls: "warn" },
    parsing: { text: "解析中", cls: "accent pulse" },
    done: { text: "已完成", cls: "ok" },
    failed: { text: "失败", cls: "err" },
  };
  return map[status] || { text: status || "未知", cls: "" };
}

/** 是否已完成解析（后端 done）。 */
export function isParsedDone(status) {
  return status === "done";
}
