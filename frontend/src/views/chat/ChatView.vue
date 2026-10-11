<template>
 <div ref="chatLayout" class="chat-layout" :class="{'sources-open':sourcesOpen,'sources-resizing':sourcesDragging}">
  <section v-if="selectedKb&&!returningHome" v-show="!syncing" class="chat-main" aria-label="问答对话" :inert="syncing||sourcesOpen&&smallScreen">
   <div class="chat-toolbar"><span>{{ chat.streaming?'正在生成回答':chat.currentSession?'继续这段对话':'从资料开始探索' }}</span><div class="chat-toolbar-actions">
    <button v-if="chat.currentSession" class="btn-icon" title="重命名会话" @click="renameOpen=true"><Icon name="edit"/></button>
    <button v-if="chat.currentSession" class="btn-icon" title="导出会话" @click="exportCurrent"><Icon name="export"/></button>
    <button v-if="chat.currentSession" class="btn-icon danger" title="删除会话" :disabled="chat.streaming" @click="deleteOpen=true"><Icon name="trash"/></button>
    <button class="btn btn-ghost btn-sm" :aria-expanded="sourcesOpen" @click="toggleSources"><Icon name="panel"/>Sources</button>
   </div></div>
   <p v-if="readError" class="error-item chat-context-error" role="alert">{{ readError }}<button class="btn btn-ghost btn-sm" :disabled="syncing||fileBusy||sending||chat.streaming" @click="syncContext">重新读取</button></p>
   <MessageList :items="chat.items" :loading="chat.loadingMessages||!ready||syncing" :busy="chat.streaming||syncing||fileBusy" :turn="chat.turnSeq" source-panel @show-citation="openCitation" @retry="retry" @regenerate="regenerate" @feedback="feedback">
    <template #empty>
     <div class="chat-empty"><span class="chat-empty-mark"><Icon name="graph"/></span><h1>让问题，找到依据。</h1><p>从一个问题开始，连接知识库里的信息。</p>
      <div v-if="noDocuments" class="empty-library-tip"><Icon name="doc"/><span>这个知识库还没有资料。</span><RouterLink :to="'/app/kbs/'+selectedKb">上传第一份文档</RouterLink></div>
      <div class="suggestion-grid"><button v-for="suggestion in suggestions" :key="suggestion.title" @click="input?.restoreText(suggestion.question)"><Icon :name="suggestion.icon"/><span>{{ suggestion.title }}</span><small>{{ suggestion.description }}</small></button></div>
     </div>
    </template>
   </MessageList>
   <div v-if="sending&&!chat.streaming&&uploadStatus.name" class="chat-upload"><span>{{ uploadStatus.name }} / 上传 {{ fmtPercent(uploadStatus.ratio*100) }}</span><ProgressBar :value="uploadStatus.ratio*100" label="附件上传进度"/></div>
   <ChatInput ref="input" :busy="sending||!ready||syncing||!!readError||fileBusy" @send="send" @stop="chat.abort"/>
  </section>
  <p v-if="!selectedKb||syncing||returningHome" role="status">正在读取知识库和会话…</p>
  <div v-if="sourcesOpen&&smallScreen" class="sources-scrim" @click="sourcesOpen=false" aria-hidden="true"/>
  <Transition name="sources"><aside v-if="sourcesOpen" id="chat-sources" ref="sourceAside" class="sources-aside" :style="smallScreen?undefined:{width:sourcesWidth+'px'}" :role="smallScreen?'dialog':'complementary'" :aria-modal="smallScreen?true:undefined" aria-label="Sources 来源" tabindex="-1">
   <div v-if="!smallScreen" class="sources-resize-handle" role="separator" tabindex="0" aria-label="调整 Sources 宽度" aria-orientation="vertical" aria-controls="chat-sources" :aria-valuemin="320" :aria-valuemax="sourcesMaxWidth" :aria-valuenow="sourcesWidth" :aria-valuetext="sourcesWidth+' 像素'" title="拖动调整宽度，双击恢复默认"
    @pointerdown="startResize" @pointermove="moveResize" @pointerup="endResize" @pointercancel="endResize" @lostpointercapture="endResize" @keydown="keyboardResize" @dblclick="resetWidth"/>
   <CitationDialog :open="sourcesOpen" panel :chunk-id="source.chunkId" :citation="source.citation" @close="sourcesOpen=false"/>
  </aside></Transition>
  <ConfirmDialog :open="renameOpen" title="重命名会话" message="设置一个容易找到的标题。" input :initial-value="chat.currentSession?.title||''" placeholder="会话标题" confirm-text="保存" @cancel="renameOpen=false" @confirm="rename"/>
  <ConfirmDialog :open="deleteOpen" title="删除会话" message="会话中的消息与轨迹将被删除。" danger confirm-text="删除" @cancel="deleteOpen=false" @confirm="deleteCurrent"/>
 </div>
</template>
<script setup lang="ts">
import {ref,computed,onMounted,onBeforeUnmount,watch} from 'vue';
import {useRoute,useRouter} from 'vue-router';
import MessageList from '../../components/chat/MessageList.vue';
import ChatInput from '../../components/chat/ChatInput.vue';
import CitationDialog from '../../components/chat/CitationDialog.vue';
import ConfirmDialog from '../../components/common/ConfirmDialog.vue';
import Icon from '../../components/common/Icon.vue';
import ProgressBar from '../../components/common/ProgressBar.vue';
import {useWorkbenchAuth,useWorkbenchChat,useWorkbenchKb} from '../../composables/useWorkbench';
import {useWorkspaceUpload} from '../../composables/useWorkspaceUpload';
import {useKnowledgeFileBusy} from '../../composables/useKnowledgeFileSelection';
import {useOverlayFocus} from '../../composables/useOverlayFocus';
import {useSourcesResize} from '../../composables/useSourcesResize';
import {positiveId,sessionKnowledgeId} from '../../utils/workbench-navigation';
import {clearChatContext} from '../../router/guards';
import {apiErrorMessage,apiReadErrorMessage,isUnavailableResource} from '../../api/http';
import {downloadText} from '../../utils/download';
import {fmtPercent} from '../../utils/format';
import {toast} from '../../utils/toast';
import type {Citation,UploadFailure} from '../../types/workbench';
const chat=useWorkbenchChat(),kb=useWorkbenchKb(),auth=useWorkbenchAuth(),uploads=useWorkspaceUpload(),route=useRoute(),router=useRouter();
const fileBusy=useKnowledgeFileBusy();
kb.loading=true;
const input=ref<InstanceType<typeof ChatInput>|null>(null),ready=ref(false),contextError=ref(''),contextUnavailable=ref(false),syncing=ref(true),returningHome=ref(false);
const sending=ref(false),uploadStatus=ref({name:'',ratio:0});
const sourcesOpen=ref(false),smallScreen=ref(false),sourceAside=ref<HTMLElement|null>(null),renameOpen=ref(false),deleteOpen=ref(false);
const chatLayout=ref<HTMLElement|null>(null);
const {width:sourcesWidth,maxWidth:sourcesMaxWidth,dragging:sourcesDragging,startResize,moveResize,endResize,keyboardResize,resetWidth}=useSourcesResize(sourcesOpen,smallScreen,chatLayout);
const source=ref<{chunkId:string|number|null;citation:Citation|null}>({chunkId:null,citation:null});
const selectedKb=computed(()=>chat.selectedKbId);
const readError=computed(()=>contextError.value||(kb.currentKbId===selectedKb.value?kb.error:'')||'');
const noDocuments=computed(()=>ready.value&&!!selectedKb.value&&kb.currentKbId===selectedKb.value&&!kb.docs.length);
const suggestions=[
 {title:'概览核心内容',description:'梳理资料的主题与重点',question:'总结这个知识库的核心内容，并注明出处。',icon:'book'},
 {title:'寻找关键依据',description:'从原文中定位相关段落',question:'这个知识库里有哪些值得关注的结论？请给出原文依据。',icon:'search'},
 {title:'对比不同文档',description:'看清相同观点与差异',question:'对比知识库中文档的主要观点，说明相同点和差异。',icon:'graph'},
 {title:'解释一个概念',description:'结合资料，建立清晰理解',question:'解释资料中最重要的概念，并给出相关引用。',icon:'bulb'},
];
useOverlayFocus(computed(()=>sourcesOpen.value&&smallScreen.value),sourceAside,()=>sourcesOpen.value=false);
let media:MediaQueryList|null=null,contextSequence=0,active=true;
function resize(){smallScreen.value=media?.matches??false}
onMounted(async()=>{
 media=window.matchMedia('(max-width: 1099px)');resize();media.addEventListener('change',resize);
 ready.value=true;await syncContext();
});
onBeforeUnmount(()=>{active=false;contextSequence++;kb.loading=false;media?.removeEventListener('change',resize);kb.stopPolling()});
watch(()=>[route.query.kb,route.query.session],()=>{
 sourcesOpen.value=false;source.value={chunkId:null,citation:null};
 if(ready.value)syncContext();
});
watch(selectedKb,id=>{if(!id){sourcesOpen.value=false;source.value={chunkId:null,citation:null};input.value?.clear()}});
watch([()=>kb.errorStatus,contextUnavailable,fileBusy,()=>sending.value,()=>chat.streaming],([status,unavailable,saving,uploading,streaming])=>{
 const inaccessible=status===403||status===404;
 const currentKnowledge=kb.currentKbId===selectedKb.value;
 if((unavailable||inaccessible&&currentKnowledge)&&!saving&&!uploading&&!streaming)returnToHome();
});
watch(()=>chat.currentSessionId,id=>{
 if(!ready.value||syncing.value||!id||positiveId(route.query.session)===id)return;
 if(selectedKb.value)router.replace({path:'/app/chat',query:{kb:String(selectedKb.value),session:String(id)}});
});
async function returnToHome(){
 if(returningHome.value||!active||route.path!=='/app/chat')return;
 if(fileBusy.value||sending.value||chat.streaming){contextUnavailable.value=true;return}
 returningHome.value=true;contextSequence++;
 sourcesOpen.value=false;source.value={chunkId:null,citation:null};input.value?.clear();
 clearChatContext();toast('知识库或会话不存在或无法访问，请重新选择。','info');
 await router.replace('/app/kbs');
}
async function syncContext(){
 if(chat.streaming||returningHome.value)return;
 const request=++contextSequence,kbId=positiveId(route.query.kb),sessionId=positiveId(route.query.session);
 const owner=auth.user;
 const isCurrent=()=>active&&request===contextSequence&&auth.user===owner&&route.path==='/app/chat';
 syncing.value=true;kb.loading=true;contextUnavailable.value=false;
 contextError.value='';
 try{
  if(!kbId||!chat.kbs.some(base=>base.id===kbId)){await returnToHome();return}
  if(sessionId){
   const session=chat.sessions.find(item=>item.id===sessionId);
   if(!session||sessionKnowledgeId(session,chat.kbs)!==kbId){await returnToHome();return}
   chat.selectedKbId=kbId;
   if(chat.currentSessionId!==sessionId||chat.error){chat.error=null;await chat.selectSession(sessionId)}
  }else{
   if(chat.currentSessionId||chat.selectedKbId!==kbId)await chat.newSession();
   if(!isCurrent())return;
   chat.selectedKbId=kbId;
  }
  if(!isCurrent())return;
  if(kb.currentKbId!==kbId){kb.docs=[];await kb.selectKb(kbId)}
  else await kb.loadDocs();
  if(!isCurrent())return;
  contextError.value=chat.error||'';
 }catch(error){
  if(isCurrent()){
   if(isUnavailableResource(error))await returnToHome();
   else contextError.value=apiReadErrorMessage(error,'知识库或会话读取失败，请稍后重试。');
  }
 }finally{if(isCurrent()){syncing.value=false;kb.loading=false}}
}
async function send({question,files}:{question:string;files:File[]}){
 if(sending.value||chat.streaming||fileBusy.value||!ready.value||syncing.value)return;
 sending.value=true;uploadStatus.value={name:'',ratio:0};
 try{await performSend({question,files})}finally{sending.value=false;uploadStatus.value={name:'',ratio:0}}
}
async function retry(){if(!fileBusy.value&&!syncing.value&&!readError.value)await chat.retryLast()}
async function regenerate(){if(!fileBusy.value&&!syncing.value&&!readError.value)await chat.regenerate()}
async function performSend({question,files}:{question:string;files:File[]}){
 const owner=auth.user;
 if(readError.value){input.value?.restoreText(question);return}
 if(files.length){
  const target=chat.selectedKbId;
  if(!target){chat.setNotice({type:'error',text:'请先选择知识库，文档才能归库解析'});input.value?.restoreText(question);input.value?.restoreFiles(files);return}
  try{await uploads.upload(files,target,(name,ratio)=>{uploadStatus.value={name,ratio:Math.max(0,Math.min(1,ratio))}});if(!active||auth.user!==owner)return;chat.setNotice({type:'info',text:files.length+' 个文档已上传，后台正在处理。'})}
  catch(error){if(!active||auth.user!==owner)return;chat.setNotice({type:'error',text:apiErrorMessage(error,'文档上传失败')});input.value?.restoreText(question);const failed=(error as UploadFailure).failedFiles;if(failed?.length)input.value?.restoreFiles(failed);return}
 }
 if(!active||auth.user!==owner)return;
 const ok=await chat.ask(question);if(!ok&&active&&auth.user===owner)input.value?.restoreText(question);
}
function openCitation(payload:{chunkId?:string|number;chunk_id?:string|number;citation?:Citation|null}){
 const id=payload.chunkId??payload.chunk_id;if(id==null)return;source.value={chunkId:id,citation:payload.citation||null};sourcesOpen.value=true;
}
function toggleSources(){
 if(!sourcesOpen.value&&source.value.chunkId==null){const answer=[...chat.items].reverse().find(item=>item.citations?.length);const citation=answer?.citations?.[0];if(citation)source.value={chunkId:citation.chunk_id,citation}}
 sourcesOpen.value=!sourcesOpen.value;
}
async function feedback(payload:{messageId?:number;kind:'up'|'down'|null}){
 const result=await chat.setFeedback(payload.messageId,payload.kind);if(result.ok)toast(payload.kind?'反馈已保存':'已取消反馈','success');else if(result.error)toast(result.error,'error');else toast('消息尚未同步，稍后再试','info');
}
async function rename(title?:string){renameOpen.value=false;if(!chat.currentSessionId||!title?.trim())return;try{await chat.renameSession(chat.currentSessionId,title.trim())}catch(error){toast(apiErrorMessage(error),'error')}}
async function exportCurrent(){if(!chat.currentSessionId)return;try{const data=await chat.exportSession(chat.currentSessionId);downloadText(typeof data==='string'?data:data.markdown||JSON.stringify(data),'rag-session-'+chat.currentSessionId+'.md')}catch(error){toast(apiErrorMessage(error),'error')}}
async function deleteCurrent(){deleteOpen.value=false;if(!chat.currentSessionId)return;try{await chat.deleteSession(chat.currentSessionId);await router.replace(selectedKb.value?{path:'/app/chat',query:{kb:String(selectedKb.value)}}:'/app/kbs')}catch(error){toast(apiErrorMessage(error),'error')}}
</script>
