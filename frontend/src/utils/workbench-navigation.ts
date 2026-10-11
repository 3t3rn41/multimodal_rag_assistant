import type {ChatSession,KnowledgeBase} from '../types/workbench';
export function positiveId(value:unknown):number|null{
 if(typeof value!=='string'&&typeof value!=='number')return null;
 const id=Number(value);return Number.isSafeInteger(id)&&id>0?id:null;
}
export function sessionKnowledgeId(session:ChatSession,bases:KnowledgeBase[]):number|null{
 if(session.kb_ids?.length!==1)return null;
 const id=positiveId(session.kb_ids[0]);
 return id!==null&&bases.some(base=>base.id===id)?id:null;
}
export function sessionsForKb(sessions:ChatSession[],kbId:number|null):ChatSession[]{
 return kbId==null?[]:sessions.filter(session=>session.kb_ids?.length===1&&session.kb_ids[0]===kbId);
}
export function matchesActiveChat(path:string,query:Record<string,unknown>,sessionId:number|null,kbId:number|null):boolean{
 if(path!=='/app/chat'||!sessionId||positiveId(query.session)!==sessionId)return false;
 const kb=positiveId(query.kb);
 return kbId!==null&&kb===kbId;
}
