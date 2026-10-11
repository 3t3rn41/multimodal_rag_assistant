import {computed,ref,watch} from 'vue';
import {useRoute} from 'vue-router';
import {useWorkbenchAuth,useWorkbenchChat,useWorkbenchKb} from './useWorkbench';
import {positiveId} from '../utils/workbench-navigation';

interface RecentVisit {id:number;usedAt:number}
const LIMIT=5;
const recentKnowledgeKey=(ownerId:number)=>'mmrag:recent-knowledge:'+ownerId;

function readRecentKnowledge(storage:Pick<Storage,'getItem'>,ownerId:number):RecentVisit[]{
 try{
  const value:unknown=JSON.parse(storage.getItem(recentKnowledgeKey(ownerId))||'[]');
  if(!Array.isArray(value))return [];
  const seen=new Set<number>();
  return value.filter((item):item is RecentVisit=>{
   if(!item||typeof item!=='object')return false;
   const {id,usedAt}=item as Partial<RecentVisit>;
   if(positiveId(id)!==id||typeof usedAt!=='number'||!Number.isFinite(usedAt)||usedAt<=0||seen.has(id!))return false;
   seen.add(id!);return true;
  }).sort((a,b)=>b.usedAt-a.usedAt).slice(0,LIMIT);
 }catch{return []}
}

export function useRecentKnowledge(){
 const auth=useWorkbenchAuth(),kb=useWorkbenchKb(),chat=useWorkbenchChat(),route=useRoute();
 const visits=ref<RecentVisit[]>([]);
 const bases=computed(()=>kb.kbs.length?kb.kbs:chat.kbs);
 let lastVisit='';
 watch(()=>auth.user?.id,id=>{
  lastVisit='';visits.value=[];
  if(positiveId(id))try{visits.value=readRecentKnowledge(window.localStorage,id!)}catch{/* Storage can be unavailable. */}
 },{immediate:true});
 watch([()=>route.fullPath,()=>auth.user?.id,bases],()=>{
  const owner=positiveId(auth.user?.id);
  const id=route.path==='/app/chat'?positiveId(route.query.kb):route.path.startsWith('/app/kbs/')?positiveId(route.params.id):null;
  if(!owner||!id||!bases.value.some(base=>base.id===id))return;
  const key=owner+':'+route.fullPath;
  if(lastVisit===key)return;
  lastVisit=key;
  visits.value=[{id,usedAt:Date.now()},...visits.value.filter(item=>item.id!==id)].slice(0,LIMIT);
  try{window.localStorage.setItem(recentKnowledgeKey(owner),JSON.stringify(visits.value))}catch{/* Navigation still works without storage. */}
 },{immediate:true});
 const recent=computed(()=>visits.value.flatMap(visit=>{
  const base=bases.value.find(item=>item.id===visit.id);return base?[base]:[];
 }));
 return {recent};
}
