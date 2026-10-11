<template>
 <main class="welcome-page">
  <header class="welcome-header"><BrandMark/></header>
  <section class="welcome-hero">
   <div class="welcome-copy"><h1>让你的知识，真正可检索、可理解、可追溯</h1><p>上传 PDF、DOCX、TXT 或 MD 文档，构建属于你的知识库，通过自然语言提问，并查看回答的原文引用。</p><button class="btn btn-primary welcome-start" :disabled="entering" @click="start">{{ entering?'正在进入…':'开始使用' }}</button></div>
   <div class="welcome-network"><KnowledgeNetwork variant="reference" :count="80"/></div>
  </section>
 </main>
</template>
<script setup lang="ts">
import {ref} from 'vue';
import {useRouter} from 'vue-router';
import BrandMark from '../../components/common/BrandMark.vue';
import KnowledgeNetwork from '../../components/welcome/KnowledgeNetwork.vue';
import {useWorkbenchAuth} from '../../composables/useWorkbench';
const router=useRouter(),auth=useWorkbenchAuth(),entering=ref(false);
async function start(){if(entering.value)return;entering.value=true;try{await auth.init();await router.push(auth.user?'/app/kbs':'/login')}finally{entering.value=false}}
</script>
<style scoped>
.welcome-page{min-height:100dvh;max-width:1440px;margin:auto;padding:32px 56px;display:flex;flex-direction:column}
.welcome-header{min-height:40px;display:flex;align-items:center}.welcome-hero{flex:1;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.2fr);gap:48px;align-items:center;min-height:calc(100dvh - 104px)}
.welcome-copy{padding:24px 0 64px}.welcome-copy h1{font-size:clamp(32px,3.6vw,52px);font-weight:550;letter-spacing:-1.8px;line-height:1.45;max-width:12em}
.welcome-copy p{font-size:16px;line-height:2;color:var(--ink-mute);max-width:36em;margin-top:24px}
.welcome-start{margin-top:36px;min-height:46px;padding:12px 23px;gap:24px;font-size:14px}
.welcome-network{height:min(84dvh,820px);min-height:400px;width:100%;margin-bottom:28px}
@media(max-width:1023px){.welcome-page{padding:28px 36px}.welcome-hero{gap:24px;grid-template-columns:minmax(0,1fr) minmax(0,1.1fr)}.welcome-copy h1{letter-spacing:-1px}.welcome-copy p{font-size:15px}.welcome-network{min-height:360px}}
@media(max-width:767px){.welcome-page{padding:24px 24px 16px}.welcome-hero{grid-template-columns:minmax(0,1fr);gap:8px;min-height:0;align-items:start}.welcome-copy{padding:56px 0 8px}.welcome-copy h1{font-size:32px;line-height:1.5;letter-spacing:-.8px}.welcome-copy p{font-size:14px;line-height:1.9;margin-top:18px}.welcome-start{margin-top:26px}.welcome-network{height:300px;min-height:260px;margin-bottom:0}}
</style>
