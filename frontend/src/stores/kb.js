import { defineStore } from "pinia";
import { http, apiErrorMessage, apiReadErrorMessage, isCanceledRequest } from "../api/http";
import { isDocumentProcessing } from "../utils/document-task";

const POLL_MS = 3000;

/**
 * 知识库管理：库 CRUD、库内文档（上传/启停/移除）、解析状态轮询、
 */
export const useKbStore = defineStore("kb", {
  state: () => ({
    kbs: [],
    currentKbId: null,
    docs: [],
    loading: false,
    error: null,
    errorStatus: null,
    _pollTimer: null,
  }),

  getters: {
    currentKb: (s) => s.kbs.find((k) => k.id === s.currentKbId) || null,
    hasParsingDocs: (s) =>
      s.docs.some(isDocumentProcessing),
  },

  actions: {
    async loadKbs() {
      const { data } = await http.get("/knowledge");
      this.kbs = data;
      if (this.currentKbId && !data.some((k) => k.id === this.currentKbId)) {
        this.currentKbId = null;
        this.docs = [];
      }
      return data;
    },

    async createKb(name, description, topicTags) {
      const { data } = await http.post("/knowledge", {
        name,
        description: description || null,
        topic_tags: topicTags?.length ? topicTags : null,
      });
      await this.loadKbs();
      this.currentKbId = data.id;
      await this.loadDocs();
      return data;
    },

    async updateKb(kbId, patch) {
      const { data } = await http.patch(`/knowledge/${kbId}`, patch);
      await this.loadKbs();
      return data;
    },

    async deleteKb(kbId) {
      await http.delete(`/knowledge/${kbId}`);
      if (this.currentKbId === kbId) {
        this.currentKbId = null;
        this.docs = [];
      }
      await this.loadKbs();
    },

    async selectKb(id) {
      this.stopPolling();
      this.error = null;
      this.errorStatus = null;
      this.currentKbId = id;
      await this.loadDocs();
    },

    async loadDocs() {
      if (!this.currentKbId) {
        this.docs = [];
        return;
      }
      const kbId = this.currentKbId;
      try {
        const { data } = await http.get(`/knowledge/${kbId}/files`);
        if (kbId !== this.currentKbId) return;
        this.docs = data;
        this.error = null;
        this.errorStatus = null;
        this._syncPolling();
      } catch (err) {
        if (!isCanceledRequest(err) && kbId === this.currentKbId) {
          this.error = apiReadErrorMessage(err, "文档状态读取失败，请稍后重试。");
          this.errorStatus = err.response?.status || null;
        }
        throw err;
      }
    },

    /** 上传文件并归入当前库。files: File[] → 返回新增文档列表 */
    async uploadFiles(files, onProgress) {
      if (!this.currentKbId) throw new Error("请先选择知识库");
      const added = [];
      const failedFiles = [];
      let lastErr = null;
      for (const file of files) {
        try {
          const form = new FormData();
          form.append("file", file);
          const { data } = await http.post("/files/upload", form, {
            headers: { "Content-Type": "multipart/form-data" },
            onUploadProgress: (e) => onProgress?.(file.name, e.loaded / (e.total || 1)),
          });
          await http.post(`/knowledge/${this.currentKbId}/files`, { file_id: data.id, enabled: true });
          added.push(data);
        } catch (err) {
          if (isCanceledRequest(err)) throw err;
          // 单文件失败不中断其余；记录错误，结束后统一提示
          failedFiles.push(file);
          lastErr = apiErrorMessage(err, `上传失败：${file.name}`);
        }
      }
      // 无论成功失败都刷新列表，避免"已归库但列表不显示"
      try {
        await this.loadDocs();
      } catch {
        /* 刷新失败不覆盖主错误 */
      }
      if (lastErr) {
        const error = new Error(lastErr);
        error.failedFiles = failedFiles;
        throw error;
      }
      return added;
    },

    async uploadUrl(url) {
      if (!this.currentKbId) throw new Error("请先选择知识库");
      const { data } = await http.post("/files/upload_url", { url });
      await http.post(`/knowledge/${this.currentKbId}/files`, { file_id: data.id, enabled: true });
      await this.loadDocs();
      return data;
    },

    async reparse(docId) {
      await http.post(`/files/${docId}/reparse`);
      await this.loadDocs();
    },

    async removeDoc(kbId, docId) {
      await http.delete(`/knowledge/${kbId}/files/${docId}`);
      await this.loadDocs();
    },

    async setDocEnabled(docId, enabled) {
      await http.patch(`/knowledge/${this.currentKbId}/files/${docId}`, { enabled });
      await this.loadDocs();
    },

    async reportCorrection(docId) {
      await http.patch(`/knowledge/${this.currentKbId}/files/${docId}`, {
        report_correction: true,
      });
      await this.loadDocs();
    },

    stopPolling() {
      clearTimeout(this._pollTimer);
      this._pollTimer = null;
    },

    _syncPolling() {
      this.stopPolling();
      if ([403, 404].includes(this.errorStatus)) return;
      if (this.hasParsingDocs) {
        this._pollTimer = setTimeout(async () => {
          this._pollTimer = null;
          try {
            await this.loadDocs();
          } catch {
            // 暂时断连时保留真实进度，显示错误，并在下一轮继续刷新。
            this._syncPolling();
          }
        }, POLL_MS);
      }
    },
  },
});
