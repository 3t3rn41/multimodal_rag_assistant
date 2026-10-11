import axios from "axios";
import { csrfHeaders } from "./csrf";

// 统一 axios 实例：dev 下走 Vite 代理（/api -> :8001）。
export const http = axios.create({
  baseURL: "/api",
  timeout: 30_000,
  withCredentials: true,
});

let accountEpoch = 0;
export function invalidateAccountRequests() {
  accountEpoch += 1;
  if (typeof window !== "undefined") window.dispatchEvent(new Event("mmrag-account-cleared"));
}
export function isCanceledRequest(err) { return axios.isCancel(err) || err?.code === "ERR_CANCELED"; }
http.interceptors.request.use(config => {
  config.mmragEpoch = accountEpoch;
  if (!["get", "head", "options"].includes((config.method || "get").toLowerCase())) {
    Object.assign(config.headers, csrfHeaders(), { "X-Requested-With": "XMLHttpRequest" });
  }
  return config;
});
http.interceptors.response.use(response => {
  if (response.config.mmragEpoch !== accountEpoch) throw new axios.CanceledError("账号已切换");
  return response;
}, error => {
  if (error.config?.mmragEpoch != null && error.config.mmragEpoch !== accountEpoch) {
    return Promise.reject(new axios.CanceledError("账号已切换"));
  }
  if (error.response?.status === 401 && !error.config?.url?.startsWith("/auth/") && typeof window !== "undefined") {
    window.dispatchEvent(new Event("mmrag-session-expired"));
  }
  return Promise.reject(error);
});

/** 提取后端错误详情：优先统一错误体 {"error": {message}}，兼容 FastAPI detail。 */
export function apiErrorMessage(err, fallback = "请求失败") {
  const body = err?.response?.data;
  const unified = body?.error?.message;
  if (typeof unified === "string" && unified) return unified;
  const d = body?.detail;
  if (typeof d === "string" && d) return d;
  if (Array.isArray(d) && d[0]?.msg) return d[0]?.msg;
  return err?.message || fallback;
}

export function isUnavailableResource(error) {
  return [403, 404].includes(error?.response?.status);
}

export function apiReadErrorMessage(error, fallback = "读取失败，请稍后重试。") {
  return apiErrorMessage({ response: error?.response }, fallback);
}
