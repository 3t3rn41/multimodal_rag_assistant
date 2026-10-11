<template>
  <div v-if="fatal" class="fatal-screen">
    <div class="fatal-card">
      <Icon name="alert" />
      <p>页面渲染出现异常，已停止加载出错的内容。</p>
      <button class="btn btn-primary" @click="reloadPage">重新加载</button>
    </div>
  </div>
  <template v-else>
    <router-view v-slot="{ Component }">
      <component :is="Component" v-show="!navigation.target" :inert="!!navigation.target" />
    </router-view>
    <NavigationFeedback v-if="navigation.target" />
  </template>
  <ToastHost />
</template>

<script setup>
import { ref, onErrorCaptured } from "vue";
import ToastHost from "./components/common/ToastHost.vue";
import Icon from "./components/common/Icon.vue";
import NavigationFeedback from "./components/common/NavigationFeedback.vue";
import { useNavigationStore } from "./stores/navigation";

const fatal = ref(false), navigation = useNavigationStore();

// 未被消息级 ErrorBoundary 捕获的渲染错误：降级为整页提示，避免白屏
onErrorCaptured((err, _instance, info) => {
  console.error("[Multimodal RAG captured]", info, err);
  fatal.value = true;
  return false;
});

function reloadPage() {
  window.location.reload();
}
</script>

<style scoped>
.fatal-screen {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
}
.fatal-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 36px 44px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
  text-align: center;
}
.fatal-card svg { width: 28px; height: 28px; color: var(--err); }
</style>
