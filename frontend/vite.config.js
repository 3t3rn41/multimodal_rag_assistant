import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath } from "node:url";

const envDir = fileURLToPath(new URL("..", import.meta.url));

// Vite 配置：dev server 把 /api 代理到后端 FastAPI（:8001），
// 前端代码里统一写相对路径 /api/...，本地与部署行为一致。
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, envDir, ["APP_", "PUBLIC_"]);
  const publicUrl = new URL(env.PUBLIC_BASE_URL || "http://127.0.0.1:5174");
  return {
    envDir,
    plugins: [vue()],
    server: {
      host: publicUrl.hostname,
      port: Number(publicUrl.port || (publicUrl.protocol === "https:" ? 443 : 80)),
      strictPort: true,
      proxy: {
        "/api": {
          target: env.APP_BACKEND_URL || "http://127.0.0.1:8001",
          changeOrigin: true,
          // SSE 不能被代理缓冲，否则事件会攒着一起到
          configure: (proxy) => {
            proxy.on("proxyRes", (proxyRes) => {
              const ct = proxyRes.headers["content-type"] || "";
              if (ct.includes("text/event-stream")) {
                proxyRes.headers["cache-control"] = "no-cache";
                proxyRes.headers["x-accel-buffering"] = "no";
              }
            });
          },
        },
      },
    },
  };
});
