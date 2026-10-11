<template>
 <div ref="host" class="knowledge-network" :class="{compact}" @pointermove="pointerMove" @pointerleave="pointerLeave">
  <canvas ref="canvas" class="network-canvas" :data-motion-state="variant==='reference'?motionState:undefined" :aria-hidden="decorative?true:undefined" :role="decorative?undefined:'img'" :aria-label="decorative?undefined:(variant==='reference'?'自动汇聚与散开的知识节点网络':'缓慢连接的知识节点网络')"/>
  <button v-if="variant==='ambient'&&available&&!decorative&&!reduced" type="button" class="network-toggle" :aria-pressed="paused" @click="paused=!paused">{{ paused?'继续动画':'暂停动画' }}</button>
 </div>
</template>
<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount} from 'vue';
const props=withDefaults(defineProps<{compact?:boolean;decorative?:boolean;count?:number;variant?:'ambient'|'reference'|'auth'}>(),{compact:false,decorative:false,count:64,variant:'ambient'});
const host=ref<HTMLDivElement|null>(null),canvas=ref<HTMLCanvasElement|null>(null);
const paused=ref(false),reduced=ref(false),available=ref(false);
const motionState=ref<'scattered'|'gathering'|'gathered'|'scattering'>('scattered');
let dispose=()=>{},leavePointer=()=>{};
let handlePointer:(event:PointerEvent)=>void=()=>{};
function pointerMove(event:PointerEvent){handlePointer(event)}
function pointerLeave(){leavePointer()}
onMounted(()=>{
 const container=host.value,element=canvas.value;
 if(!container||!element||typeof window.matchMedia!=='function'||typeof ResizeObserver==='undefined')return;
 const context=element.getContext('2d');if(!context)return;const ctx:CanvasRenderingContext2D=context;
 available.value=true;
 const preferences=window.matchMedia('(prefers-reduced-motion: reduce)');reduced.value=preferences.matches;
 const count=Math.max(50,Math.min(80,Math.round(props.count)));
 const colored=props.variant==='auth';
 const palette=[[0,0,0],[255,119,51],[229,167,0],[168,154,26]];
 const paletteSlots=[0,1,3,0,2,0,1,2,3,0];
 const nodes=Array.from({length:count},(_,index)=>{
  const sizeGroup=index%5;
  const r=colored?(sizeGroup===0?8+Math.random()*5:sizeGroup<=2?3.5+Math.random()*3.5:1.4+Math.random()*1.7):1.6+Math.random()*1.4;
  const color='rgb('+palette[paletteSlots[(index+Math.floor(index/10))%paletteSlots.length]].join(',')+')';
  return {x:.07+Math.random()*.86,y:.07+Math.random()*.86,
   vx:(Math.random()-.5)*.008,vy:(Math.random()-.5)*.008,r,color,accent:index%10===0,ox:0,oy:0};
 });
 const labels=['PDF','Image','Audio','Video','Chunk','Vector','Knowledge','Answer'];
 const pointer={x:0,y:0,active:false};let width=0,height=0,raf=0,last=0,visible=true,destroyed=false;
 // Project a small point cloud with Canvas 2D. No WebGL, textures or scene library.
 const scatterAnchors=[{x:-.34,y:.54,z:.18},{x:.3,y:.31,z:-.36},{x:-.32,y:-.5,z:.27}];
 const cloud=props.variant==='reference'?Array.from({length:count},(_,index)=>{
  const y=1-2*(index+.5)/count,angle=index*Math.PI*(3-Math.sqrt(5))+.2*(Math.random()-.5);
  const ring=Math.sqrt(1-y*y);
  const x=Math.cos(angle)*ring,z=Math.sin(angle)*ring;
  const free=index%5===4||index%7===0;
  const anchor=scatterAnchors[index%7===1?2:index%2],spread=free?.88+Math.random()*.35:.15+Math.random()*.22;
  const cx=free?x*spread:anchor.x+x*spread,cy=free?y*spread:anchor.y+y*spread,cz=free?z*spread:anchor.z+z*spread;
  const sizeGroup=index%5;
  const radius=sizeGroup===0?10+Math.random()*6:sizeGroup<=2?4.3+Math.random()*3.9:1.3+Math.random()*2.1;
  return {x,y,z,cx,cy,cz,radius,delay:Math.random()*.11,colorStart:.25+Math.random()*.5,
   color:palette[paletteSlots[(index+Math.floor(index/10))%paletteSlots.length]],phase:Math.random()*Math.PI*2};
 }):[];
 const motion={gatherStart:2.85,gatherDuration:1.15,holdDuration:6.1,contractDuration:.5,scatterDuration:1.25,restDuration:2.25};
 const gatheredAt=motion.gatherStart+motion.gatherDuration,contractAt=gatheredAt+motion.holdDuration;
 const scatterAt=contractAt+motion.contractDuration,scatterEnd=scatterAt+motion.scatterDuration,cycleLength=scatterEnd+motion.restDuration;
 let cloudTime=0;
 function smootherstep(value:number){const t=Math.max(0,Math.min(1,value));return t*t*t*(t*(t*6-15)+10)}
 function draw(time:number,animate:boolean){
  if(props.variant==='reference'){drawCloud(time,animate);return}
  if(!width||!height)return;const delta=animate&&last?Math.min(time-last,40):0;last=time;
  ctx.clearRect(0,0,width,height);
  const points=nodes.map(node=>{
   if(animate){node.x+=node.vx*delta/width;node.y+=node.vy*delta/height;if(node.x<.06||node.x>.94)node.vx*=-1;if(node.y<.06||node.y>.94)node.vy*=-1}
   const x=node.x*width,y=node.y*height,dx=x-pointer.x,dy=y-pointer.y,distance=Math.hypot(dx,dy);
   const influence=pointer.active&&!reduced.value&&!paused.value?Math.max(0,1-distance/140):0;
   const ease=delta?1-Math.exp(-delta/220):1;
   node.ox+=((dx/(distance||1))*12*influence-node.ox)*ease;node.oy+=((dy/(distance||1))*12*influence-node.oy)*ease;
   return {node,x:x+node.ox,y:y+node.oy,influence};
  });
  const connections=new Uint8Array(count),limit=Math.min(126,width*.23);
  for(let first=0;first<count;first++)for(let second=first+1;second<count;second++){
   if(connections[first]>=2||connections[second]>=2)continue;
   const a=points[first],b=points[second],distance=Math.hypot(a.x-b.x,a.y-b.y);if(distance>=limit)continue;
   connections[first]++;connections[second]++;
   const strength=.055+.13*(1-distance/limit)+.25*Math.max(a.influence,b.influence);
   ctx.strokeStyle=(colored?'rgba(30,31,27,':'rgba(80,87,74,')+strength+')';ctx.lineWidth=.55;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();
  }
  for(const point of points){
   ctx.beginPath();ctx.arc(point.x,point.y,point.node.r*(1+.25*point.influence),0,Math.PI*2);
   ctx.fillStyle=colored?point.node.color:point.node.accent?'#b95838':'#4e5548';ctx.globalAlpha=colored?1:point.node.accent?.72:.58+.25*point.influence;ctx.fill();ctx.globalAlpha=1;
  }
  if(colored)return;
  ctx.font='11px "Segoe UI",sans-serif';ctx.fillStyle='rgba(79,85,71,.65)';
  const cycle=Math.floor(time/30000),labelCount=props.compact?2:4;
  for(let index=0;index<labelCount;index++){const point=points[(9+index*13)%count],label=labels[(index+cycle)%labels.length];const offset=point.x>width*.79?-ctx.measureText(label).width-8:8;ctx.fillText(label,point.x+offset,point.y+3)}
 }
 function drawCloud(time:number,animate:boolean){
  if(!width||!height)return;
  const delta=animate&&last?Math.min(time-last,40):0;last=time;
  cloudTime+=delta/1000;
  // The full sequence runs by itself; pointer movement only nudges nearby dots.
  const phase=cloudTime%cycleLength;
  const state=reduced.value||phase<motion.gatherStart||phase>=scatterEnd?'scattered':phase<gatheredAt?'gathering':phase<contractAt?'gathered':'scattering';
  if(motionState.value!==state)motionState.value=state;
  // Release first draws the network in slightly, then reorganizes it into separate clusters.
  const contraction=phase>=contractAt&&phase<scatterAt?1-.12*smootherstep((phase-contractAt)/motion.contractDuration):phase>=scatterAt&&phase<scatterEnd?.88+.12*smootherstep((phase-scatterAt)/motion.scatterDuration):1;
  const radius=Math.min(width*.46,height*.46,Math.max(0,width/2-24)/1.05);
  const centerX=width*.5,centerY=height*.5;
  const orbit=cloudTime*.075,tilt=.26+Math.sin(cloudTime*.23)*.11,roll=Math.sin(cloudTime*.14)*.06;
  const sin=Math.sin(orbit),cos=Math.cos(orbit),tiltSin=Math.sin(tilt),tiltCos=Math.cos(tilt),rollSin=Math.sin(roll),rollCos=Math.cos(roll);
  const points=cloud.map(node=>{
   const form=reduced.value?0:phase<motion.gatherStart?0:phase<gatheredAt?smootherstep((phase-motion.gatherStart-node.delay)/(motion.gatherDuration-node.delay)):phase<scatterAt?1:phase<scatterEnd?1-smootherstep((phase-scatterAt-node.delay)/(motion.scatterDuration-node.delay)):0;
   const bow=Math.sin(Math.PI*form)*.12,drift=(1-form)*.018;
   const cx=node.cx+Math.sin(cloudTime*.28+node.phase)*drift,cy=node.cy+Math.cos(cloudTime*.24+node.phase)*drift;
   const x=cx+(node.x*contraction-cx)*form+Math.cos(node.phase)*bow;
   const y=cy+(node.y*contraction-cy)*form+Math.sin(node.phase)*bow;
   const z=node.cz+(node.z*contraction-node.cz)*form+Math.sin(node.phase+1.1)*bow*.5;
   const rx=x*cos+z*sin,rz=z*cos-x*sin,ry=y*tiltCos-rz*tiltSin,depth=y*tiltSin+rz*tiltCos;
   const sx=rx*rollCos-ry*rollSin,sy=rx*rollSin+ry*rollCos,perspective=3.4/(3.4-depth);
   let px=centerX+sx*radius*perspective,py=centerY+sy*radius*perspective;
   const dx=px-pointer.x,dy=py-pointer.y,distance=Math.hypot(dx,dy);
   const influence=pointer.active&&!reduced.value?Math.max(0,1-distance/110):0;
   px+=dx/(distance||1)*5*influence;py+=dy/(distance||1)*5*influence;
   return {node,x:px,y:py,depth,influence,form,link:smootherstep((form-.08)/.78),color:smootherstep((form-node.colorStart)/.1),r:node.radius*perspective*(1+.12*influence)};
  });
  const gatherAmount=points.reduce((sum,point)=>sum+point.form,0)/count;
  ctx.clearRect(0,0,width,height);
  // The scattered cloud has sparse connections; organized dots connect to the center.
  const degrees=new Uint8Array(count),limit=radius*.52;
  ctx.lineWidth=.55;
  for(let first=0;first<count;first++)for(let second=first+1;second<count;second++){
   if(degrees[first]>=2||degrees[second]>=2)continue;
   const a=points[first],b=points[second],distance=Math.hypot(a.x-b.x,a.y-b.y);
   if(distance>=limit)continue;
   degrees[first]++;degrees[second]++;
   ctx.strokeStyle='rgba(30,31,27,'+(.22*(1-distance/limit)*(1-Math.max(a.link,b.link)))+')';
   ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();
  }
  if(gatherAmount>.01){
   for(const point of points){
    if(Math.hypot(point.x-centerX,point.y-centerY)<radius*.15)continue;
    if(point.link<.01)continue;
    ctx.strokeStyle='rgba(30,31,27,'+(.32*point.link)+')';
    ctx.beginPath();ctx.moveTo(point.x,point.y);ctx.lineTo(point.x+(centerX-point.x)*point.link,point.y+(centerY-point.y)*point.link);ctx.stroke();
   }
  }
  points.sort((a,b)=>a.depth-b.depth);
  for(const point of points){
   const color=point.node.color.map(value=>Math.round(value*point.color));
   ctx.fillStyle='rgb('+color.join(',')+')';
   ctx.beginPath();ctx.arc(point.x,point.y,point.r,0,Math.PI*2);ctx.fill();
  }
  if(gatherAmount>.01){ctx.fillStyle='rgb('+palette[3].join(',')+')';ctx.globalAlpha=gatherAmount;ctx.beginPath();ctx.arc(centerX,centerY,2.2,0,Math.PI*2);ctx.fill()}
  ctx.globalAlpha=1;
 }
 function canAnimate(){return !destroyed&&!paused.value&&!reduced.value&&visible&&!document.hidden}
 function frame(time:number){raf=0;draw(time,true);if(canAnimate())raf=requestAnimationFrame(frame)}
 function update(){if(raf)cancelAnimationFrame(raf);raf=0;last=0;if(canAnimate())raf=requestAnimationFrame(frame);else draw(performance.now(),false)}
 function resize(){const bounds=container!.getBoundingClientRect();width=bounds.width;height=bounds.height;const ratio=Math.min(window.devicePixelRatio||1,2);element!.width=Math.round(width*ratio);element!.height=Math.round(height*ratio);ctx.setTransform(ratio,0,0,ratio,0,0);draw(performance.now(),false)}
 handlePointer=event=>{if(paused.value||reduced.value)return;const bounds=container!.getBoundingClientRect();pointer.x=event.clientX-bounds.left;pointer.y=event.clientY-bounds.top;pointer.active=event.pointerType!=='touch'};
 leavePointer=()=>pointer.active=false;
 const observer=new ResizeObserver(resize);observer.observe(container);
 const intersection=typeof IntersectionObserver!=='undefined'?new IntersectionObserver(entries=>{visible=entries[0]?.isIntersecting??true;update()}):null;intersection?.observe(container);
 function preferenceChanged(){reduced.value=preferences.matches;pointer.active=false;update()}
 function pauseClicked(){update()}
 // A DOM click occurs after Vue updates paused on the same event; queue the draw toggle.
 const onClick=()=>queueMicrotask(pauseClicked);
 if(props.variant==='ambient')container.addEventListener('click',onClick);
 preferences.addEventListener('change',preferenceChanged);document.addEventListener('visibilitychange',update);
 resize();update();
 dispose=()=>{destroyed=true;if(raf)cancelAnimationFrame(raf);observer.disconnect();intersection?.disconnect();preferences.removeEventListener('change',preferenceChanged);document.removeEventListener('visibilitychange',update);container.removeEventListener('click',onClick);handlePointer=()=>{};leavePointer=()=>{}};
});
onBeforeUnmount(()=>dispose());
</script>
<style scoped>
.knowledge-network{position:relative;width:100%;height:100%;min-height:180px;overflow:hidden}
.network-canvas{display:block;width:100%;height:100%}.network-toggle{position:absolute;right:12px;bottom:12px;font-size:11px;color:var(--ink-mute);padding:6px 9px;border-radius:6px;background:rgb(247 247 244 / .9)}.network-toggle:hover{background:var(--surface-warm)}
.compact{opacity:.6}
@media(pointer:coarse){.network-toggle{padding:9px 12px}}
</style>
