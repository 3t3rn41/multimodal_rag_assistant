import { createRouter, createWebHistory } from "vue-router";
import { installNavigationGuard } from "./guards";

const routes = [
  { path: "/", component: () => import("../views/welcome/WelcomeView.vue") },
  { path: "/login", component: () => import("../views/auth/LoginView.vue") },
  { path: "/reset-password", component: () => import("../views/auth/ResetPasswordView.vue") },
  {
    path: "/app",
    meta: { requiresAuth: true },
    component: () => import("../views/workspace/WorkspaceLayout.vue"),
    children: [
      { path: "", redirect: "/app/kbs" },
      { path: "chat", component: () => import("../views/chat/ChatView.vue") },
      { path: "kbs", component: () => import("../views/kb/KbListView.vue") },
      { path: "kbs/:id", component: () => import("../views/kb/KbDetailView.vue") },
      { path: "settings", component: () => import("../views/settings/SettingsView.vue") },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

const router = createRouter({ history: createWebHistory(), routes });
installNavigationGuard(router);
export default router;
