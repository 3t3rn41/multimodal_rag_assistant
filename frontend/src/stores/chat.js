import { defineStore } from "pinia";
import { http, apiErrorMessage, isCanceledRequest } from "../api/http";
import { sseStream } from "../api/sse";

const CHAT_EVENTS = new Set(["start", "stage", "answer_chunk", "citation", "done", "aborted", "error"]);

/** 解析后端事件 payload 里的 session_id（形如 "sess_12"，去掉前缀取数字）。 */
function parseSessionId(raw) {
  if (raw == null) return null;
  if (typeof raw === "number") return raw;
  const m = String(raw).match(/^sess_(\d+)$/);
  return m ? Number(m[1]) : null;
}

/**
 * 对话主状态机：
 * idle → streaming → (done | aborted | error) → idle
 * 会话由 POST /chat 自动创建，session_id 从首个事件 payload 解析；
 * 渲染项 items 由 SSE 事件增量构建，历史回放按 trace 重建。
 */
export const useChatStore = defineStore("chat", {
  state: () => ({
    sessions: [],
    currentSessionId: null,
    kbs: [],
    selectedKbId: null,
    items: [],
    streaming: false,
    status: "idle", // idle | streaming | done | aborted | error
    notice: null,
    error: null,
    _seq: 0,
    turnSeq: 0,
    _abortController: null,
    loadingSessions: false,
    loadingMessages: false,
    _historySeq: 0,
  }),

  getters: {
    currentSession: (s) => s.sessions.find((x) => x.id === s.currentSessionId) || null,
    canAsk: (s) => !s.streaming && !s.loadingMessages && Number.isSafeInteger(s.selectedKbId) && s.selectedKbId > 0,
  },

  actions: {
    // ---------- 知识库作用域 ----------
    async loadKbs() {
      const { data } = await http.get("/knowledge");
      this.kbs = data;
      if (!data.some((k) => k.id === this.selectedKbId)) this.selectedKbId = null;
    },

    // ---------- 会话 ----------
    async loadSessions() {
      this.loadingSessions = true;
      try {
        const { data } = await http.get("/chat/history");
        this.sessions = data;
        return data;
      } finally {
        this.loadingSessions = false;
      }
    },

    async selectSession(id) {
      if (this.streaming) return;
      const request = ++this._historySeq;
      this.currentSessionId = id;
      this.items = [];
      this.error = null;
      this.loadingMessages = true;
      try {
        const [msgs, trace] = await Promise.all([
          http.get(`/chat/sessions/${id}/messages`),
          http.get(`/chat/sessions/${id}/trace`),
        ]);
        if (request === this._historySeq && this.currentSessionId === id) {
          this.rebuildItems(msgs.data, trace.data?.turns || []);
        }
      } catch (err) {
        if (request === this._historySeq && !isCanceledRequest(err)) {
          this.error = apiErrorMessage(err, "会话加载失败");
          throw err;
        }
      } finally {
        if (request === this._historySeq) this.loadingMessages = false;
      }
    },

    /** 历史重建：user/assistant 消息 + 按 message_id 配对的 trace 步骤。 */
    rebuildItems(messages, turns) {
      const items = [];
      const turnByMsg = new Map();
      for (const t of turns) if (t.message_id != null) turnByMsg.set(t.message_id, t);
      for (const m of messages) {
        if (m.role === "user") {
          items.push({ type: "user", content: m.content || "", created_time: m.created_time, _key: `m_${m.id}` });
        } else if (m.role === "assistant") {
          const turn = turnByMsg.get(m.id) || { steps: [] };
          for (const [i, step] of (turn.steps || []).entries()) {
            const item = this.stepToItem(step);
            if (item) {
              item._key = `m_${m.id}_step_${i}`;
              items.push(item);
            }
          }
          items.push({
            type: "answer",
            content: m.content || "",
            streaming: false,
            citations: Array.isArray(m.refs) ? m.refs : [],
            created_time: m.created_time,
            usage: turn.metrics?.usage || null,
            _key: `m_${m.id}`,
            messageId: m.id,
            feedback: m.feedback || null,
          });
        }
      }
      this.items = items;
    },

    stepToItem(step) {
      if (step?.type !== "stage") return null;
      return {type:"stage", stage:step.stage, label:step.label, status:step.status || "done", count:step.count, duration_ms:step.duration_ms};
    },

    async newSession() {
      if (this.streaming) return;
      this._historySeq++;
      this.loadingMessages = false;
      this.currentSessionId = null;
      this.items = [];
      this.error = null;
      this.notice = null;
    },

    async renameSession(id, title) {
      await http.patch(`/chat/sessions/${id}`, { title });
      await this.loadSessions();
    },

    async deleteSession(id) {
      await http.delete(`/chat/sessions/${id}`);
      if (this.currentSessionId === id) {
        await this.newSession();
      }
      await this.loadSessions();
    },

    async exportSession(id) {
      const { data } = await http.get(`/chat/sessions/${id}/export`);
      return data;
    },

    // ---------- 对话流 ----------
    /** 发起提问。返回是否真正开始发送（false = 输入为空/流式进行中，调用方应保留输入）。 */
    async ask(question, sessionId = null) {
      if (!question.trim() || this.streaming) return false;
      if (!this.canAsk) {
        this.setNotice({type:"info",text:"请先选择一个知识库，再提问。"});
        return false;
      }
      this.turnSeq += 1;
      this.items.push({ type: "user", content: question, _key: this._nextKey() });
      this._appendAnswer();
      await this._stream(question, sessionId || this.currentSessionId);
      return true;
    },

    _nextKey() {
      return `msg_${++this._seq}`;
    },

    /** 统一发起流式请求；无论正常结束、错误还是异常抛错，状态机都能复位。 */
    async _stream(question, sessionId) {
      this.streaming = true;
      this.status = "streaming";
      this.error = null;
      this.notice = null;

      const ctrl = new AbortController();
      this._abortController = ctrl;
      try {
        await sseStream(
          "/api/chat",
          { question, kb_ids: [this.selectedKbId], session_id: sessionId },
          (event, payload) => this._onSseEvent(event, payload),
          ctrl.signal,
        );
        await this._syncLastAnswerMessageId();
      } catch (err) {
        if (this._abortController !== ctrl || isCanceledRequest(err)) return;
        this.status = "error";
        this.error = apiErrorMessage(err, "请求失败");
        const last = this.lastAnswer();
        if (last) last.streaming = false;
        this.items.push({ type: "error", message: this.error, retryable: true, _key: this._nextKey() });
      } finally {
        // 身份守卫：abort 或新流已接管时（_abortController 已被替换/置空）不清理新流状态
        if (this._abortController !== ctrl) return;
        // 流异常结束（无终态事件：后端断开/重启/EOF）：复位状态，保留已生成内容
        if (this.status === "streaming") {
          const last = this.lastAnswer();
          if (last) last.streaming = false;
          this.status = "aborted";
          this.setNotice({ type: "info", text: "连接中断，已生成的内容已保留" });
        }
        this._finishStages(this.status);
        this.streaming = false;
        this._abortController = null;
      }
      this.loadSessions().catch(() => {});
    },

    /** 流结束后把最后一条 answer 关联到后端 assistant 消息 id（供反馈持久化）。 */
    async _syncLastAnswerMessageId() {
      const ans = this.lastAnswer();
      if (!ans || ans.messageId != null || !ans.content || !this.currentSessionId) return;
      if (this.status !== "done") return; // 仅完成轮自动配对，避免并发刷新错配上一轮消息
      try {
        const { data } = await http.get(`/chat/sessions/${this.currentSessionId}/messages`);
        const assistant = [...(data || [])].reverse().find((m) => m.role === "assistant");
        if (assistant) ans.messageId = assistant.id;
      } catch {
        /* 同步失败静默：反馈按钮暂不可用，不阻断对话 */
      }
    },

    /** 保存/取消反馈（乐观更新，失败回滚）。无 messageId 时不做乐观更新。 */
    async setFeedback(messageId, kind) {
      if (!messageId || !this.currentSessionId) return { ok: false, reason: "no-message-id" };
      const item = this.items.find((it) => it.messageId === messageId);
      const prev = item?.feedback ?? null;
      if (item) item.feedback = kind;
      try {
        await http.put(
          `/chat/sessions/${this.currentSessionId}/messages/${messageId}/feedback`,
          { feedback: kind },
        );
        return { ok: true };
      } catch (err) {
        if (item) item.feedback = prev;
        if (isCanceledRequest(err)) return { ok: false, reason: "canceled" };
        return { ok: false, error: apiErrorMessage(err, "反馈保存失败") };
      }
    },

    /** 重试/重新生成：清空上一轮的过程与答案，原地重开本轮。 */
    async retryLast() {
      if (this.streaming || this.loadingMessages) return;
      if (!this.canAsk) {
        this.setNotice({type:"info",text:"请先选择一个知识库，再重新生成。"});
        return;
      }
      let cut = -1;
      let question = "";
      for (let i = this.items.length - 1; i >= 0; i--) {
        if (this.items[i].type === "user") {
          question = String(this.items[i].content || "").trim();
          cut = i + 1;
          break;
        }
      }
      if (cut < 0 || !question) {
        this.setNotice({type:"info",text:"当前会话没有可重新生成的问题。"});
        return;
      }
      this.items.splice(cut);
      this._appendAnswer();
      this.error = null;
      this.notice = null;
      await this._stream(question, this.currentSessionId);
    },

    /** 重新生成最后一条回答（与错误重试共用同一套"原地重启"逻辑）。 */
    async regenerate() {
      return this.retryLast();
    },

    _appendAnswer() {
      this.items.push({
        type: "answer",
        content: "",
        streaming: true,
        citations: [],
        _key: this._nextKey(),
      });
    },

    _onSseEvent(event, payload) {
      if (!CHAT_EVENTS.has(event)) return;
      // 会话 id 由后端在事件里回传（形如 sess_12）；新会话首帧即带回
      const sid = parseSessionId(payload?.session_id);
      if (sid != null) this.currentSessionId = sid;

      switch (event) {
        case "stage": {
          let cut = this.items.length - 1;
          for (; cut >= 0; cut--) if (this.items[cut].type === "user") break;
          const current = this.items.slice(cut + 1).find((it) => it.type === "stage" && it.stage === payload.stage);
          if (current) Object.assign(current, payload, {type:"stage"});
          else {
            const index = this.items.findLastIndex((it) => it.type === "answer");
            const step = {...payload, type:"stage", _key:this._nextKey()};
            if (index > cut) this.items.splice(index, 0, step);
            else this.items.push(step);
          }
          break;
        }
        case "answer_chunk": {
          let last = this.lastAnswer();
          if (!last) {
            // 防御：脏流/异常流兜底创建 answer 项
            this._appendAnswer();
            last = this.lastAnswer();
          }
          if (last) last.content += payload.chunk ?? payload.content ?? "";
          break;
        }
        case "citation": {
          const last = this.lastAnswer();
          if (last && payload.chunk_id != null && !last.citations.some((c) => String(c.chunk_id) === String(payload.chunk_id))) last.citations.push(payload);
          break;
        }
        case "done": {
          const last = this.lastAnswer();
          if (last) {
            if (payload.answer != null) last.content = payload.answer;
            if (Array.isArray(payload.citations)) last.citations = payload.citations;
            last.streaming = false;
            last.usage = payload.usage || null;
            last.stats = {
              cost: payload.cost,
              duration_ms: payload.duration_ms,
            };
          }
          this.status = "done";
          break;
        }
        case "aborted": {
          const last = this.lastAnswer();
          if (last) last.streaming = false;
          this.status = "aborted";
          this._finishStages("aborted");
          this.setNotice({ type: "info", text: payload.message || "已中断，已生成的内容已保留" });
          break;
        }
        case "error": {
          const last = this.lastAnswer();
          if (last) last.streaming = false;
          this.status = "error";
          this._finishStages("error");
          this.error = payload.message || "未知错误";
          this.items.push({ type: "error", message: this.error, retryable: true, _key: this._nextKey() });
          break;
        }
        default:
          break;
      }
    },

    _finishStages(status) {
      for (let i = this.items.length - 1; i >= 0; i--) {
        const item = this.items[i];
        if (item.type === "user") break;
        if (item.type === "stage" && item.status === "running") item.status = status;
      }
    },

    lastAnswer() {
      for (let i = this.items.length - 1; i >= 0; i--) {
        if (this.items[i].type === "answer") return this.items[i];
      }
      return null;
    },

    async abort() {
      if (!this.streaming) return;
      if (this.currentSessionId) {
        try {
          await http.post(`/chat/sessions/${this.currentSessionId}/abort`);
        } catch {
          /* 后端中断失败时直接断开本地流 */
        }
      }
      this._abortController?.abort();
      const last = this.lastAnswer();
      if (last) last.streaming = false;
      this.streaming = false;
      this.status = "aborted";
      this._finishStages("aborted");
    },

    setNotice(n) {
      this.notice = n;
    },
    clearNotice() {
      this.notice = null;
    },
  },
});

