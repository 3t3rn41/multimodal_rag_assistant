<template>
 <section class="knowledge-files">
  <div class="upload-area" :class="{'drag-over':dragOver,'upload-busy':uploading}" role="button" tabindex="0" :aria-disabled="uploading" aria-label="上传知识库文件" @click="pickFiles" @keydown.enter.prevent="pickFiles" @keydown.space.prevent="pickFiles" @dragover.prevent="dragOver=!uploading" @dragleave="dragOver=false" @drop.prevent="dropFiles">
   <span class="upload-icon"><Icon name="upload"/></span><div><h2>{{ uploading?'正在上传资料…':'把资料放进知识库' }}</h2><p>拖拽文件到这里，或点击选择。支持 PDF、DOCX、TXT、MD，单个文件不超过 100 MB。</p></div><span class="btn btn-ghost">选择文件</span>
   <input ref="fileInput" type="file" multiple :accept="WORKSPACE_FILE_ACCEPT" style="display:none" :disabled="uploading" @change="onFiles"/>
  </div>
  <div v-if="uploading&&uploadProgress.name" class="upload-status" role="status"><div><span>{{ uploadProgress.name }}</span><span>{{ fmtPercent(uploadProgress.ratio*100) }}</span></div><ProgressBar :value="uploadProgress.ratio*100" label="文件上传进度"/></div>
  <p v-if="uploadError" class="error-item files-error" role="alert">{{ uploadError }}</p>
  <header class="files-toolbar"><div><h2>文件</h2><span>{{ docs.length }} 个文件 / {{ enabledCount }} 个已启用<span v-if="processingCount"> / {{ processingCount }} 个处理中</span></span></div><div><button class="btn btn-ghost btn-sm" :disabled="uploading||importing" @click="urlModal=true"><Icon name="link"/>链接导入</button><button class="btn-icon" title="刷新文件状态" aria-label="刷新文件状态" @click="refresh"><Icon name="refresh"/></button></div></header>
  <p class="files-caption">处理完成且启用的文件可以参与问答。排队和处理状态会自动更新。</p>
  <p v-if="kb.error" class="error-item files-error" role="alert">{{ kb.error }}</p>
  <div v-if="docs.length" class="document-table-wrap">
   <table class="document-table"><thead><tr><th>文件名称</th><th>类型</th><th>大小</th><th>上传时间</th><th>处理状态</th><th class="chunk-count" title="文档切分后的片段数量">Chunk 数量</th><th>操作</th></tr></thead>
    <tbody><tr v-for="document in docs" :key="document.file_id">
     <td><button class="document-name" :title="document.file_name" @click="showChunks(document)"><Icon name="doc"/><span>{{ document.file_name }}</span></button></td>
     <td><span class="file-format">{{ document.file_type.toUpperCase() }}</span></td><td class="file-meta">{{ sizeLabel(document) }}</td><td class="file-meta">{{ timeLabel(document) }}</td>
     <td class="task-cell"><span class="badge" :class="task(document).cls">{{ task(document).text }}</span><div v-if="task(document).active" class="document-progress"><ProgressBar :value="task(document).progress" :label="document.file_name+' 处理进度'"/><span>{{ fmtPercent(task(document).progress) }}</span></div><p v-if="task(document).error" class="task-error" role="alert">{{ task(document).error }}</p><TaskProgress :meta="document.meta"/></td>
     <td class="chunk-count">{{ chunkCountLabel(document) }}</td>
     <td><div class="file-actions"><button class="btn btn-ghost btn-sm" :disabled="!task(document).canReparse||busyDocs.has(document.file_id)" @click="reparse(document)"><Icon name="refresh"/>{{ busyDocs.has(document.file_id)?'提交中…':task(document).reparseLabel }}</button><button class="btn-icon" title="查看内容与原文" :aria-label="'预览 '+document.file_name" @click="showChunks(document)"><Icon name="eye"/></button><button class="btn-icon" title="标记内容错误" :disabled="!isParsedDone(document.status)||busyDocs.has(document.file_id)" @click="requestCorrection(document)"><Icon name="alert"/></button><button class="btn-icon danger" title="移除文件" :aria-label="'移除 '+document.file_name" :disabled="busyDocs.has(document.file_id)" @click="requestRemove(document)"><Icon name="trash"/></button></div></td>
    </tr></tbody>
   </table>
  </div>
  <EmptyState v-else title="还没有文件" description="先上传一份包含可选中文字的 PDF，等待处理完成后开始问答。" icon="doc"/>
  <DialogShell :open="urlModal" title="从链接导入" @close="closeUrl">
   <form id="import-url-form" @submit.prevent="importUrl"><div class="field"><label for="doc-url">文档链接</label><input id="doc-url" v-model.trim="url" class="input" type="url" required placeholder="https://arxiv.org/abs/…" :disabled="importing"/><p class="field-hint">arXiv 链接会下载论文 PDF。其他网页导入能力沿用现有服务，是否可检索以处理状态为准。</p></div><p v-if="importError" class="error-item" role="alert">{{ importError }}</p></form>
   <template #footer><button class="btn btn-ghost" :disabled="importing" @click="closeUrl">取消</button><button class="btn btn-primary" form="import-url-form" type="submit" :disabled="importing||!url">{{ importing?'正在导入…':'导入文档' }}</button></template>
  </DialogShell>
  <DialogShell :open="chunkModal.open" :title="chunkModal.title" wide @close="closeChunks">
   <div v-if="chunkModal.loading" class="skeleton chunks-loading" aria-label="正在加载文档内容"/>
   <p v-else-if="chunkModal.error" class="error-item" role="alert">{{ chunkModal.error }}</p>
   <EmptyState v-else-if="!chunkModal.chunks.length" title="内容尚未就绪" description="处理完成后，这里会显示可检索的原文片段。" icon="doc"/>
   <div v-else class="chunk-list"><article v-for="chunk in chunkModal.chunks" :key="chunk.chunk_id"><header><span>{{ sourceLabel(chunk) }}</span><span v-if="chunk.page">第 {{ chunk.page }} 页</span><span v-else-if="chunk.time_start!=null">{{ chunk.time_start }} 秒<span v-if="chunk.time_end!=null">–{{ chunk.time_end }} 秒</span></span><span v-else>原文片段 {{ chunk.seq??'' }}</span><button class="btn btn-ghost btn-sm" @click="openOriginal(chunk)"><Icon name="external"/>查看原文</button></header><p>{{ chunk.content }}</p></article></div>
  </DialogShell>
  <CitationDialog :open="source.open" :chunk-id="source.chunkId" :citation="source.citation" @close="source.open=false"/>
  <ConfirmDialog :open="dialog.open" :title="confirmation.title" :message="confirmation.message" danger :confirm-text="confirmation.action" @cancel="dialog.open=false" @confirm="confirm"/>
 </section>
</template>
<script setup lang="ts">
import {ref,computed,onMounted,onBeforeUnmount} from 'vue';
import {onBeforeRouteLeave,onBeforeRouteUpdate} from 'vue-router';
import Icon from '../../components/common/Icon.vue';
import DialogShell from '../../components/common/DialogShell.vue';
import ConfirmDialog from '../../components/common/ConfirmDialog.vue';
import EmptyState from '../../components/common/EmptyState.vue';
import ProgressBar from '../../components/common/ProgressBar.vue';
import TaskProgress from '../../components/common/TaskProgress.vue';
import CitationDialog from '../../components/chat/CitationDialog.vue';
import {useWorkbenchAuth,useWorkbenchKb} from '../../composables/useWorkbench';
import {useWorkspaceUpload} from '../../composables/useWorkspaceUpload';
import {http,apiErrorMessage} from '../../api/http';
import {isParsedDone,fmtBytes,fmtTime,fmtNumber,fmtPercent} from '../../utils/format';
import {documentTaskView,isDocumentProcessing} from '../../utils/document-task';
import {acceptedUploads,WORKSPACE_FILE_ACCEPT} from '../../utils/workspace-files';
import {toast} from '../../utils/toast';
import type {KbDocument,Citation} from '../../types/workbench';
interface Chunk {chunk_id:string;file_id:string;source_type:string;content:string;seq?:number;page?:number;time_start?:number|null;time_end?:number|null;media_path?:string|null;extra?:Record<string,unknown>;generation:number}
const kb=useWorkbenchKb(),auth=useWorkbenchAuth(),uploads=useWorkspaceUpload(),docs=computed(()=>kb.docs),enabledCount=computed(()=>docs.value.filter(document=>document.enabled).length),processingCount=computed(()=>docs.value.filter(isDocumentProcessing).length);
const fileInput=ref<HTMLInputElement|null>(null),uploading=ref(false),dragOver=ref(false),uploadError=ref(''),uploadProgress=ref({name:'',ratio:0});
const urlModal=ref(false),url=ref(''),importing=ref(false),importError=ref(''),busyDocs=ref(new Set<number>());
const chunkModal=ref<{open:boolean;title:string;chunks:Chunk[];loading:boolean;error:string}>({open:false,title:'',chunks:[],loading:false,error:''});
const source=ref<{open:boolean;chunkId:string|number|null;citation:Citation|null}>({open:false,chunkId:null,citation:null});
const dialog=ref<{open:boolean;mode:string;target:KbDocument|null;kbId:number|null}>({open:false,mode:'',target:null,kbId:null});let previewSequence=0;
const confirmations = {
 remove: {title:'移除文件',message:'将文件移出当前知识库。若其他知识库未使用该文件，会永久清理文件资源；历史对话文字保留，清理后的来源无法预览。确认移除？',action:'移除'},
 correction: {title:'标记内容错误',message:'这会记录内容错误反馈，文件启用状态保持不变。确认提交反馈？',action:'确认标记'},
};
const confirmation = computed(() => confirmations[dialog.value.mode as keyof typeof confirmations] || confirmations.correction);
const task=(document:KbDocument)=>documentTaskView(document);
function sizeLabel(document:KbDocument){const size=document.file_size;return typeof size==='number'?fmtBytes(size):'-'}
function timeLabel(document:KbDocument){return fmtTime(document.upload_time)||'-'}
function chunkCountLabel(document:KbDocument){const count=document.meta?.chunk_count;return typeof count==='number'&&Number.isSafeInteger(count)&&count>=0?fmtNumber(count):'-'}
function pickFiles(){if(!uploading.value)fileInput.value?.click()}
function onFiles(event:Event){const element=event.target as HTMLInputElement;const files=Array.from(element.files||[]);element.value='';upload(files)}
function dropFiles(event:DragEvent){dragOver.value=false;upload(Array.from(event.dataTransfer?.files||[]))}
async function upload(files:File[]){
 if(uploading.value||importing.value||!kb.currentKbId)return;const result=acceptedUploads(files);uploadError.value=result.rejected.join(' ');if(!result.accepted.length)return;
 uploading.value=true;uploadProgress.value={name:result.accepted[0].name,ratio:0};
 try{await uploads.upload(result.accepted,kb.currentKbId,(name,ratio)=>uploadProgress.value={name,ratio:Math.max(0,Math.min(1,ratio))});toast('文件已上传，后台开始处理。','success')}
 catch(error){uploadError.value=apiErrorMessage(error,'上传失败，请重试')}
 finally{uploading.value=false;uploadProgress.value={name:'',ratio:0}}
}
async function refresh(){try{await kb.loadDocs()}catch(error){toast(apiErrorMessage(error,'文件状态刷新失败'),'error')}}
function closeUrl(){if(!importing.value){urlModal.value=false;importError.value=''}}
async function importUrl(){
 if(importing.value)return;importing.value=true;importError.value='';
 try{await uploads.importUrl(url.value);url.value='';urlModal.value=false;toast('链接已导入，请查看文件处理状态。','success')}
 catch(error){importError.value=apiErrorMessage(error,'导入失败')}
 finally{importing.value=false}
}
async function reparse(document:KbDocument){
 if(busyDocs.value.has(document.file_id))return;busyDocs.value.add(document.file_id);
 try{await kb.reparse(document.file_id);toast('已提交后台处理。','success')}
 catch(error){toast(apiErrorMessage(error,'处理提交失败'),'error')}
 finally{busyDocs.value.delete(document.file_id)}
}
function requestRemove(document:KbDocument){dialog.value={open:true,mode:'remove',target:document,kbId:kb.currentKbId}}
function requestCorrection(document:KbDocument){dialog.value={open:true,mode:'correction',target:document,kbId:kb.currentKbId}}
async function confirm(){
 const {mode,target,kbId} = dialog.value;
 dialog.value.open = false;
 if (!target||kbId==null||busyDocs.value.has(target.file_id)) return;
 busyDocs.value.add(target.file_id);
 try {
  if (mode === 'remove') {
   await kb.removeDoc(kbId,target.file_id);
   toast('已移出知识库','success');
  } else {
   if(kb.currentKbId!==kbId)throw new Error('知识库已切换，请重新选择文件。');
   await kb.reportCorrection(target.file_id);
   toast('已标记内容错误','success');
  }
 } catch (error) {
  toast(apiErrorMessage(error),'error');
  await refresh();
 } finally {
  busyDocs.value.delete(target.file_id);
 }
}
function closeChunks(){previewSequence++;chunkModal.value.open=false}
async function showChunks(document:KbDocument){
 const request=++previewSequence;chunkModal.value={open:true,title:document.file_name,chunks:[],loading:true,error:''};
 try{const {data}=await http.get<Chunk[]>('/files/'+document.file_id+'/chunks');if(request===previewSequence)chunkModal.value.chunks=data}
 catch(error){if(request===previewSequence)chunkModal.value.error=apiErrorMessage(error,'原文内容读取失败')}
 finally{if(request===previewSequence)chunkModal.value.loading=false}
}
function sourceLabel(chunk:Chunk){return ({document:'文档',image:'图片',audio:'音频',video:'视频'} as Record<string,string>)[chunk.source_type]||'资料'}
function openOriginal(chunk:Chunk){const title=chunkModal.value.title,id=chunk.chunk_id;closeChunks();source.value={open:true,chunkId:id,citation:{chunk_id:id,doc_title:title,page:chunk.page,source_type:chunk.source_type,time_start:chunk.time_start??undefined,time_end:chunk.time_end??undefined,media_path:chunk.media_path??undefined,preview:chunk.content}}}
onMounted(()=>kb.loadDocs().catch(()=>{}));
function guardNavigation(){if(auth.user&&(uploading.value||importing.value)){toast('文件正在上传或导入，请等待完成。','info');return false}}
onBeforeRouteLeave(guardNavigation);onBeforeRouteUpdate(guardNavigation);
onBeforeUnmount(()=>{previewSequence++;kb.stopPolling()});
</script>

