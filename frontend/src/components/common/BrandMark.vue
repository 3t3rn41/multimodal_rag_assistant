<template>
 <span class="brand-mark"><svg viewBox="0 0 26 26" aria-hidden="true"><rect x="1.5" y="1.5" width="23" height="23" rx="4" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="13" cy="13" r="4.5" fill="currentColor"/></svg><span v-if="!compact" class="brand-mark__text">多模态 <b>RAG</b></span></span>
</template>
<script setup lang="ts">
withDefaults(defineProps<{compact?:boolean}>(),{compact:false});
</script>
