import {watch,nextTick,onBeforeUnmount,type Ref} from 'vue';
const overlays:HTMLElement[]=[];
let savedOverflow='';
export function useOverlayFocus(open:Readonly<Ref<boolean>>,root:Ref<HTMLElement|null>,close:()=>void){
 let active:HTMLElement|null=null,previous:HTMLElement|null=null;
 function deactivate(){
  if(!active)return;
  const index=overlays.indexOf(active);if(index>=0)overlays.splice(index,1);
  if(!overlays.length)document.body.style.overflow=savedOverflow;
  active=null;previous?.focus();previous=null;
 }
 function keydown(event:KeyboardEvent){
  if(!active||overlays.at(-1)!==active)return;
  if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close();return}
  if(event.key!=='Tab')return;
  const nodes=Array.from(active.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),textarea:not(:disabled),select:not(:disabled),[tabindex="0"]')).filter(node=>!node.closest('[hidden],[inert]'));
  const first=nodes[0],last=nodes.at(-1);
  if(!first){event.preventDefault();active.focus();return}
  if(event.shiftKey&&(document.activeElement===first||document.activeElement===active)){event.preventDefault();last?.focus()}
  else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
 }
 watch(open,async value=>{
  if(!value){deactivate();return}
  await nextTick();if(!open.value||!root.value)return;
  previous=document.activeElement instanceof HTMLElement?document.activeElement:null;
  active=root.value;if(!overlays.length)savedOverflow=document.body.style.overflow;
  overlays.push(active);document.body.style.overflow='hidden';
  (active.querySelector<HTMLElement>('[autofocus]')||active.querySelector<HTMLElement>('input:not(:disabled):not([type="hidden"]),button:not(:disabled)')||active).focus();
 },{immediate:true,flush:'post'});
 document.addEventListener('keydown',keydown);
 onBeforeUnmount(()=>{document.removeEventListener('keydown',keydown);deactivate()});
}
