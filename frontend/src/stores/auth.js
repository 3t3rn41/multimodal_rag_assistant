import { defineStore, getActivePinia } from "pinia";
import { http, apiReadErrorMessage, invalidateAccountRequests, isCanceledRequest } from "../api/http";

export const useAuthStore = defineStore("auth", {
  state: () => ({ user: null, loaded: false, error: null, _pending: null }),
  actions: {
    async init() {
      if (this.loaded) return;
      if (this._pending) return this._pending;
      this._pending = (async () => {
        this.error = null;
        try {
          this.user = (await http.get("/auth/me")).data;
          this.loaded = true;
        } catch (error) {
          if (isCanceledRequest(error)) return;
          if (error.response?.status === 401) {
            this.user = null;
            this.loaded = true;
          } else {
            this.error = apiReadErrorMessage(error, "登录状态读取失败，请稍后重试。");
          }
        } finally {
          this._pending = null;
        }
      })();
      return this._pending;
    },
    clearAccount() {
      invalidateAccountRequests();
      for (const [name, store] of getActivePinia()._s) {
        if (name === "auth") continue;
        store.stopPolling?.();
        store._abortController?.abort();
        store.$reset?.();
      }
      this.user = null;
      this.error = null;
    },
    async login(email, password) {
      const { data } = await http.post("/auth/login", { email, password });
      this.clearAccount();
      this.user = data;
      this.loaded = true;
      return data;
    },
    async logout() {
      try { await http.post("/auth/logout"); }
      catch (error) { if (error.response?.status !== 401) throw error; }
      this.clearAccount();
    },
  },
});
