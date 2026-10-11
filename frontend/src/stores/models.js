import { defineStore } from "pinia";
import { http } from "../api/http";

export const useModelsStore = defineStore("models", {
  state: () => ({ config: null, loading: false }),
  getters: { configured: state => !!state.config?.configured },
  actions: {
    async load() {
      this.loading = true;
      try { this.config = (await http.get("/users/me/models")).data; return this.config; }
      finally { this.loading = false; }
    },
  },
});
