import { toast } from "./toast";

/** 下载 Markdown 文本并给出成功反馈（应用内浏览器也能看到结果）。 */
export function downloadText(text, filename) {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
  toast(`已导出：${filename}`, "success");
}
