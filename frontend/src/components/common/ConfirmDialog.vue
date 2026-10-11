<template>
 <DialogShell :open="open" :title="title" @close="emit('cancel')">
  <p class="cd-message">{{ message }}</p>
  <div v-if="input" class="field" style="margin-top:20px"><label for="confirm-dialog-value">{{ placeholder||'新名称' }}</label><input id="confirm-dialog-value" v-model.trim="value" class="input" :placeholder="placeholder" @keydown.enter.prevent="confirm"/></div>
  <template #footer><button class="btn btn-ghost" @click="emit('cancel')">取消</button><button class="btn" :class="danger?'btn-danger':'btn-primary'" :disabled="input&&!value.trim()" @click="confirm">{{ confirmText }}</button></template>
 </DialogShell>
</template>
<script setup lang="ts">
import {ref,watch} from 'vue';
import DialogShell from './DialogShell.vue';
const props=withDefaults(defineProps<{open:boolean;title?:string;message?:string;confirmText?:string;danger?:boolean;input?:boolean;placeholder?:string;initialValue?:string}>(),{title:'确认',message:'',confirmText:'确认',danger:false,input:false,placeholder:'',initialValue:''});
const emit=defineEmits<{confirm:[value?:string];cancel:[]}>();
const value=ref('');
watch(()=>props.open,open=>{if(open)value.value=props.initialValue},{immediate:true});
function confirm(){if(props.input&&!value.value.trim())return;emit('confirm',props.input?value.value:undefined)}
</script>
<style scoped>.cd-message{white-space:pre-line;line-height:1.8;color:var(--ink-mute);font-size:14px}</style>
