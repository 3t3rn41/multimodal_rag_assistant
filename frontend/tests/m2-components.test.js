import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createApp, h, nextTick } from "vue";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { http } from "../src/api/http";
import { useKbStore } from "../src/stores/kb";
import SettingsView from "../src/views/settings/SettingsView.vue";
import TaskProgress from "../src/components/common/TaskProgress.vue";
import KbDocsTab from "../src/views/kb/KbDocsTab.vue";

let apps;
async function flush() { await Promise.resolve(); await Promise.resolve(); await nextTick(); }
async function mount(component, props = {}, options = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const app = createApp({ render: () => h(options.router ? RouterView : component, props) });
  const pinia = createPinia();
  app.use(pinia);
  options.setupPinia?.(pinia);
  if (options.router) {
    app.use(options.router);
    await options.router.push("/");
    await options.router.isReady();
  }
  apps.push(app);
  app.mount(container);
  await flush();
  return container;
}
beforeEach(() => {
  apps = []; setActivePinia(createPinia());
});
afterEach(() => { apps.forEach(app => app.unmount()); document.body.replaceChildren(); vi.useRealTimers(); });

describe("system model status", () => {
  function config(configured = true) {
    return { readonly: true, configuration_source: "environment", configured,
      llm_key_configured: configured, llm_model: "environment-model", llm_base_url: "https://example.invalid/v1" };
  }
  it("provides read-only configuration and tests the current model", async () => {
    vi.spyOn(http, "get").mockImplementation(async url => ({ data: url === "/users/me/models" ? config() : { online: true } }));
    const post = vi.spyOn(http, "post").mockResolvedValue({ data: { message: "connection passed" } });
    const container = await mount(SettingsView);
    expect(container.textContent).toContain("environment-model");
    expect(container.textContent).toContain("只读");
    expect(container.querySelector("input")).toBeNull();
    expect(container.querySelector('[type="submit"]')).toBeNull();
    [...container.querySelectorAll("button")].find(button => button.textContent.includes("测试连接")).click();
    await flush();
    expect(post).toHaveBeenCalledWith("/users/me/models/test-llm");
    expect(container.textContent).toContain("connection passed");
  });

  it("disables connection tests when the model is missing", async () => {
    vi.spyOn(http, "get").mockImplementation(async url => ({ data: url === "/users/me/models" ? config(false) : { online: true } }));
    const container = await mount(SettingsView);
    expect([...container.querySelectorAll("button")].find(button => button.textContent.includes("测试连接")).disabled).toBe(true);
    expect(container.textContent).toContain("尚未就绪");
  });
});

describe("durable task details", () => {
  it("shows retry stage, elapsed time, zero counts and the exact indexing report", async () => {
    const container = await mount(TaskProgress, { meta: { task_id: "task", failed_stage: "EMBEDDING", retry_count: 2,
      stage_metrics: { EMBEDDING: { status: "RETRYING", elapsed_ms: 2500, completed: 0, total: 1 } },
      indexing_report: { total: 3, skipped: 3, embedded: 0, upserted: 0 } } });
    expect(container.textContent).toContain("已重试 2 次");
    expect(container.textContent).toContain("向量化 · 重试中");
    expect(container.textContent).toContain("2.5 秒 · 0/1");
    expect(container.textContent).toContain("跳过 3 · 向量化 0 · 入库 0");
  });

  it("does not invent statistics for legacy tasks", async () => {
    const container = await mount(TaskProgress, { meta: { task_id: "old-task" } });
    expect(container.textContent).toContain("暂无阶段统计");
    expect(container.querySelector(".indexing-report")).toBeNull();
  });
});

describe("knowledge file actions", () => {
  it("shows one trash action, binds its knowledge base and never loads cleanup records", async () => {
    let removed = false;
    const file = { file_id: 7, file_name: "example.pdf", file_type: "pdf", enabled: true, status: "done", meta: {} };
    const get = vi.spyOn(http, "get").mockImplementation(async url => ({ data:
      removed ? [] : [file],
    }));
    const del = vi.spyOn(http, "delete").mockImplementation(async () => {
      removed = true;
      return {status: 204};
    });
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/", component: KbDocsTab }] });
    const container = await mount(KbDocsTab, {}, { router, setupPinia: pinia => { useKbStore(pinia).currentKbId = 1; } });
    expect(container.textContent).not.toContain("资源清理记录");
    expect([...container.querySelectorAll("button")].some(button => button.textContent === "删除文件")).toBe(false);
    const trigger = container.querySelector('button[title="移除文件"]');
    trigger.click();
    await flush();
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog.textContent).toContain("若其他知识库未使用该文件");
    expect(del).not.toHaveBeenCalled();
    useKbStore().currentKbId = 2;
    [...dialog.querySelectorAll("button")].find(button => button.textContent === "移除").click();
    await vi.waitFor(() => expect(del).toHaveBeenCalledWith("/knowledge/1/files/7"));
    await vi.waitFor(() => expect(container.querySelector(".document-name")).toBeNull());
    expect(get.mock.calls.some(([url]) => url === "/cleanup-jobs")).toBe(false);
  });

  it("formats processing percentages without rounding the progress bar value", async () => {
    const progress = 53.61702127659574;
    vi.spyOn(http, "get").mockResolvedValue({data: [{file_id: 7, file_name: "progress.pdf", file_type: "pdf", status: "parsing",
      enabled: true, meta: {task_status: "PROCESSING", task_stage: "EMBEDDING", task_progress: progress}}]});
    const router = createRouter({history: createMemoryHistory(), routes: [{path: "/", component: KbDocsTab}]});
    const container = await mount(KbDocsTab, {}, {router, setupPinia: pinia => {useKbStore(pinia).currentKbId = 1;}});
    expect(container.querySelector(".document-progress span").textContent).toBe("53.62%");
    expect(container.querySelector('[role="progressbar"]').getAttribute("aria-valuenow")).toBe(String(progress));
  });
});
