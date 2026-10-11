<template>
 <div class="workspace" :class="{'nav-collapsed':collapsed,'mobile-open':mobileOpen,'workspace-chat':isChatRoute}">
  <div v-if="mobileOpen" class="nav-mask" @click="mobileOpen=false" aria-hidden="true"/>
  <aside ref="nav" class="nav" :inert="isMobile&&!mobileOpen" :role="isMobile&&mobileOpen?'dialog':undefined" :aria-modal="isMobile&&mobileOpen?true:undefined" aria-label="工作台导航" tabindex="-1">
   <RouterLink to="/app/kbs" class="nav-brand" aria-label="多模态 RAG 知识库首页"><BrandMark :compact="collapsed&&!isMobile"/></RouterLink>
   <nav class="nav-items" aria-label="主导航">
    <RouterLink v-for="item in navigation" :key="item.to" :to="item.to" class="nav-item" :class="{active:isActive(item.to)}" :title="item.label" :aria-current="isActive(item.to)?'page':undefined">
     <Icon :name="item.icon"/><span class="nav-label">{{ item.label }}</span>
    </RouterLink>
   </nav>
   <section v-if="!isChatRoute" class="nav-recent" aria-label="最近使用的知识库">
    <h2>最近使用</h2>
    <RouterLink v-for="base in recent" :key="base.id" :to="{path:'/app/chat',query:{kb:String(base.id)}}" class="recent-knowledge" :title="base.name" :aria-label="'打开最近使用的知识库 '+base.name"><Icon name="folder"/><span>{{ base.name }}</span></RouterLink>
    <p v-if="!recent.length">打开过的知识库会显示在这里。</p>
   </section>
   <SessionSidebar v-if="isChatRoute" class="nav-sessions" @new-session="newConversation"/>
   <button v-if="isChatRoute&&collapsed&&!isMobile" class="rail-new btn-icon" title="新建会话" :disabled="chat.streaming||chat.loadingMessages||kb.loading||uploadBusy||fileBusy" @click="newConversation"><Icon name="plus"/></button>
   <div class="nav-foot">
    <div class="account-line"><span class="account-initial" aria-hidden="true">{{ (auth.user?.email||'U').charAt(0).toUpperCase() }}</span><span class="account-email" :title="auth.user?.email">{{ auth.user?.email||'个人空间' }}</span><button class="btn-icon" title="退出登录" aria-label="退出登录" :disabled="loggingOut" @click="logout"><Icon name="logout"/></button></div>
    <p v-if="logoutError" class="error-item" role="alert">{{ logoutError }}</p>
   </div>
  </aside>
  <div class="main-col" :inert="isMobile&&mobileOpen">
   <header class="topbar">
    <button class="btn-icon collapse-btn" :aria-label="isMobile?'打开导航':collapsed?'展开导航':'折叠导航'" :aria-expanded="isMobile?mobileOpen:!collapsed" @click="toggleNavigation"><Icon :name="isMobile?'menu':'sidebar'"/></button>
    <div class="topbar-titles"><span class="page-title">{{ currentTitle }}</span><span v-if="isChatRoute" class="page-context">{{ chatKnowledgeLabel }}</span><span v-else class="page-context">个人知识空间</span></div>
    <div class="spacer"/>
    <RouterLink to="/app/settings" class="model-chip" :class="{unconfigured:models.config&&!models.configured}" :title="modelsError||'查看系统回答模型状态'"><Icon name="plug"/><span>{{ modelsError?'配置读取失败':models.config?(models.configured?'模型已就绪':'模型未就绪'):'模型状态' }}</span></RouterLink>
   </header>
   <div v-if="chat.notice" class="notice-banner" :class="chat.notice.type==='error'?'error':'info'" role="status">
    <Icon :name="chat.notice.type==='error'?'alert':'bulb'"/><span>{{ chat.notice.text }}</span><button class="btn-icon nb-close" aria-label="关闭提示" @click="chat.clearNotice()"><Icon name="x"/></button>
   </div>
   <main class="content">
    <div class="content-inner">
     <RouterView v-slot="{Component}"><Transition name="page-fade" mode="out-in"><component :is="Component" :key="route.path"/></Transition></RouterView>
    </div>
   </main>
  </div>
 </div>
</template>
<script setup lang="ts">
import {ref,computed,onMounted,onBeforeUnmount,watch} from 'vue';
import {useRoute,useRouter} from 'vue-router';
import Icon from '../../components/common/Icon.vue';
import BrandMark from '../../components/common/BrandMark.vue';
import SessionSidebar from '../../components/chat/SessionSidebar.vue';
import {useWorkbenchAuth,useWorkbenchChat,useWorkbenchModels,useWorkbenchKb} from '../../composables/useWorkbench';
import {useOverlayFocus} from '../../composables/useOverlayFocus';
import {useWorkspaceBusy} from '../../composables/useWorkspaceUpload';
import {useKnowledgeFileBusy} from '../../composables/useKnowledgeFileSelection';
import {useRecentKnowledge} from '../../composables/useRecentKnowledge';
import {positiveId} from '../../utils/workbench-navigation';
import {clearChatContext} from '../../router/guards';
import {apiErrorMessage} from '../../api/http';
const route=useRoute(),router=useRouter(),auth=useWorkbenchAuth(),chat=useWorkbenchChat(),models=useWorkbenchModels(),kb=useWorkbenchKb();
const uploadBusy=useWorkspaceBusy();
const fileBusy=useKnowledgeFileBusy(),{recent}=useRecentKnowledge();
const collapsed=ref(false),mobileOpen=ref(false),isMobile=ref(false),nav=ref<HTMLElement|null>(null);
const loggingOut=ref(false),logoutError=ref(''),modelsError=ref('');
const isChatRoute=computed(()=>route.path==='/app/chat');
const navigation=[{to:'/app/kbs',label:'知识库',icon:'book'}];
const chatKnowledgeLabel=computed(()=>{
 const id=positiveId(route.query.kb);
 return chat.kbs.find(base=>base.id===id)?.name||kb.kbs.find(base=>base.id===id)?.name||(id?'正在读取知识库…':'请选择知识库');
});
const currentTitle=computed(()=>{
 if(isChatRoute.value)return chat.currentSession?.title||'新会话';
 if(route.path.startsWith('/app/kbs/'))return kb.currentKb?.name||'知识库详情';
 return route.path==='/app/settings'?'模型设置':'我的知识库';
});
const modalOpen=computed(()=>isMobile.value&&mobileOpen.value);
useOverlayFocus(modalOpen,nav,()=>mobileOpen.value=false);
function isActive(path:string){return path==='/app/kbs'?route.path.startsWith(path):route.path===path}
async function newConversation(){
 if(chat.streaming||chat.loadingMessages||kb.loading||uploadBusy.value||fileBusy.value)return;
 const target=positiveId(route.query.kb);
 if(!target||!chat.kbs.some(base=>base.id===target)){clearChatContext();await router.replace('/app/kbs');return}
 await chat.newSession();
 chat.selectedKbId=target;
 await router.replace({path:'/app/chat',query:{kb:String(target)}});
}
function toggleNavigation(){if(isMobile.value)mobileOpen.value=!mobileOpen.value;else collapsed.value=!collapsed.value}
watch(()=>route.fullPath,()=>mobileOpen.value=false);
let media:MediaQueryList|null=null;
function resize(){isMobile.value=media?.matches??false;if(!isMobile.value)mobileOpen.value=false}
onMounted(async()=>{
 media=window.matchMedia('(max-width: 767px)');resize();media.addEventListener('change',resize);
 const results=await Promise.allSettled([models.load(),...(route.path==='/app/settings'?[kb.loadKbs()]:[])]);
 const modelResult=results[0];if(modelResult.status==='rejected')modelsError.value=apiErrorMessage(modelResult.reason,'模型配置读取失败');
});
onBeforeUnmount(()=>media?.removeEventListener('change',resize));
async function logout(){
 loggingOut.value=true;logoutError.value='';
 try{await auth.logout();await router.replace('/login')}
 catch(error){logoutError.value=apiErrorMessage(error,'退出失败，请重试')}
 finally{loggingOut.value=false}
}
</script>
