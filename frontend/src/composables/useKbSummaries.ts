import {reactive,onBeforeUnmount} from 'vue';
import {http} from '../api/http';
import {isDocumentProcessing} from '../utils/document-task';
import type {KbDocument,KnowledgeBase} from '../types/workbench';
interface KbSummary {count:number|null;ready:number;active:number;failed:number;loading:boolean;error:boolean}
function summarizeDocuments(documents:KbDocument[]):KbSummary{
 return {count:documents.length,ready:documents.filter(doc=>doc.status==='done'&&doc.enabled&&!doc.meta?.requires_reindex).length,
 active:documents.filter(isDocumentProcessing).length,failed:documents.filter(doc=>doc.status==='failed'||doc.meta?.task_status==='FAILED').length,loading:false,error:false};
}
export function useKbSummaries(){
 const summaries=reactive<Record<number,KbSummary>>({});let generation=0,timer:ReturnType<typeof setTimeout>|null=null;
 async function refresh(bases:KnowledgeBase[]){
  const request=++generation;if(timer)clearTimeout(timer);timer=null;
  const ids=bases.map(base=>base.id),queue=[...ids];
  for(const id of ids)summaries[id]={...(summaries[id]||{count:null,ready:0,active:0,failed:0}),loading:true,error:false};
  const worker=async()=>{
   while(queue.length&&request===generation){
    const id=queue.shift()!;
    try{const {data}=await http.get<KbDocument[]>('/knowledge/'+id+'/files');if(request===generation)summaries[id]=summarizeDocuments(data)}
    catch{if(request===generation)summaries[id]={count:null,ready:0,active:0,failed:0,loading:false,error:true}}
   }
  };
  await Promise.all(Array.from({length:Math.min(4,queue.length)},worker));
  if(request===generation&&ids.some(id=>summaries[id]?.active))timer=setTimeout(()=>refresh(bases),3000);
 }
 onBeforeUnmount(()=>{generation++;if(timer)clearTimeout(timer)});
 return {summaries,refresh};
}
