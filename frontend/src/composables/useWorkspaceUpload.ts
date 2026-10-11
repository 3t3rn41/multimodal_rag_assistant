import {computed,onScopeDispose,shallowReactive} from 'vue';
import {useWorkbenchAuth,useWorkbenchKb} from './useWorkbench';
import {apiErrorMessage} from '../api/http';
import type {AuthStore} from '../types/workbench';

type Owner=AuthStore['user'];
// A local presentation lock. The original Pinia actions still own all requests.
const uploads=shallowReactive(new Map<symbol,Owner>());
export function hasWorkspaceUpload(owner:Owner):boolean{
 return owner!==null&&Array.from(uploads.values()).includes(owner);
}
export function useWorkspaceBusy(){
 const auth=useWorkbenchAuth();
 return computed(()=>hasWorkspaceUpload(auth.user));
}
export function useWorkspaceUpload(){
 const auth=useWorkbenchAuth(),kb=useWorkbenchKb();
 let disposed=false;
 onScopeDispose(()=>disposed=true);
 function contextError(owner:Owner,target:number|null){
  if(disposed||!owner||auth.user!==owner)return '账号或页面已切换，剩余文件未继续上传。';
  if(kb.currentKbId!==target)return '知识库已切换，剩余文件未继续上传。';
  return null;
 }
 async function withLock<T>(operation:(owner:Owner)=>Promise<T>):Promise<T>{
  const owner=auth.user;
  if(!owner)throw new Error('请先登录。');
  if(hasWorkspaceUpload(owner))throw new Error('请等待当前文件上传完成。');
  const token=Symbol('workspace-upload');uploads.set(token,owner);
  try{return await operation(owner)}finally{uploads.delete(token)}
 }
 async function upload(files:File[],target:number,progress?:(name:string,ratio:number)=>void){
  return withLock(async owner=>{
   const added:unknown[]=[],failed:File[]=[];let lastError='';
   const fail=(message:string,remaining:File[]=[])=>Object.assign(new Error(message),{failedFiles:[...failed,...remaining]});
   try{if(kb.currentKbId!==target)await kb.selectKb(target)}
   catch(error){throw fail(apiErrorMessage(error,'知识库读取失败'),files)}
   for(let index=0;index<files.length;index++){
    const changed=contextError(owner,target);if(changed)throw fail(changed,files.slice(index));
    try{added.push(...await kb.uploadFiles([files[index]],progress))}
    catch(error){failed.push(files[index]);lastError=apiErrorMessage(error,'文件上传失败')}
    const changedAfter=contextError(owner,target);if(changedAfter)throw fail(changedAfter,files.slice(index+1));
   }
   if(failed.length)throw fail(lastError);
   return added;
  });
 }
 async function importUrl(url:string){
  return withLock(async owner=>{
   const target=kb.currentKbId,changed=contextError(owner,target);
   if(changed)throw new Error(changed);
   if(!target)throw new Error('请先选择知识库。');
   const result=await kb.uploadUrl(url);
   const changedAfter=contextError(owner,target);if(changedAfter)throw new Error(changedAfter);
   return result;
  });
 }
 return {upload,importUrl};
}
