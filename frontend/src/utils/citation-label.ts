import type {Citation} from '../types/workbench';
import {extractCitations} from './markdown';
export function citationLabel(citation:Citation):string{
 const name=citation.doc_title||citation.file_name||'文档';
 if(citation.page)return name+' · 第'+citation.page+'页';
 const start=citation.time_start,end=citation.time_end;
 if((citation.source_type==='video'||citation.source_type==='audio')&&typeof start==='number'&&typeof end==='number'){
  const format=(seconds:number)=>String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(Math.floor(seconds%60)).padStart(2,'0');
  return name+' · '+format(start)+'-'+format(end);
 }
 return name;
}
export function numberedCitations(content:string,citations:Citation[]):{citation:Citation;number:number}[]{
 const trusted=new Map(citations.map(citation=>[String(citation.chunk_id),citation]));
 const ids=[...new Set([...extractCitations(content),...trusted.keys()])].filter(id=>trusted.has(id));
 return ids.map((id,index)=>({citation:trusted.get(id)!,number:index+1}));
}
export function decorateCitationNumbers(html:string,content:string,citations:Citation[]):string{
 const indexed=new Map(numberedCitations(content,citations).map(item=>[String(item.citation.chunk_id),item]));
 const template=document.createElement('template');template.innerHTML=html;
 for(const node of template.content.querySelectorAll<HTMLElement>('.cite-slot')){
  const item=indexed.get(node.dataset.cite||'');
  if(!item){node.remove();continue;}
  node.textContent=String(item.number);
  node.title=citationLabel(item.citation);
  node.setAttribute('aria-label','引用 '+item.number+'：'+citationLabel(item.citation));
 }
 return template.innerHTML;
}
