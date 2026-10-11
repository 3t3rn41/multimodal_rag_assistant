import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {createApp, h, nextTick, reactive} from 'vue';
import {http, invalidateAccountRequests} from '../src/api/http';
import CitationDialog from '../src/components/chat/CitationDialog.vue';
import AnswerBlock from '../src/components/chat/AnswerBlock.vue';

let apps;
const flush = async () => {await Promise.resolve(); await Promise.resolve(); await nextTick();};
async function mount(component, props) {
 const container = document.createElement('div');document.body.appendChild(container);
 const app = createApp({render:()=>h(component,props)});apps.push(app);app.mount(container);await flush();return container;
}
function source(id='first',format='txt',file='7') {
 return {chunk_id:id,file_id:file,file_name:'sample.'+format,file_type:format,generation:1,source_type:'document',page:format==='pdf'?3:null,
  blocks:[{id:'body',kind:format==='md'?'markdown':'text',text:'全文第一段\n第二段证据',page:format==='pdf'?3:null}],
  locations:{first:[{block_id:'body',start:0,end:5}],second:[{block_id:'body',start:6,end:11}]},
  contents:{first:'全文第一段',second:'第二段证据'},original_url:'/api/files/'+file+'/content'};
}
beforeEach(()=>{apps=[];});
afterEach(()=>{apps.forEach(app=>app.unmount());document.body.replaceChildren();});

it.each(['pdf','docx','txt','md'])('uses the shared %s body reader and authenticated original link',async format=>{
 const get=vi.spyOn(http,'get').mockResolvedValue({data:source('first',format)});
 const container=await mount(CitationDialog,{open:true,panel:true,chunkId:'first'});
 const frame=container.querySelector('iframe');
 expect(frame?.getAttribute('srcdoc')).toContain('全文第一段');
 expect(frame?.getAttribute('sandbox')).toContain('allow-same-origin');
 expect(frame?.getAttribute('sandbox')).not.toContain('allow-scripts');
 expect(container.querySelector('a')?.getAttribute('href')).toContain('/api/files/7/content');
 expect(get).toHaveBeenCalledTimes(1);
 expect(get.mock.calls[0][0]).toBe('/chunks/first/source');
 expect(container.querySelector('.citation-excerpt,.original-preview-frame')).toBeNull();
});

it('switches citations in a cached document without replacing the iframe or downloading again',async()=>{
 const get=vi.spyOn(http,'get').mockResolvedValue({data:source()});
 const props=reactive({open:true,panel:true,chunkId:'first'});
 const container=await mount(CitationDialog,props);
 const frame=container.querySelector('iframe'),html=frame.getAttribute('srcdoc');
 props.chunkId='second';await flush();
 expect(container.querySelector('iframe')).toBe(frame);
 expect(frame.getAttribute('srcdoc')).toBe(html);
 expect(get).toHaveBeenCalledTimes(1);
 props.open=false;await flush();props.open=true;await flush();
 expect(get).toHaveBeenCalledTimes(2);
});

it.each([403,404])('keeps Sources open and clears preview/link after a source %s',async status=>{
 const get=vi.spyOn(http,'get').mockResolvedValueOnce({data:source()}).mockRejectedValue({response:{status}});
 const container=await mount(CitationDialog,{open:true,panel:true,chunkId:'first'});
 container.querySelector('[title="重新加载来源"]').click();await flush();
 expect(container.querySelector('.citation-panel')).not.toBeNull();
 expect(container.querySelector('[role="alert"]')?.textContent).toContain('来源已删除或无法查看');
 expect(container.querySelector('iframe,a')).toBeNull();
 expect(get).toHaveBeenCalledTimes(2);
});

it.each([503,undefined])('offers retry after transient failure %s',async status=>{
 const get=vi.spyOn(http,'get').mockRejectedValueOnce({response:{status}}).mockResolvedValue({data:source()});
 const container=await mount(CitationDialog,{open:true,panel:true,chunkId:'first'});
 expect(container.querySelector('[role="alert"]')?.textContent).toContain('读取失败');
 [...container.querySelectorAll('button')].find(button=>button.textContent==='重新加载').click();await flush();
 expect(container.querySelector('iframe')).not.toBeNull();
 expect(get).toHaveBeenCalledTimes(2);
});

it('ignores late responses when switching, closing and clearing the account',async()=>{
 const pending=[];
 vi.spyOn(http,'get').mockImplementation((url,config)=>new Promise(resolve=>pending.push({resolve,signal:config.signal,url})));
 const props=reactive({open:true,panel:true,chunkId:'first'});
 const container=await mount(CitationDialog,props);
 props.chunkId='other';await flush();
 expect(pending[0].signal.aborted).toBe(true);
 pending[1].resolve({data:source('other','txt','8')});pending[0].resolve({data:source()});await flush();
 expect(container.querySelector('a')?.getAttribute('href')).toContain('/files/8/');
 props.open=false;await flush();props.open=true;await flush();
 invalidateAccountRequests();
 expect(pending[2].signal.aborted).toBe(true);
 pending[2].resolve({data:source()});await flush();
 expect(container.querySelector('iframe,a')).toBeNull();
});

it('shows complete trusted text when a location cannot be verified',async()=>{
 const data=source();data.locations.first=[];data.contents.first='完整历史证据'.repeat(150);
 vi.spyOn(http,'get').mockResolvedValue({data});
 const container=await mount(CitationDialog,{open:true,panel:true,chunkId:'first'});
 expect(container.textContent).toContain('暂未定位到全文');
 expect(container.querySelector('.source-fallback pre')?.textContent).toBe(data.contents.first);
});

it('opens the same body reader in the knowledge-base popup',async()=>{
 vi.spyOn(http,'get').mockResolvedValue({data:source()});
 await mount(CitationDialog,{open:true,chunkId:'first'});
 expect(document.querySelector('[role="dialog"] iframe')?.getAttribute('title')).toBe('来源正文');
});

it('emits a direct trusted citation event and shows the same numbers in the footer',async()=>{
 vi.stubGlobal('requestAnimationFrame',callback=>{callback();return 1;});vi.stubGlobal('cancelAnimationFrame',vi.fn());
 const click=vi.fn();
 const item={content:'引用 [chunk:a]，重复 [chunk:a]，第二个 [chunk:b]。',citations:[{chunk_id:'b',doc_title:'B'},{chunk_id:'a',doc_title:'A'}]};
 const container=await mount(AnswerBlock,{item,onShowCitation:click});
 expect([...container.querySelectorAll('.cite-slot')].map(node=>node.textContent)).toEqual(['1','1','2']);
 expect([...container.querySelectorAll('.answer-sources .cite-number')].map(node=>node.textContent)).toEqual(['1','2']);
 container.querySelector('.cite-slot').click();
 expect(click).toHaveBeenCalledWith({chunkId:'a',citation:item.citations[1]});
 container.querySelector('[data-cite="b"]').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
 expect(click).toHaveBeenLastCalledWith({chunkId:'b',citation:item.citations[0]});
});
