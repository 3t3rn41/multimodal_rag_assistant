import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createApp, effectScope, h, nextTick } from "vue";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { http } from "../src/api/http";
import { useAuthStore } from "../src/stores/auth";
import { useChatStore } from "../src/stores/chat";
import { useKbStore } from "../src/stores/kb";
import { useNavigationStore } from "../src/stores/navigation";
import App from "../src/App.vue";
import { installNavigationGuard } from "../src/router/guards";
import { useWorkspaceUpload } from "../src/composables/useWorkspaceUpload";
import { useKnowledgeFileSelection } from "../src/composables/useKnowledgeFileSelection";
import { sessionsForKb } from "../src/utils/workbench-navigation";
import { toast } from "../src/utils/toast";
import LoginView from "../src/views/auth/LoginView.vue";

vi.mock("../src/utils/toast", () => ({ toast: vi.fn(), toasts: [], removeToast: vi.fn() }));
const bases = [{ id: 7, name: "Library A" }, { id: 8, name: "Library B" }];
const sessions = [{ id: 10, kb_ids: [7] }, { id: 20, kb_ids: [8] }, { id: 30, kb_ids: [] }, { id: 40, kb_ids: [7, 8] }];
const page = { render: () => h("h1", "page") };
let pinia, auth, chat, kb, get, app, scope;
function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}
function makeRouter(login = page) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: "/", component: page }, { path: "/login", component: login },
    ...["/app/kbs", "/app/chat", "/app/settings"].map(path => ({ path, component: page, meta: { requiresAuth: true } })),
  ] });
  installNavigationGuard(router);
  return router;
}
beforeEach(() => {
  pinia = createPinia(); setActivePinia(pinia);
  auth = useAuthStore(); chat = useChatStore(); kb = useKbStore();
  auth.loaded = true; auth.user = { id: 1, email: "user@example.invalid" };
  get = vi.spyOn(http, "get").mockImplementation(async url => ({ data: url === "/knowledge" ? bases : sessions }));
  toast.mockClear();
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
});
afterEach(() => { app?.unmount(); app = null; scope?.stop(); scope = null; document.body.replaceChildren(); vi.unstubAllGlobals(); });

describe("knowledge-bound navigation", () => {
  it.each(["/app/chat", "/app/chat?session=10", "/app/chat?kb=0", "/app/chat?kb=-7", "/app/chat?kb=bad",
    "/app/chat?kb=7.5", "/app/chat?kb=9007199254740992", "/app/chat?kb=7&kb=8",
    "/app/chat?kb=7&session=bad", "/app/chat?kb=7&session", "/app/chat?kb=7&session=10&session=20"])(
    "returns to the library home before loading an invalid entry: %s", async address => {
      const router = makeRouter();
      chat.selectedKbId = 7; chat.currentSessionId = 10; chat.items = [{ type: "user", content: "stale" }];
      kb.currentKbId = 7; kb.docs = [{ file_id: 1 }];
      const stop = vi.spyOn(kb, "stopPolling");
      await router.push(address);
      expect(router.currentRoute.value.fullPath).toBe("/app/kbs");
      expect(get).not.toHaveBeenCalled();
      expect(chat.currentSessionId).toBeNull(); expect(chat.selectedKbId).toBeNull(); expect(chat.items).toEqual([]);
      expect(kb.currentKbId).toBeNull(); expect(kb.docs).toEqual([]); expect(stop).toHaveBeenCalled();
    },
  );
  it.each(["/app/chat?kb=999", "/app/chat?kb=7&session=999", "/app/chat?kb=7&session=20",
    "/app/chat?kb=7&session=30", "/app/chat?kb=7&session=40"])("rejects inaccessible resources and mismatched scopes: %s", async address => {
    const router = makeRouter(); await router.push(address);
    expect(router.currentRoute.value.path).toBe("/app/kbs");
    expect(chat.selectedKbId).toBeNull();
  });
  it.each(["/app/chat?kb=7", "/app/chat?kb=7&session=10"])("keeps a valid library entry and reuses its data: %s", async address => {
    const router = makeRouter(); await router.push(address);
    expect(router.currentRoute.value.fullPath).toBe(address);
    expect(chat.kbs).toEqual(bases); expect(kb.kbs).toEqual(bases); expect(chat.sessions).toEqual(sessions);
    expect(get.mock.calls.map(([url]) => url)).toEqual(["/knowledge", "/chat/history"]);
  });
  it("never exposes all histories without a selected library", () => {
    expect(sessionsForKb(sessions, null)).toEqual([]);
    expect(sessionsForKb(sessions, 7)).toEqual([sessions[0]]);
  });
  it("sends an unauthenticated deep link to login without preserving it", async () => {
    auth.user = null;
    const router = makeRouter(); await router.push("/app/chat?kb=7&session=10");
    expect(router.currentRoute.value.fullPath).toBe("/login"); expect(get).not.toHaveBeenCalled();
  });
  it("ignores a legacy next parameter for an authenticated account", async () => {
    const router = makeRouter(); await router.push("/login?next=/app/chat?kb=7%26session=10");
    expect(router.currentRoute.value.fullPath).toBe("/app/kbs"); expect(get).not.toHaveBeenCalled();
  });
  it.each(["/knowledge", "/chat/history"])("preserves the page and offers retry for a failed %s validation", async failedUrl => {
    const router = makeRouter(); await router.push("/app/kbs");
    const host = document.createElement("div"); document.body.appendChild(host);
    app = createApp(App); app.use(pinia); app.use(router); app.mount(host);
    chat.items = [{ type: "user", content: "keep current context" }];
    let failed = true;
    get.mockImplementation(async url => {
      if (failed && url === failedUrl) throw { response: { status: 503, data: { error: { message: "Service unavailable" } } } };
      return { data: url === "/knowledge" ? bases : sessions };
    });
    await router.push("/app/chat?kb=7&session=10"); await nextTick();
    expect(router.currentRoute.value.path).toBe("/app/kbs");
    expect(host.querySelector('[role="alert"]').textContent).toBe("Service unavailable");
    expect(useNavigationStore().target).toBe("/app/chat?kb=7&session=10");
    expect(chat.items[0].content).toBe("keep current context");
    expect(toast).not.toHaveBeenCalled(); expect(auth.user).not.toBeNull();
    failed = false; host.querySelector('.navigation-feedback .btn-primary').click();
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe("/app/chat?kb=7&session=10"));
    expect(useNavigationStore().target).toBeNull();
  });
  it.each([403, 404])("returns home when a validation resource is inaccessible (%s)", async status => {
    const router = makeRouter(); await router.push("/app/kbs");
    chat.selectedKbId = 7; chat.items = [{ type: "user", content: "old" }];
    get.mockRejectedValue({ response: { status } });
    await router.push("/app/chat?kb=7&session=10");
    expect(router.currentRoute.value.path).toBe("/app/kbs");
    expect(chat.items).toEqual([]); expect(chat.selectedKbId).toBeNull();
    expect(useNavigationStore().target).toBeNull();
  });
  it.each([{message: 'Network Error'}, {code: 'ECONNABORTED', message: 'timeout'}, {message: 'Request failed with status code 500', response: {status: 500}}])(
    "keeps network, timeout and server failures retryable", async error => {
      const router = makeRouter(); await router.push("/app/settings");
      get.mockRejectedValue(error); await router.push("/app/chat?kb=7");
      expect(router.currentRoute.value.path).toBe("/app/settings");
      expect(useNavigationStore().target).toBe("/app/chat?kb=7");
      expect(useNavigationStore().error).toContain("读取失败"); expect(auth.user).not.toBeNull();
    },
  );
  it("offers the same retry gate when account initialization fails", async () => {
    auth.loaded = false; auth.user = null;
    const router = makeRouter(); await router.push("/");
    const host = document.createElement("div"); document.body.appendChild(host);
    app = createApp(App); app.use(pinia); app.use(router); app.mount(host);
    let failed = true;
    get.mockImplementation(async url => {
      if (url === '/auth/me') {
        if (failed) throw {response: {status: 503}};
        return {data: {id: 1, email: 'user@example.invalid'}};
      }
      return {data: url === '/knowledge' ? bases : sessions};
    });
    await router.push('/app/chat?kb=7&session=10'); await nextTick();
    expect(router.currentRoute.value.path).toBe('/');
    expect(host.querySelector('[role="alert"]').textContent).toContain('登录状态读取失败');
    expect(useNavigationStore().target).toBe('/app/chat?kb=7&session=10');
    failed = false; host.querySelector('.navigation-feedback .btn-primary').click();
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/app/chat?kb=7&session=10'));
    expect(auth.user.id).toBe(1); expect(host.querySelector('.navigation-feedback')).toBeNull();
  });
  it("lets the user leave the failed validation for the library home", async () => {
    const router = makeRouter(); await router.push('/app/settings');
    const host = document.createElement('div'); document.body.appendChild(host);
    app = createApp(App); app.use(pinia); app.use(router); app.mount(host);
    get.mockRejectedValue({response: {status: 503}}); await router.push('/app/chat?kb=7'); await nextTick();
    host.querySelector('.navigation-feedback .btn-ghost').click();
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/app/kbs'));
    expect(useNavigationStore().target).toBeNull();
  });
  it("expires the account on a validation 401", async () => {
    get.mockRejectedValue({ response: { status: 401 } });
    const router = makeRouter(); await router.push("/app/chat?kb=7");
    expect(router.currentRoute.value.fullPath).toBe("/login"); expect(auth.user).toBeNull();
  });
  it("does not publish an older validation after a newer navigation", async () => {
    const first = deferred(); let signal;
    get.mockImplementation((url, config) => {
      if (url === "/knowledge" && !signal) { signal = config.signal; return first.promise; }
      return Promise.resolve({ data: url === "/knowledge" ? [{ id: 8, name: "New result" }] : sessions });
    });
    const router = makeRouter(), old = router.push("/app/chat?kb=7");
    await vi.waitFor(() => expect(signal).toBeDefined());
    await router.push("/app/chat?kb=8");
    first.resolve({ data: bases }); await old;
    expect(signal.aborted).toBe(true); expect(chat.kbs).toEqual([{ id: 8, name: "New result" }]);
    expect(router.currentRoute.value.fullPath).toBe("/app/chat?kb=8"); expect(toast).not.toHaveBeenCalled();
  });
  it("cancels validation and discards its data when the account changes", async () => {
    const pending = deferred(); let signal;
    get.mockImplementation((url, config) => {
      signal = config.signal; return url === "/knowledge" ? pending.promise : Promise.resolve({ data: sessions });
    });
    const router = makeRouter(), navigation = router.push("/app/chat?kb=7");
    await vi.waitFor(() => expect(signal).toBeDefined());
    auth.clearAccount(); auth.user = { id: 2, email: "new@example.invalid" };
    expect(signal.aborted).toBe(true); pending.resolve({ data: bases }); await navigation;
    expect(router.currentRoute.value.path).toBe("/app/kbs"); expect(chat.kbs).toEqual([]); expect(kb.kbs).toEqual([]);
  });
  it("blocks leaving an answer while allowing its new session URL", async () => {
    const router = makeRouter(); await router.push("/app/chat?kb=7");
    chat.selectedKbId = 7; chat.currentSessionId = 99; chat.streaming = true; get.mockClear();
    await router.replace("/app/chat?kb=7&session=99");
    expect(router.currentRoute.value.fullPath).toBe("/app/chat?kb=7&session=99");
    await router.push("/app/kbs");
    expect(router.currentRoute.value.path).toBe("/app/chat"); expect(get).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith(expect.stringContaining("回答正在生成"), "info");
  });
  it("preserves the upload navigation lock", async () => {
    const router = makeRouter(); await router.push("/app/chat?kb=7");
    kb.currentKbId = 7; const pending = deferred();
    vi.spyOn(kb, "uploadFiles").mockReturnValue(pending.promise);
    scope = effectScope(); const uploads = scope.run(() => useWorkspaceUpload());
    const uploading = uploads.upload([new File(["text"], "file.txt")], 7);
    await router.push("/app/kbs"); expect(router.currentRoute.value.path).toBe("/app/chat");
    pending.resolve([]); await uploading;
    await router.push("/app/kbs"); expect(router.currentRoute.value.path).toBe("/app/kbs");
  });
  it("preserves the file selection navigation lock", async () => {
    const router = makeRouter(); await router.push("/app/chat?kb=7");
    kb.currentKbId = 7; kb.docs = [{ file_id: 1, enabled: true }]; const pending = deferred();
    vi.spyOn(kb, "setDocEnabled").mockReturnValue(pending.promise);
    scope = effectScope(); const selection = scope.run(() => useKnowledgeFileSelection());
    const saving = selection.setEnabled(7, 1, false);
    await router.push("/app/kbs"); expect(router.currentRoute.value.path).toBe("/app/chat");
    pending.resolve(); await saving;
    await router.push("/app/kbs"); expect(router.currentRoute.value.path).toBe("/app/kbs");
  });
});

describe("login landing page", () => {
  it.each(["/login", "/login?next=/app/chat?kb=999%26session=999", "/login?next=/app/settings", "/login?next=https://example.invalid"])(
    "replaces the login entry with the library home: %s", async address => {
      auth.user = null;
      const post = vi.spyOn(http, "post").mockResolvedValue({ data: { id: 1, email: "user@example.invalid" } });
      const router = makeRouter(LoginView), host = document.createElement("div"); document.body.appendChild(host);
      app = createApp({ render: () => h(RouterView) }); app.use(pinia); app.use(router);
      await router.push(address); await router.isReady(); app.mount(host);
      for (const [id, value] of [["email", "user@example.invalid"], ["password", "password1"]]) {
        const input = host.querySelector("#" + id); input.value = value; input.dispatchEvent(new Event("input", { bubbles: true }));
      }
      await nextTick(); host.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe("/app/kbs"));
      expect(post).toHaveBeenCalledWith("/auth/login", { email: "user@example.invalid", password: "password1" });
      expect(get).not.toHaveBeenCalled();
      await router.back(); await nextTick(); expect(router.currentRoute.value.path).not.toBe("/login");
    },
  );
  it("keeps a failed login on the login form", async () => {
    auth.user = null;
    vi.spyOn(http, "post").mockRejectedValue({ response: { status: 401, data: { error: { message: "邮箱或密码错误" } } } });
    const router = makeRouter(LoginView), host = document.createElement("div"); document.body.appendChild(host);
    app = createApp({ render: () => h(RouterView) }); app.use(pinia); app.use(router);
    await router.push("/login"); await router.isReady(); app.mount(host);
    for (const [id, value] of [["email", "user@example.invalid"], ["password", "password1"]]) {
      const input = host.querySelector("#" + id); input.value = value; input.dispatchEvent(new Event("input", { bubbles: true }));
    }
    host.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await vi.waitFor(() => expect(host.textContent).toContain("邮箱或密码错误"));
    expect(router.currentRoute.value.path).toBe("/login"); expect(auth.user).toBeNull();
  });
});
