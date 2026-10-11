import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { http } from "../src/api/http";
import { useChatStore } from "../src/stores/chat";
import { sseStream } from "../src/api/sse";
import { statsRows } from "../src/utils/process-summary";

vi.mock("../src/api/sse", () => ({ sseStream: vi.fn() }));

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

describe("history regeneration", () => {
  let chat;
  beforeEach(() => {
    setActivePinia(createPinia());
    chat = useChatStore();
    chat.selectedKbId = 7;
    vi.spyOn(http, "get").mockResolvedValue({ data: [] });
    sseStream.mockReset().mockImplementation(async (_url, _body, event) => {
      event("done", { answer: "regenerated", citations: [] });
    });
  });

  it("regenerates a restored question after refreshing", async () => {
    chat.currentSessionId = 10;
    chat.rebuildItems([{ id: 1, role: "user", content: "restored question" },
      { id: 2, role: "assistant", content: "old answer" }], []);
    await chat.regenerate();
    expect(sseStream.mock.calls[0][1]).toEqual({ question: "restored question", kb_ids: [7], session_id: 10 });
  });

  it("uses the selected conversation after leaving another conversation", async () => {
    chat.currentSessionId = 10;
    chat.rebuildItems([{ id: 1, role: "user", content: "other conversation" }], []);
    chat.currentSessionId = 20;
    chat.rebuildItems([{ id: 2, role: "user", content: "current question" },
      { id: 3, role: "assistant", content: "answer" }], []);
    await chat.retryLast();
    expect(sseStream.mock.calls[0][1].question).toBe("current question");
    expect(sseStream.mock.calls[0][1].session_id).toBe(20);
  });

  it("preserves answers and explains when there is no question", async () => {
    chat.items = [{ type: "answer", content: "preserved answer" }];
    await chat.regenerate();
    expect(sseStream).not.toHaveBeenCalled();
    expect(chat.items[0].content).toBe("preserved answer");
    expect(chat.notice.text).toContain("没有可重新生成的问题");
  });

  it.each(["streaming", "loadingMessages"])("blocks regeneration while %s", async field => {
    chat.items = [{ type: "user", content: "question" }];
    chat[field] = true;
    await chat.regenerate();
    expect(sseStream).not.toHaveBeenCalled();
  });

  it("ignores an older history response after switching conversations", async () => {
    const messages = [deferred(), deferred()];
    http.get.mockImplementation(url => {
      if (url.endsWith("/trace")) return Promise.resolve({ data: { turns: [] } });
      return messages[url.includes("/1/") ? 0 : 1].promise;
    });
    const first = chat.selectSession(1);
    const second = chat.selectSession(2);
    messages[1].resolve({ data: [{ id: 2, role: "user", content: "second question" }] });
    await second;
    messages[0].resolve({ data: [{ id: 1, role: "user", content: "first question" }] });
    await first;
    expect(chat.currentSessionId).toBe(2);
    expect(chat.items[0].content).toBe("second question");
    http.get.mockResolvedValue({ data: [] });
    await chat.regenerate();
    expect(sseStream.mock.calls[0][1]).toEqual({ question: "second question", kb_ids: [7], session_id: 2 });
  });

  it("new conversation clears the question and invalidates pending history", async () => {
    const messages = deferred();
    http.get.mockImplementation(url => url.endsWith("/trace")
      ? Promise.resolve({ data: { turns: [] } }) : messages.promise);
    const pending = chat.selectSession(1);
    await chat.newSession();
    messages.resolve({ data: [{ id: 1, role: "user", content: "old question" }] });
    await pending;
    expect(chat.currentSessionId).toBeNull();
    expect(chat.items).toEqual([]);
    expect(chat.loadingMessages).toBe(false);
    await chat.regenerate();
    expect(sseStream).not.toHaveBeenCalled();
    expect(chat.notice.text).toContain("没有可重新生成的问题");
  });

  it("keeps usage and timing on the answer displayed for each turn", async () => {
    const usage = { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 };
    sseStream.mockImplementationOnce(async (_url, _body, event) => {
      event("done", { answer: "answer [chunk:one]", citations: [{ chunk_id: "one" }],
        usage, cost: 0.02, duration_ms: 250 });
    });
    await chat.ask("first question");
    const firstAnswer = chat.lastAnswer();
    expect(firstAnswer.usage).toEqual(usage);
    expect(firstAnswer.stats).toEqual({ cost: 0.02, duration_ms: 250 });
    expect(statsRows(firstAnswer)).toEqual([
      { label: "Token 用量", value: "15" },
      { label: "耗时", value: "0.3s" },
      { label: "成本", value: "$0.0200" },
    ]);
    expect(firstAnswer.citations).toEqual([{ chunk_id: "one" }]);
    await chat.ask("second question");
    expect(chat.lastAnswer().usage).toBeNull();
    expect(firstAnswer.usage).toEqual(usage);
  });
});
