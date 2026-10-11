<template>
 <main class="auth-page">
  <aside class="auth-aside"><RouterLink to="/" class="auth-home" aria-label="返回欢迎页"><BrandMark/></RouterLink><div class="auth-aside-copy"><h2>让知识，<br/>连接起来。</h2><p>整理你的资料，提出你的问题。<br/>让每一个回答，都有原文可以追溯。</p></div><div class="auth-network"><KnowledgeNetwork variant="auth" decorative :count="50"/></div></aside>
  <div class="auth-main"><section class="auth-card"><slot/></section></div>
 </main>
</template>
<script setup lang="ts">
import BrandMark from '../common/BrandMark.vue';
import KnowledgeNetwork from '../welcome/KnowledgeNetwork.vue';
</script>
