<template>
 <section class="kb-home page-width">
  <header class="page-head"><div><h1>我的知识库</h1><p>把资料放在一起，让每一次提问都有据可查。</p></div><button class="btn btn-primary" @click="openCreate"><Icon name="plus"/>新建知识库</button></header>
  <div class="library-toolbar"><label class="knowledge-search"><Icon name="search"/><input v-model="search" type="search" placeholder="搜索知识库名称或简介" aria-label="搜索知识库"/></label><span>{{ filtered.length }} 个知识库</span></div>
  <div v-if="error" class="error-item" role="alert">{{ error }}<button class="btn btn-ghost btn-sm" @click="load">重新加载</button></div>
  <div v-if="loading" class="library-grid" aria-label="正在加载知识库"><div v-for="index in 4" :key="index" class="library-skeleton card"><div class="skeleton"/><div class="skeleton"/><div class="skeleton"/></div></div>
  <div v-else-if="filtered.length" class="library-grid">
   <article v-for="base in filtered" :key="base.id" class="library-card">
    <RouterLink :to="{path:'/app/chat',query:{kb:String(base.id)}}" class="library-card-body" :aria-label="'进入知识库 '+base.name">
     <span class="library-icon"><Icon name="folder"/></span><h2>{{ base.name }}</h2><p>{{ base.description||'添加文档，在这里建立你的知识连接。' }}</p>
     <div class="library-card-meta"><span><Icon name="doc"/>{{ summaries[base.id]?.loading&&summaries[base.id]?.count==null?'读取文件数量…':summaries[base.id]?.count==null?'数量暂不可用':summaries[base.id].count+' 个文件' }}</span><span class="library-state" :class="stateClass(base.id)">{{ stateLabel(base.id) }}</span></div>
    </RouterLink>
    <RouterLink :to="'/app/kbs/'+base.id" class="btn-icon library-settings" title="管理知识库" :aria-label="'设置知识库 '+base.name"><Icon name="settings"/></RouterLink>
   </article>
  </div>
  <EmptyState v-else :title="search?'没有匹配的知识库':'创建你的第一个知识库'" :description="search?'试试其他名称，或清空搜索。':'上传论文、报告或笔记，然后通过问题找到资料中的答案。'" icon="book"><button v-if="!search" class="btn btn-primary" @click="openCreate"><Icon name="plus"/>新建知识库</button><button v-else class="btn btn-ghost" @click="search=''">清空搜索</button></EmptyState>
  <DialogShell :open="modalOpen" title="新建知识库" @close="closeCreate">
   <form id="create-knowledge-form" @submit.prevent="create">
    <div class="field"><label for="kb-name">知识库名称</label><input id="kb-name" v-model.trim="form.name" class="input" required maxlength="255" placeholder="例如：研究论文" :disabled="busy"/></div>
    <div class="field"><label for="kb-desc">简介 <span class="optional">可选</span></label><textarea id="kb-desc" v-model.trim="form.description" class="textarea" rows="3" placeholder="这个知识库收集哪些资料？" :disabled="busy"/></div>
    <p v-if="createError" class="error-item" role="alert">{{ createError }}</p>
   </form>
   <template #footer><button class="btn btn-ghost" :disabled="busy" @click="closeCreate">取消</button><button class="btn btn-primary" form="create-knowledge-form" type="submit" :disabled="busy||!form.name">{{ busy?'正在创建…':'创建知识库' }}</button></template>
  </DialogShell>
 </section>
</template>
<script setup lang="ts">
import {ref,reactive,computed,onMounted} from 'vue';
import Icon from '../../components/common/Icon.vue';
import EmptyState from '../../components/common/EmptyState.vue';
import DialogShell from '../../components/common/DialogShell.vue';
import {useWorkbenchKb,useWorkbenchChat} from '../../composables/useWorkbench';
import {useKbSummaries} from '../../composables/useKbSummaries';
import {apiErrorMessage} from '../../api/http';
const kb=useWorkbenchKb(),chat=useWorkbenchChat(),{summaries,refresh}=useKbSummaries();
const search=ref(''),loading=ref(false),error=ref(''),modalOpen=ref(false),busy=ref(false),createError=ref('');
const form=reactive({name:'',description:''});
const filtered=computed(()=>{const query=search.value.trim().toLowerCase();return kb.kbs.filter(base=>(base.name+' '+(base.description||'')).toLowerCase().includes(query))});
function stateLabel(id:number){const value=summaries[id];if(!value||value.loading&&value.count==null)return '读取状态';if(value.error)return '状态读取失败';if(value.active)return value.active+' 个处理中';if(value.failed)return value.failed+' 个处理失败';if(!value.count)return '等待上传';return value.ready?'可检索':'等待处理'}
function stateClass(id:number){const value=summaries[id];return value?.failed||value?.error?'failed':value?.active?'processing':value?.ready?'ready':''}
async function load(){loading.value=true;error.value='';try{const bases=await kb.loadKbs();await refresh(bases)}catch(err){error.value=apiErrorMessage(err,'知识库读取失败')}finally{loading.value=false}}
function openCreate(){form.name=form.description='';createError.value='';modalOpen.value=true}
function closeCreate(){if(!busy.value)modalOpen.value=false}
async function create(){
 if(busy.value||!form.name)return;busy.value=true;createError.value='';
 try{await kb.createKb(form.name,form.description,[]);await chat.loadKbs();modalOpen.value=false;await refresh(kb.kbs)}
 catch(err){createError.value=apiErrorMessage(err,'创建失败，请重试')}
 finally{busy.value=false}
}
onMounted(load);
</script>


