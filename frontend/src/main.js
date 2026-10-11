import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import { useAuthStore } from "./stores/auth";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/app.css";
import "./styles/chat.css";
import "./styles/kb.css";
import "./styles/auth.css";
import "./styles/design-system.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);

window.addEventListener("mmrag-session-expired", () => {
  const auth = useAuthStore();
  if (!auth.user) return;
  auth.clearAccount();
  router.replace("/login");
});

// 全局渲染错误兜底：与 App.vue 的 onErrorCaptured / 消息级 ErrorBoundary 配合，
// 保证单条数据异常不会白屏整个应用。
app.config.errorHandler = (err, _instance, info) => {
  console.error("[Multimodal RAG render error]", info, err);
};

app.mount("#app");
