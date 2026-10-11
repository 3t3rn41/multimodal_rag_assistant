<template>
 <div class="chat-input-wrap">
  <div class="chat-input-box" :class="{'drag-over':dragOver}" @dragover.prevent="dragOver=!uploadDisabled" @dragleave="dragOver=false" @drop.prevent="onDrop">
   <div v-if="files.length" class="ci-files"><span v-for="(file,index) in files" :key="index" class="ci-file"><Icon name="doc"/><span class="fname">{{ file.name }}</span><span class="fsize">{{ fmtBytes(file.size) }}</span><button class="btn-icon" :disabled="streaming" aria-label="移除附件" @click="files.splice(index,1)"><Icon name="x"/></button></span></div>
   <textarea ref="ta" v-model="text" class="ci-textarea" rows="2" placeholder="向你的知识库提问…" aria-label="输入问题" maxlength="4000" @input="autoGrow" @keydown="onKeydown" @paste="onPaste"/>
   <p v-if="fileError" class="ci-file-error" role="alert">{{ fileError }}</p>
   <div class="ci-bar">
    <label class="ci-attach btn-icon" :class="{disabled:uploadDisabled}" title="上传文档（将归入所选知识库）" aria-label="添加附件" role="button" tabindex="0" :aria-disabled="uploadDisabled" @click.prevent="onUploadClick" @keydown.enter.prevent="onUploadClick" @keydown.space.prevent="onUploadClick"><Icon name="attachment"/><input ref="fileInput" type="file" multiple :accept="WORKSPACE_FILE_ACCEPT" style="display:none" :disabled="uploadDisabled" @change="onFiles"/></label>
    <div class="ci-scope"><span v-if="scopeName" class="ci-scope-label"><Icon name="book"/>{{ scopeName }}</span><span v-else class="scope-empty">请先选择知识库</span></div>
    <button class="ci-send" :class="{stop:streaming}" :disabled="!canSend&&!streaming" :title="streaming?'停止生成':'发送'" :aria-label="streaming?'停止生成':'发送问题'" @click="streaming?emit('stop'):onSend()"><Icon :name="streaming?'stop':'send'"/></button>
   </div>
  </div>
  <div class="composer-caption"><span>回答以原文引用为依据，请核实关键信息。</span><span class="ci-key-hint">Enter 发送 / Shift+Enter 换行</span></div>
 </div>
</template>
<script setup lang="ts">
import {ref,computed,nextTick} from 'vue';
import Icon from '../common/Icon.vue';
import {useWorkbenchChat} from '../../composables/useWorkbench';
import {fmtBytes} from '../../utils/format';
import {acceptedUploads,WORKSPACE_FILE_ACCEPT} from '../../utils/workspace-files';
const props=withDefaults(defineProps<{busy?:boolean}>(),{busy:false});
const chat=useWorkbenchChat(),emit=defineEmits<{send:[payload:{question:string;files:File[]}];stop:[]}>();
const text=ref(''),ta=ref<HTMLTextAreaElement|null>(null),fileInput=ref<HTMLInputElement|null>(null);
const files=ref<File[]>([]),dragOver=ref(false),fileError=ref('');
const streaming=computed(()=>chat.streaming),uploadDisabled=computed(()=>streaming.value||props.busy||!chat.selectedKbId),canSend=computed(()=>!!text.value.trim()&&chat.canAsk&&!props.busy);
const scopeName=computed(()=>chat.kbs.find(base=>base.id===chat.selectedKbId)?.name||'');
function autoGrow(){const element=ta.value;if(!element)return;element.style.height='auto';element.style.height=Math.min(element.scrollHeight,180)+'px'}
function onKeydown(event:KeyboardEvent){if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();if(canSend.value)onSend()}}
function addFiles(selected:File[]){if(uploadDisabled.value)return;const result=acceptedUploads(selected);files.value.push(...result.accepted);fileError.value=result.rejected.join(' ')}
function onFiles(event:Event){const input=event.target as HTMLInputElement;addFiles(Array.from(input.files||[]));input.value=''}
function onUploadClick(){if(!uploadDisabled.value)fileInput.value?.click()}
function onPaste(event:ClipboardEvent){if(event.clipboardData?.files.length)addFiles(Array.from(event.clipboardData.files))}
function onDrop(event:DragEvent){dragOver.value=false;addFiles(Array.from(event.dataTransfer?.files||[]))}
function onSend(){const question=text.value.trim();if(!question||!canSend.value)return;emit('send',{question,files:[...files.value]});text.value='';files.value=[];fileError.value='';nextTick(autoGrow)}
function restoreText(question:string){text.value=question;nextTick(()=>{autoGrow();ta.value?.focus()})}
function restoreFiles(pending:File[]){files.value.push(...pending)}
function clear(){text.value='';files.value=[];fileError.value='';nextTick(autoGrow)}
defineExpose({clear,restoreText,restoreFiles});
</script>
