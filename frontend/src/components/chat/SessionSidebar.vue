<template>
 <div class="sb-panel">
  <button class="btn btn-primary sb-new" :disabled="blocked" @click="newConversation"><Icon name="plus"/>新建会话</button>
  <details class="scope-picker">
   <summary :title="scopeLabel"><Icon name="book"/><span>{{ scopeLabel }}</span><Icon name="chevronDown"/></summary>
   <div class="scope-picker-body">
    <p v-if="kb.loading||activeKb&&kb.currentKbId!==activeKb" class="scope-hint" role="status">正在读取知识库文件…</p>
    <template v-else>
     <div v-if="kb.error||selectionError" class="scope-error" role="alert"><span>{{ selectionError||kb.error }}</span><button :disabled="blocked" @click="refreshFiles">重新读取</button></div>
     <template v-if="documents.length">
      <div class="scope-files-meta">
       <label class="scope-select-all">
        <input type="checkbox" :checked="allEnabled" :indeterminate="partlyEnabled" :disabled="blocked||!!kb.error" aria-label="全选知识库文件" @change="toggleAllFiles"/>
        <span>全选</span>
       </label>
       <span>已启用 {{ enabledCount }} / {{ documents.length }}</span>
      </div>
      <div class="scope-picker-list" aria-label="知识库检索文件">
       <label v-for="doc in documents" :key="doc.file_id" class="scope-file" :class="{'scope-file-off':!doc.enabled}">
        <input type="checkbox" :checked="doc.enabled" :disabled="blocked||!!kb.error" :aria-label="'启用 '+doc.file_name" @change="toggleFile(doc,$event)"/>
        <Icon name="doc"/><span class="scope-file-info"><span class="scope-file-name" :title="doc.file_name">{{ doc.file_name }}</span><small :class="{'scope-file-failed':fileStatus(doc).failed}">{{ savingDoc===doc.file_id?'正在保存…':fileStatus(doc).label }}</small></span>
       </label>
      </div>
      <p class="scope-hint">勾选需要检索的文件。</p>
      <p v-if="!enabledCount" class="scope-empty-note" role="status">尚未启用文件，请勾选后再提问。</p>
     </template>
     <p v-else-if="!kb.error" class="scope-hint">还没有文件，先到知识库详情上传资料。</p>
    </template>
   </div>
  </details>
  <div class="sb-label">历史会话</div>
  <div class="sb-sessions">
   <template v-if="chat.loadingSessions"><div v-for="index in 4" :key="index" class="skeleton session-skeleton"/></template>
   <div v-for="session in sessions" :key="session.id" class="sb-session" :class="{active:session.id===chat.currentSessionId}">
    <button class="session-link" :disabled="blocked" :title="session.title||'未命名会话'" @click="select(session)"><Icon name="chat"/><span class="s-title">{{ session.title||'未命名会话' }}</span></button>
    <button class="btn-icon s-menu" :aria-label="'管理会话 '+(session.title||'未命名会话')" :aria-expanded="menuId===session.id" :disabled="blocked" @click="menuId=menuId===session.id?null:session.id"><Icon name="more"/></button>
    <div v-if="menuId===session.id" class="session-menu"><button @click="rename(session)"><Icon name="edit"/>重命名</button><button @click="exportSession(session)"><Icon name="export"/>导出 Markdown</button><button class="danger" @click="remove(session)"><Icon name="trash"/>删除会话</button></div>
   </div>
   <p v-if="!sessions.length&&!chat.loadingSessions" class="sessions-empty">你的提问会保存在这里。</p>
  </div>
  <RouterLink v-if="activeKb" :to="'/app/kbs/'+activeKb" class="sidebar-manage"><Icon name="settings"/>管理知识库文件<Icon name="chevronRight"/></RouterLink>
  <ConfirmDialog :open="dialog.open" :title="dialog.mode==='rename'?'重命名会话':'删除会话'" :message="dialog.mode==='rename'?'为这段对话设置一个容易找到的名字。':'删除后，该会话的消息和轨迹会一并删除。'" :input="dialog.mode==='rename'" :danger="dialog.mode==='delete'" :initial-value="dialog.session?.title||''" :confirm-text="dialog.mode==='rename'?'保存':'删除'" placeholder="会话名称" @cancel="dialog.open=false" @confirm="confirm"/>
 </div>
</template>
<script setup lang="ts">
import {computed,ref,watch} from 'vue';
import {useRoute,useRouter} from 'vue-router';
import Icon from '../common/Icon.vue';
import ConfirmDialog from '../common/ConfirmDialog.vue';
import {useWorkbenchChat,useWorkbenchKb} from '../../composables/useWorkbench';
import {useWorkspaceBusy} from '../../composables/useWorkspaceUpload';
import {useKnowledgeFileSelection} from '../../composables/useKnowledgeFileSelection';
import {positiveId,sessionsForKb,sessionKnowledgeId} from '../../utils/workbench-navigation';
import {documentTaskView,isDocumentProcessing} from '../../utils/document-task';
import {apiErrorMessage} from '../../api/http';
import {downloadText} from '../../utils/download';
import {toast} from '../../utils/toast';
import type {ChatSession,KbDocument} from '../../types/workbench';
const chat=useWorkbenchChat(),kb=useWorkbenchKb(),route=useRoute(),router=useRouter(),emit=defineEmits<{'new-session':[]}>();
const {busy:fileBusy,savingDoc,error:selectionError,setEnabled,setAllEnabled}=useKnowledgeFileSelection();
const uploadBusy=useWorkspaceBusy(),blocked=computed(()=>chat.streaming||chat.loadingMessages||kb.loading||uploadBusy.value||fileBusy.value);
const menuId=ref<number|null>(null),dialog=ref<{open:boolean;mode:string;session:ChatSession|null}>({open:false,mode:'',session:null});
const activeKb=computed(()=>positiveId(route.query.kb));
const sessions=computed(()=>sessionsForKb(chat.sessions,activeKb.value));
const scopeLabel=computed(()=>chat.kbs.find(base=>base.id===activeKb.value)?.name||kb.kbs.find(base=>base.id===activeKb.value)?.name||(activeKb.value?'正在读取知识库…':'选择知识库'));
const documents=computed(()=>!kb.loading&&kb.currentKbId===activeKb.value?kb.docs:[]);
const enabledCount=computed(()=>documents.value.filter(doc=>doc.enabled).length);
const allEnabled=computed(()=>documents.value.length>0&&enabledCount.value===documents.value.length);
const partlyEnabled=computed(()=>enabledCount.value>0&&!allEnabled.value);
watch(()=>route.fullPath,()=>{menuId.value=null;selectionError.value=''});
function fileStatus(doc:KbDocument){
 if(documentTaskView(doc).failed)return {label:'处理失败 · 暂不可检索',failed:true};
 if(isDocumentProcessing(doc))return {label:'处理中 · 完成后可检索',failed:false};
 if(doc.status==='done')return {label:doc.enabled?'可检索':'已停用',failed:false};
 return {label:'等待处理',failed:false};
}
async function toggleFile(doc:KbDocument,event:Event){
 const checkbox=event.target as HTMLInputElement,enabled=checkbox.checked;
 checkbox.checked=doc.enabled;
 if(blocked.value||kb.error||!activeKb.value)return;
 await setEnabled(activeKb.value,doc.file_id,enabled);
}
async function toggleAllFiles(event:Event){
 const checkbox=event.target as HTMLInputElement,enabled=checkbox.checked;
 checkbox.checked=allEnabled.value;
 checkbox.indeterminate=partlyEnabled.value;
 if(blocked.value||kb.error||!activeKb.value)return;
 await setAllEnabled(activeKb.value,enabled);
}
async function refreshFiles(){
 if(blocked.value||kb.currentKbId!==activeKb.value)return;
 kb.loading=true;selectionError.value='';
 try{await kb.loadDocs()}catch(error){selectionError.value=apiErrorMessage(error,'文件读取失败，请重试')}finally{kb.loading=false}
}
function select(session:ChatSession){if(blocked.value)return;const kb=sessionKnowledgeId(session,chat.kbs);if(!kb||kb!==activeKb.value){router.replace('/app/kbs');return}router.push({path:'/app/chat',query:{kb:String(kb),session:String(session.id)}})}
function newConversation(){if(blocked.value)return;emit('new-session')}
function rename(session:ChatSession){menuId.value=null;dialog.value={open:true,mode:'rename',session}}
function remove(session:ChatSession){menuId.value=null;dialog.value={open:true,mode:'delete',session}}
async function confirm(value?:string){
 const {mode,session}=dialog.value;if(!session||blocked.value)return;dialog.value.open=false;
 try{if(mode==='rename'&&value?.trim())await chat.renameSession(session.id,value.trim());else if(mode==='delete'){await chat.deleteSession(session.id);if(positiveId(route.query.session)===session.id)await router.replace(activeKb.value?{path:'/app/chat',query:{kb:String(activeKb.value)}}:'/app/kbs')}toast(mode==='rename'?'会话已重命名':'会话已删除','success')}
 catch(error){toast(apiErrorMessage(error,'操作失败'),'error')}
}
async function exportSession(session:ChatSession){
 menuId.value=null;try{const data=await chat.exportSession(session.id);downloadText(typeof data==='string'?data:data.markdown||JSON.stringify(data),'rag-'+session.id+'.md')}
 catch(error){toast(apiErrorMessage(error,'导出失败'),'error')}
}
</script>
