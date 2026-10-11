import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createApp, h, nextTick } from "vue";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { http } from "../src/api/http";
import { useAuthStore } from "../src/stores/auth";
import { useChatStore } from "../src/stores/chat";
import { useKbStore } from "../src/stores/kb";
import { installNavigationGuard } from "../src/router/guards";
import WorkspaceLayout from "../src/views/workspace/WorkspaceLayout.vue";
import ChatView from "../src/views/chat/ChatView.vue";

vi.mock("../src/utils/toast", () => ({ toast: vi.fn() }));
const home = { render: () => h("h1", "知识库首页") };
const bases = [{ id: 7, name: "Library A" }, { id: 8, name: "Library B" }];
const sessions = [{ id: 10, title: "History A", kb_ids: [7] }, { id: 20, title: "History B", kb_ids: [7] }, { id: 30, kb_ids: [8] }, { id: 40, kb_ids: [] }];
let pinia, auth, chat, kb, get, app, host, deleted;
function sourceBody() {const frame=host.querySelector('.sources-aside iframe');return frame ? new DOMParser().parseFromString(frame.getAttribute('srcdoc'),'text/html').body.textContent : null;}
function deferred() { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; }
function response(url) {
  if (url === "/knowledge") return bases;
  if (url === "/chat/history") return sessions.filter(item => item.id !== deleted);
  if (url === "/users/me/models") return { configured: true, readonly: true };
  if (/^\/knowledge\/\d+\/files$/.test(url)) return [];
  if (url.endsWith("/trace")) return { turns: [] };
  if (url.endsWith("/messages")) return [
    { id: 1, role: "user", content: "question " + url.split("/")[3] },
    { id: 2, role: "assistant", content: "answer", refs: [{ chunk_id: "source", doc_title: "original.txt" }] },
  ];
  if (url === '/chunks/source/source') return {chunk_id:'source',file_id:'1',file_name:'original.txt',file_type:'txt',generation:1,content:'full original',blocks:[{id:'body',kind:'text',text:'full original',page:null}],locations:{source:[{block_id:'body',start:0,end:13}]},contents:{source:'full original'},original_url:'/api/files/1/content'};
  throw new Error("Unexpected request: " + url);
}
async function mount(address = "/app/chat?kb=7&session=10") {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: "/", component: home },
    { path: "/login", component: home },
    { path: "/app", component: WorkspaceLayout, meta: { requiresAuth: true }, children: [
      { path: "kbs", component: home }, { path: "kbs/:id", component: home }, { path: "chat", component: ChatView }, { path: "settings", component: home },
    ] },
  ] });
  installNavigationGuard(router);
  host = document.createElement("div"); document.body.appendChild(host);
  app = createApp({ render: () => h(RouterView) }); app.use(pinia); app.use(router);
  await router.push(address); await router.isReady(); app.mount(host); await nextTick();
  return router;
}
beforeEach(() => {
  pinia = createPinia(); setActivePinia(pinia);
  auth = useAuthStore(); chat = useChatStore(); kb = useKbStore();
  auth.loaded = true; auth.user = { id: 1, email: "user@example.invalid" }; deleted = null;
  get = vi.spyOn(http, "get").mockImplementation(async url => ({ data: response(url) }));
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {} })));
  window.matchMedia = globalThis.matchMedia;
});
afterEach(() => { app?.unmount(); app = null; document.body.replaceChildren(); vi.unstubAllGlobals(); });

describe("validated chat context", () => {
  it("loads the route data once and only shows histories for the chosen library", async () => {
    await mount();
    await vi.waitFor(() => expect(kb.loading).toBe(false));
    expect(chat.selectedKbId).toBe(7); expect(kb.currentKbId).toBe(7);
    expect(get.mock.calls.filter(([url]) => url === "/knowledge")).toHaveLength(1);
    expect(get.mock.calls.filter(([url]) => url === "/chat/history")).toHaveLength(1);
    expect(get.mock.calls.filter(([url]) => url === "/knowledge/7/files")).toHaveLength(1);
    expect(host.querySelectorAll(".sb-session")).toHaveLength(2);
    expect(host.textContent).toContain("question 10");
  });
  it("withholds the chat content and composer until its files load", async () => {
    const files = deferred(); get.mockImplementation(url => url === "/knowledge/7/files" ? files.promise : Promise.resolve({ data: response(url) }));
    await mount(); await vi.waitFor(() => expect(kb.currentKbId).toBe(7));
    expect(host.querySelector('.chat-main').style.display).toBe('none');
    expect(host.querySelector('.chat-main').hasAttribute('inert')).toBe(true);
    expect(host.textContent).toContain("正在读取知识库和会话");
    files.resolve({ data: [] });
    await vi.waitFor(() => expect(host.querySelector('.chat-main').style.display).not.toBe('none'));
  });
  it("allows an empty chosen library and links to uploading its first document", async () => {
    const router = await mount("/app/chat?kb=7");
    await vi.waitFor(() => expect(host.textContent).toContain("这个知识库还没有资料"));
    expect(host.querySelector(".empty-library-tip a").getAttribute("href")).toBe("/app/kbs/7");
    expect(router.currentRoute.value.path).toBe("/app/chat");
  });
  it("starts a new conversation within the selected library", async () => {
    const router = await mount(); await vi.waitFor(() => expect(kb.loading).toBe(false));
    host.querySelector(".sb-new").click();
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe("/app/chat?kb=7"));
    await vi.waitFor(() => expect(host.querySelector(".chat-input-wrap")).not.toBeNull());
    expect(chat.currentSessionId).toBeNull(); expect(chat.selectedKbId).toBe(7); expect(chat.items).toEqual([]);
  });
  it("deletes the selected conversation and keeps its valid library", async () => {
    const del = vi.spyOn(http, "delete").mockImplementation(async () => { deleted = 10; return { status: 204 }; });
    const router = await mount(); await vi.waitFor(() => expect(kb.loading).toBe(false));
    host.querySelector('button[title="删除会话"]').click(); await nextTick();
    [...document.querySelectorAll('[role="dialog"] button')].find(button => button.textContent === "删除").click();
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe("/app/chat?kb=7"));
    expect(del).toHaveBeenCalledWith("/chat/sessions/10"); expect(chat.currentSessionId).toBeNull(); expect(chat.selectedKbId).toBe(7);
  });
  it.each([403, 404].flatMap(status => ["/knowledge/7/files", "/chat/sessions/10/messages"].map(url => [url, status])))("returns home if %s is inaccessible (%s) after route validation", async (missingUrl, status) => {
    get.mockImplementation(async url => {
      if (url === missingUrl) throw { response: { status } };
      return { data: response(url) };
    });
    const router = await mount(); await vi.waitFor(() => expect(router.currentRoute.value.path).toBe("/app/kbs"));
    expect(chat.items).toEqual([]); expect(chat.currentSessionId).toBeNull(); expect(chat.selectedKbId).toBeNull();
    expect(kb.currentKbId).toBeNull(); expect(kb.docs).toEqual([]); expect(kb._pollTimer).toBeNull();
    expect(host.querySelector(".chat-input-wrap")).toBeNull();
  });
  it.each(["/knowledge/7/files", "/chat/sessions/10/messages"])("retries a temporary %s failure without treating it as a deleted resource", async failedUrl => {
    let failed = true;
    get.mockImplementation(async url => {
      if (failed && url === failedUrl) throw { response: { status: 503, data: { error: { message: "Temporary read failure" } } } };
      return { data: response(url) };
    });
    const router = await mount(); await vi.waitFor(() => expect(host.textContent).toContain("Temporary read failure"));
    expect(router.currentRoute.value.path).toBe("/app/chat");
    failed = false; host.querySelector(".chat-context-error button").click();
    await vi.waitFor(() => expect(host.querySelector(".chat-context-error")).toBeNull());
    expect(host.textContent).toContain("question 10"); expect(chat.selectedKbId).toBe(7);
  });
  it("clears Sources and stops polling when a later document refresh reports 404", async () => {
    get.mockImplementation(async url => ({ data: url === "/knowledge/7/files"
      ? [{ file_id: 1, file_name: "original.txt", enabled: true, status: "parsing", meta: {} }] : response(url) }));
    const router = await mount(); await vi.waitFor(() => expect(kb.loading).toBe(false));
    expect(kb._pollTimer).not.toBeNull();
    host.querySelector(".chat-toolbar button[aria-expanded]").click();
    await vi.waitFor(() => expect(sourceBody()).toBe("full original"));
    get.mockImplementation(async url => {
      if (url === "/knowledge/7/files") throw { response: { status: 404 } };
      return { data: response(url) };
    });
    await expect(kb.loadDocs()).rejects.toMatchObject({ response: { status: 404 } });
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe("/app/kbs"));
    await vi.waitFor(() => expect(host.querySelector(".sources-aside")).toBeNull());
    expect(kb._pollTimer).toBeNull(); expect(chat.items).toEqual([]); expect(chat.selectedKbId).toBeNull();
  });
  it("discards late history after switching to another valid conversation", async () => {
    const first = deferred();
    get.mockImplementation(url => url === "/chat/sessions/10/messages" ? first.promise : Promise.resolve({ data: response(url) }));
    const router = await mount(); await vi.waitFor(() => expect(chat.loadingMessages).toBe(true));
    await router.push("/app/chat?kb=7&session=20");
    await vi.waitFor(() => expect(host.textContent).toContain("question 20"));
    first.resolve({ data: [{ role: "user", content: "late previous question" }] }); await nextTick(); await nextTick();
    expect(chat.currentSessionId).toBe(20); expect(host.textContent).not.toContain("late previous question");
  });
  it.each([403, 404].flatMap(status => ["/chunks/source/source"].map(url => [url, status])))("keeps the conversation and Sources when %s is inaccessible (%s)", async (missingUrl, status) => {
    get.mockImplementation(async url => {
      if (url === missingUrl) throw { response: { status } };
      return { data: response(url) };
    });
    const router = await mount(); await vi.waitFor(() => expect(kb.loading).toBe(false));
    const items = chat.items;
    const input = host.querySelector('.chat-input-wrap textarea');
    input.value = '尚未发送的问题'; input.dispatchEvent(new Event('input', {bubbles: true}));
    host.querySelector(".chat-toolbar button[aria-expanded]").click();
    await vi.waitFor(() => expect(host.querySelector('.sources-aside [role="alert"]')?.textContent).toContain('来源已删除或无法查看'));
    expect(router.currentRoute.value.fullPath).toBe('/app/chat?kb=7&session=10');
    expect(chat.items).toBe(items); expect(chat.selectedKbId).toBe(7); expect(kb.currentKbId).toBe(7);
    expect(host.querySelector('.chat-input-wrap textarea').value).toBe('尚未发送的问题');
    expect(host.querySelector('.sources-aside a')).toBeNull(); expect(host.querySelector('.sources-aside iframe')).toBeNull();
    get.mockImplementation(async url => ({data: response(url)}));
    [...host.querySelectorAll('.sources-aside button')].find(button => button.textContent === '重新加载').click();
    await vi.waitFor(() => expect(sourceBody()).toBe('full original'));
  });
  it("keeps a missing source local while an answer is generating and after it ends", async () => {
    get.mockImplementation(async url => {
      if (url === "/chunks/source/source") throw { response: { status: 404 } };
      return { data: response(url) };
    });
    const router = await mount(); await vi.waitFor(() => expect(kb.loading).toBe(false));
    chat.streaming = true;
    host.querySelector(".chat-toolbar button[aria-expanded]").click();
    await vi.waitFor(() => expect(get.mock.calls.some(([url]) => url === "/chunks/source/source")).toBe(true));
    await vi.waitFor(() => expect(host.querySelector('.sources-aside [role="alert"]')?.textContent).toContain('来源已删除或无法查看'));
    expect(router.currentRoute.value.path).toBe("/app/chat"); expect(chat.selectedKbId).toBe(7); expect(chat.items).not.toEqual([]);
    chat.streaming = false;
    await nextTick();
    expect(router.currentRoute.value.path).toBe('/app/chat'); expect(chat.items).not.toEqual([]); expect(chat.selectedKbId).toBe(7);
    expect(host.querySelector('.sources-aside')).not.toBeNull();
  });
  it('shows a later polling service failure without clearing messages, sources or the draft', async () => {
    const router = await mount(); await vi.waitFor(() => expect(kb.loading).toBe(false));
    const items = chat.items, input = host.querySelector('.chat-input-wrap textarea');
    input.value = '保留草稿'; input.dispatchEvent(new Event('input', {bubbles: true}));
    host.querySelector('.chat-toolbar button[aria-expanded]').click();
    await vi.waitFor(() => expect(sourceBody()).toBe('full original'));
    get.mockImplementation(async url => {
      if (url === '/knowledge/7/files') throw {response: {status: 503}};
      return {data: response(url)};
    });
    await expect(kb.loadDocs()).rejects.toMatchObject({response: {status: 503}});
    await vi.waitFor(() => expect(host.querySelector('.chat-context-error')).not.toBeNull());
    expect(router.currentRoute.value.path).toBe('/app/chat'); expect(chat.items).toBe(items); expect(input.value).toBe('保留草稿');
    get.mockImplementation(async url => ({data: response(url)}));
    host.querySelector('.chat-context-error button').click();
    await vi.waitFor(() => expect(host.querySelector('.chat-context-error')).toBeNull());
    expect(sourceBody()).toBe('full original'); expect(chat.items).toBe(items);
    expect(host.querySelector('.chat-input-wrap textarea').value).toBe('保留草稿');
  });
  it('waits for the protected answer before leaving an inaccessible knowledge base', async () => {
    const router = await mount(); await vi.waitFor(() => expect(kb.loading).toBe(false));
    chat.streaming = true;
    get.mockImplementation(async url => {
      if (url === '/knowledge/7/files') throw {response: {status: 403}};
      return {data: response(url)};
    });
    await expect(kb.loadDocs()).rejects.toMatchObject({response: {status: 403}}); await nextTick();
    expect(router.currentRoute.value.path).toBe('/app/chat'); expect(chat.items).not.toEqual([]);
    chat.streaming = false;
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/app/kbs'));
    expect(chat.items).toEqual([]); expect(kb._pollTimer).toBeNull();
  });
  it("does not restore late history after logout", async () => {
    const first = deferred();
    get.mockImplementation(url => url === "/chat/sessions/10/messages" ? first.promise : Promise.resolve({ data: response(url) }));
    const router = await mount(); await vi.waitFor(() => expect(chat.loadingMessages).toBe(true));
    auth.clearAccount(); await router.replace("/login");
    first.resolve({ data: [{ role: "user", content: "old account question" }] }); await nextTick(); await nextTick();
    expect(chat.items).toEqual([]); expect(host.textContent).not.toContain("old account question");
    expect(host.querySelector(".chat-input-wrap")).toBeNull();
  });
});
