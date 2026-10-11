<template>
 <section class="page-width kb-detail-page">
  <RouterLink to="/app/kbs" class="back-link"><Icon name="chevronLeft"/>返回知识库</RouterLink>
  <div v-if="loading" class="detail-loading" aria-label="正在加载知识库"><div class="skeleton"/><div class="skeleton"/></div>
  <p v-else-if="error" class="error-item" role="alert">{{ error }}<button class="btn btn-ghost btn-sm" @click="load">重新加载</button></p>
  <template v-else-if="current">
   <header class="page-head"><div class="detail-title"><span class="library-icon"><Icon name="folder"/></span><div><h1>{{ current.name }}</h1><p>{{ current.description||'为这个知识库添加简介，说明资料的主题。' }}</p><span class="detail-file-count">{{ kb.docs.length }} 个文件</span></div></div><div class="page-actions"><button class="btn btn-ghost" @click="openEdit"><Icon name="edit"/>编辑资料</button><RouterLink :to="{path:'/app/chat',query:{kb:String(current.id)}}" class="btn btn-primary"><Icon name="chat"/>进入问答</RouterLink></div></header>
   <KbDocsTab :inert="deleting"/>
   <section class="knowledge-danger"><div><h2>删除知识库</h2><p>其他知识库仍在使用的文件会保留，其余文件资源将永久清理。历史对话文字保留。</p></div><button class="btn btn-danger" :disabled="deleting||uploadBusy" @click="deleteOpen=true"><Icon name="trash"/>删除知识库</button></section>
  </template>
  <DialogShell :open="editOpen" title="编辑知识库" @close="closeEdit">
   <form id="edit-knowledge-form" @submit.prevent="save"><div class="field"><label for="kb-name">知识库名称</label><input id="kb-name" v-model.trim="form.name" class="input" required maxlength="255" :disabled="saving"/></div><div class="field"><label for="kb-desc">简介</label><textarea id="kb-desc" v-model.trim="form.description" class="textarea" rows="4" :disabled="saving"/></div><p v-if="editError" class="error-item" role="alert">{{ editError }}</p></form>
   <template #footer><button class="btn btn-ghost" :disabled="saving" @click="closeEdit">取消</button><button type="submit" form="edit-knowledge-form" class="btn btn-primary" :disabled="saving||!form.name">{{ saving?'正在保存…':'保存修改' }}</button></template>
  </DialogShell>
  <ConfirmDialog :open="deleteOpen" title="删除知识库" message="删除知识库及其文档关联。其他知识库仍在使用的文件会保留，其余文件资源将永久清理；历史对话文字保留。此操作不能直接撤销。" danger confirm-text="删除知识库" @cancel="deleteOpen=false" @confirm="remove"/>
 </section>
</template>
<script setup lang="ts">
import {ref,reactive,computed,watch,onBeforeUnmount} from 'vue';
import {useRoute,useRouter} from 'vue-router';
import Icon from '../../components/common/Icon.vue';
import DialogShell from '../../components/common/DialogShell.vue';
import ConfirmDialog from '../../components/common/ConfirmDialog.vue';
import KbDocsTab from './KbDocsTab.vue';
import {useWorkbenchKb,useWorkbenchChat} from '../../composables/useWorkbench';
import {positiveId} from '../../utils/workbench-navigation';
import {useWorkspaceBusy} from '../../composables/useWorkspaceUpload';
import {apiErrorMessage} from '../../api/http';
import {toast} from '../../utils/toast';
const route=useRoute(),router=useRouter(),kb=useWorkbenchKb(),chat=useWorkbenchChat();
const uploadBusy=useWorkspaceBusy();
const loading=ref(true),error=ref(''),editOpen=ref(false),editError=ref(''),saving=ref(false),deleteOpen=ref(false),deleting=ref(false);
const form=reactive({name:'',description:''}),id=computed(()=>positiveId(route.params.id));
const current=computed(()=>kb.currentKb?.id===id.value?kb.currentKb:null);let sequence=0;
async function load(){
 const request=++sequence;loading.value=true;error.value='';
 try{await kb.loadKbs();if(request!==sequence)return;if(!id.value||!kb.kbs.some(base=>base.id===id.value))throw Error('知识库不存在或无法访问。');await kb.selectKb(id.value)}
 catch(err){if(request===sequence)error.value=apiErrorMessage(err,'知识库读取失败')}
 finally{if(request===sequence)loading.value=false}
}
watch(id,load,{immediate:true});onBeforeUnmount(()=>{sequence++;kb.stopPolling()});
function openEdit(){if(!current.value)return;form.name=current.value.name;form.description=current.value.description||'';editError.value='';editOpen.value=true}
function closeEdit(){if(!saving.value)editOpen.value=false}
async function save(){
 if(!id.value||!form.name||saving.value)return;saving.value=true;editError.value='';
 try{await kb.updateKb(id.value,{name:form.name,description:form.description||null});await chat.loadKbs();editOpen.value=false;toast('知识库资料已更新','success')}
 catch(err){editError.value=apiErrorMessage(err,'保存失败')}
 finally{saving.value=false}
}
async function remove(){
 if(!id.value||deleting.value||uploadBusy.value)return;deleteOpen.value=false;deleting.value=true;
 try{await kb.deleteKb(id.value);await chat.loadKbs();await router.push('/app/kbs')}
 catch(err){error.value=apiErrorMessage(err,'删除失败')}
 finally{deleting.value=false}
}
</script>

