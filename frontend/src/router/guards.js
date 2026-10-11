import { useAuthStore } from "../stores/auth";
import { useChatStore } from "../stores/chat";
import { useKbStore } from "../stores/kb";
import { useNavigationStore } from "../stores/navigation";
import { http, apiReadErrorMessage, isCanceledRequest, isUnavailableResource } from "../api/http";
import { hasWorkspaceUpload } from "../composables/useWorkspaceUpload";
import { hasPendingKnowledgeFiles } from "../composables/useKnowledgeFileSelection";
import { matchesActiveChat, positiveId, sessionKnowledgeId } from "../utils/workbench-navigation";
import { toast } from "../utils/toast";

export function clearChatContext() {
  const chat = useChatStore(), kb = useKbStore();
  chat.newSession();
  chat.selectedKbId = null;
  kb.stopPolling();
  kb.currentKbId = null;
  kb.docs = [];
  kb.loading = false;
  kb.error = null;
  kb.errorStatus = null;
}

export function installNavigationGuard(router) {
  let sequence = 0, pendingController = null;
  return router.beforeEach(async (to, from) => {
    const request = ++sequence;
    pendingController?.abort();
    pendingController = null;
    const auth = useAuthStore(), chat = useChatStore(), navigation = useNavigationStore();
    if (auth.user && to.fullPath !== from.fullPath) {
      if (hasPendingKnowledgeFiles(auth.user)) {
        toast("文件启用状态正在保存，请稍等。", "info");
        return false;
      }
      if (hasWorkspaceUpload(auth.user)) {
        toast("文件正在上传或导入，请等待完成。", "info");
        return false;
      }
      if (chat.streaming && !matchesActiveChat(to.path, to.query, chat.currentSessionId, chat.selectedKbId)) {
        toast("回答正在生成，请先停止当前回答。", "info");
        return false;
      }
    }
    navigation.clear();
    // The welcome page can render when the login service is unavailable.
    if (to.path === "/") return;
    if (!auth.loaded) navigation.begin(to.fullPath);
    await auth.init();
    if (request !== sequence) return false;
    if (!auth.loaded) {
      navigation.fail(auth.error || "登录状态读取失败，请稍后重试。");
      return false;
    }
    navigation.clear();
    if (to.meta.requiresAuth && !auth.user) return { path: "/login", replace: true };
    if (to.path === "/login" && auth.user) return { path: "/app/kbs", replace: true };
    if (to.path !== "/app/chat") return;

    // The server-created session becomes part of the URL while its answer is streaming.
    if (chat.streaming && from.path === "/app/chat" && matchesActiveChat(to.path, to.query, chat.currentSessionId, chat.selectedKbId)) return;
    const kbId = positiveId(to.query.kb), sessionId = positiveId(to.query.session);
    const home = message => {
      clearChatContext();
      if (message) toast(message, "info");
      return { path: "/app/kbs", replace: true };
    };
    if (!kbId || (to.query.session !== undefined && !sessionId)) return home("请先从首页选择一个可用的知识库。");

    navigation.begin(to.fullPath);
    const owner = auth.user, controller = new AbortController();
    pendingController = controller;
    const cancel = () => controller.abort();
    window.addEventListener("mmrag-account-cleared", cancel);
    try {
      const [bases, sessions] = await Promise.all([
        http.get("/knowledge", { signal: controller.signal }),
        http.get("/chat/history", { signal: controller.signal }),
      ]);
      if (request !== sequence) return false;
      if (auth.user !== owner) return { path: auth.user ? "/app/kbs" : "/login", replace: true };
      if (controller.signal.aborted) return false;
      chat.kbs = bases.data;
      useKbStore().kbs = bases.data;
      chat.sessions = sessions.data;
      if (!bases.data.some(base => base.id === kbId)) return home("知识库不存在或无法访问，请重新选择。");
      if (sessionId) {
        const session = sessions.data.find(item => item.id === sessionId);
        if (!session || sessionKnowledgeId(session, bases.data) !== kbId) return home("会话已失效或不属于当前知识库，请重新选择。");
      }
    } catch (error) {
      if (request !== sequence) return false;
      if (auth.user !== owner) return { path: auth.user ? "/app/kbs" : "/login", replace: true };
      if (controller.signal.aborted || isCanceledRequest(error)) return false;
      if (error.response?.status === 401) {
        auth.clearAccount();
        return { path: "/login", replace: true };
      }
      if (isUnavailableResource(error)) return home("知识库或会话不存在或无法访问，请重新选择。");
      navigation.fail(apiReadErrorMessage(error, "知识库或会话读取失败，请稍后重试。"));
      return false;
    } finally {
      controller.abort();
      window.removeEventListener("mmrag-account-cleared", cancel);
      if (pendingController === controller) pendingController = null;
      if (request === sequence && !navigation.error) navigation.clear();
    }
  });
}
