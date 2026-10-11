<template>
  <div class="toast-host" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="t.type">
        <Icon :name="iconName(t.type)" />
        <span class="toast-msg">{{ t.message }}</span>
        <button class="btn-icon" @click="removeToast(t.id)"><Icon name="x" /></button>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup>
import { toasts, removeToast } from "../../utils/toast";
import Icon from "./Icon.vue";

function iconName(type) {
  return { error: "alert", success: "check", warn: "alert" }[type] || "spark";
}
</script>