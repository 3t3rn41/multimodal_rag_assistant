import { defineStore } from "pinia";

export const useNavigationStore = defineStore("navigation", {
  state: () => ({ target: null, error: null }),
  actions: {
    begin(target) {
      this.target = target;
      this.error = null;
    },
    fail(message) {
      this.error = message;
    },
    clear() {
      this.$reset();
    },
  },
});
