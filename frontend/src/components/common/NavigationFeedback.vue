<template>
  <section ref="root" class="navigation-feedback" role="dialog" aria-modal="true" aria-label="页面读取状态" tabindex="-1">
    <div class="navigation-feedback-card">
      <p v-if="!navigation.error" role="status">正在读取账号、知识库和会话…</p>
      <template v-else>
        <h1>读取失败</h1>
        <p role="alert">{{ navigation.error }}</p>
        <div class="navigation-feedback-actions">
          <button class="btn btn-primary" @click="retry">重试</button>
          <button class="btn btn-ghost" @click="router.replace('/app/kbs')">返回知识库</button>
        </div>
      </template>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch, nextTick } from "vue";
import { useRouter } from "vue-router";
import { useNavigationStore } from "../../stores/navigation";
import { useOverlayFocus } from "../../composables/useOverlayFocus";

const router = useRouter(), navigation = useNavigationStore();
const root = ref(null);
useOverlayFocus(computed(() => !!navigation.target), root, () => {});
watch(() => navigation.error, async error => {
  if (error) { await nextTick(); root.value?.querySelector('button')?.focus(); }
});
function retry() {
  if (navigation.target) router.replace(navigation.target);
}
</script>

<style scoped>
.navigation-feedback{position:fixed;inset:0;z-index:calc(var(--z-dialog) + 1);overflow:auto;display:grid;place-items:center;padding:24px;background:var(--bg)}
.navigation-feedback-card{width:min(100%,480px);padding:32px;display:flex;flex-direction:column;gap:18px;background:var(--surface);border:1px solid var(--line);border-radius:12px}
.navigation-feedback-card h1{font-size:20px}.navigation-feedback-card p{overflow-wrap:anywhere}
.navigation-feedback-actions{display:flex;flex-wrap:wrap;gap:10px}
</style>
