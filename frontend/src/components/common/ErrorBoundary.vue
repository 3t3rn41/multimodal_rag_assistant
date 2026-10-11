<template>
  <slot v-if="!error" />
  <div v-else class="error-item" role="alert">
    <Icon name="alert" /><span>该条消息渲染失败：{{ message }}</span>
  </div>
</template>

<script setup>
import { ref, onErrorCaptured } from "vue";
import Icon from "./Icon.vue";

const error = ref(false);
const message = ref("");

onErrorCaptured((err) => {
  message.value = err?.message || "未知错误";
  error.value = true;
  return false; // 已兜底，阻止继续向上传播
});
</script>
