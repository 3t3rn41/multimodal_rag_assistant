import {computed,onScopeDispose,ref,shallowReactive} from 'vue';
import {useWorkbenchAuth,useWorkbenchKb} from './useWorkbench';
import {apiErrorMessage} from '../api/http';
import type {AuthStore} from '../types/workbench';

type Owner=AuthStore['user'];
const pending=shallowReactive(new Map<symbol,Owner>());

export function hasPendingKnowledgeFiles(owner:Owner):boolean{
 return owner!==null&&Array.from(pending.values()).includes(owner);
}
export function useKnowledgeFileBusy(){
 const auth=useWorkbenchAuth();
 return computed(()=>hasPendingKnowledgeFiles(auth.user));
}

// Reuse the original enabled action. Saving is scoped to the current account.
export function useKnowledgeFileSelection(){
 const auth=useWorkbenchAuth(),kb=useWorkbenchKb(),busy=useKnowledgeFileBusy();
 const savingDoc=ref<number|null>(null),error=ref('');
 let active=true;
 onScopeDispose(()=>active=false);
 function isCurrentContext(owner:Owner,target:number):boolean{
  return active&&auth.user===owner&&kb.currentKbId===target;
 }
 async function saveChanges(target:number,docIds:number[],enabled:boolean):Promise<boolean>{
  const owner=auth.user;
  if(!owner||busy.value||kb.loading||!isCurrentContext(owner,target)||!docIds.length)return false;
  if(docIds.some(id=>!kb.docs.some(doc=>doc.file_id===id)))return false;
  const token=Symbol('knowledge-file-selection');
  pending.set(token,owner);error.value='';
  try{
   for(const docId of docIds){
    if(!isCurrentContext(owner,target))return false;
    savingDoc.value=docId;
    await kb.setDocEnabled(docId,enabled);
   }
   return isCurrentContext(owner,target);
  }catch(cause){
   if(isCurrentContext(owner,target)){
    error.value=apiErrorMessage(cause,'文件启用状态保存失败，请重试。');
    // A PATCH may have succeeded even if the following GET failed.
    try{await kb.loadDocs()}catch{/* The original store retains its refresh error. */}
   }
   return false;
  }finally{
   pending.delete(token);
   if(active)savingDoc.value=null;
  }
 }
 function setEnabled(target:number,docId:number,enabled:boolean):Promise<boolean>{
  return saveChanges(target,[docId],enabled);
 }
 function setAllEnabled(target:number,enabled:boolean):Promise<boolean>{
  const docIds=kb.docs.filter(doc=>doc.enabled!==enabled).map(doc=>doc.file_id);
  return saveChanges(target,docIds,enabled);
 }
 return {busy,savingDoc,error,setEnabled,setAllEnabled};
}
