import { reactive } from "vue";

/** 全局轻提示：任何组件调用 toast(msg, type) 即可弹出。 */
export const toasts = reactive([]);

let seq = 0;

export function toast(message, type = "info", duration = 2600) {
  const id = ++seq;
  toasts.push({ id, message, type });
  setTimeout(() => removeToast(id), duration);
}

export function removeToast(id) {
  const i = toasts.findIndex((t) => t.id === id);
  if (i >= 0) toasts.splice(i, 1);
}