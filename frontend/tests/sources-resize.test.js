import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {createApp, h, nextTick, ref} from 'vue';
import {useSourcesResize} from '../src/composables/useSourcesResize';

let app, api, open, small, handle, observedResize, disconnect, size;
const initialViewport = window.innerWidth;

async function mount() {
 open = ref(false); small = ref(false);
 const layout = ref(null), host = document.createElement('div');
 document.body.appendChild(host);
 app = createApp({setup() {
  api = useSourcesResize(open, small, layout);
  return () => h('div', {ref: node => {
   layout.value = node;
   if (node) node.getBoundingClientRect = () => ({width: size});
  }, class: {'sources-resizing': api.dragging.value}}, [h('div', {
   onPointerdown: api.startResize, onPointermove: api.moveResize, onPointerup: api.endResize,
   onPointercancel: api.endResize, onLostpointercapture: api.endResize,
   onKeydown: api.keyboardResize, onDblclick: api.resetWidth, tabindex: 0,
  })]);
 }});
 app.mount(host);
 handle = host.firstElementChild.firstElementChild;
 const captures = new Set();
 handle.setPointerCapture = vi.fn(id => captures.add(id));
 handle.hasPointerCapture = id => captures.has(id);
 handle.releasePointerCapture = vi.fn(id => captures.delete(id));
 open.value = true;
 await nextTick(); await nextTick();
}

async function pointer(type, x = 600, id = 1, options = {}) {
 const event = new MouseEvent(type, {bubbles: true, cancelable: true, clientX: x, button: 0, ...options});
 Object.defineProperties(event, {pointerId: {value: id}, isPrimary: {value: true}});
 handle.dispatchEvent(event); await nextTick();
}
async function key(value) {handle.dispatchEvent(new KeyboardEvent('keydown', {key: value, bubbles: true, cancelable: true})); await nextTick();}

beforeEach(() => {
 size = 1200;
 window.innerWidth = 1440;
 disconnect = vi.fn();
 vi.stubGlobal('ResizeObserver', class {
  constructor(callback) {observedResize = callback;}
  observe() {}
  disconnect = disconnect;
 });
});
afterEach(() => {app?.unmount(); app = null; document.body.replaceChildren(); window.innerWidth = initialViewport;});

describe('Sources resizing', () => {
 it('resets adjusted widths on reopen and chooses the current viewport default', async () => {
  await mount(); expect(api.width.value).toBe(380);
  await key('ArrowLeft'); expect(api.width.value).toBe(390);
  open.value = false; open.value = true;
  await nextTick(); await nextTick(); expect(api.width.value).toBe(380);
  window.innerWidth = 1200;
  open.value = false; open.value = true;
  await nextTick(); await nextTick(); expect(api.width.value).toBe(340);
 });

 it('captures the pointer, moves both ways and clamps to panel and chat limits', async () => {
  await mount();
  await pointer('pointerdown'); expect(api.dragging.value).toBe(true);
  expect(handle.setPointerCapture).toHaveBeenCalledWith(1);
  expect(document.activeElement).toBe(handle);
  await pointer('pointermove', 500); expect(api.width.value).toBe(480);
  await pointer('pointermove', 1000); expect(api.width.value).toBe(320);
  await pointer('pointermove', 0); expect(api.width.value).toBe(800);
  await pointer('pointermove', 800, 2); expect(api.width.value).toBe(800);
  expect(handle.parentElement.classList.contains('sources-resizing')).toBe(true);
  size = 900; observedResize(); await nextTick();
  expect(api.width.value).toBe(500); expect(api.dragging.value).toBe(false);
  expect(handle.releasePointerCapture).toHaveBeenCalledWith(1);
 });

 it('supports keyboard bounds and double-click reset', async () => {
  size = 1000; await mount();
  await key('ArrowLeft'); expect(api.width.value).toBe(390);
  await key('ArrowRight'); expect(api.width.value).toBe(380);
  await key('Home'); expect(api.width.value).toBe(320);
  await key('End'); expect(api.width.value).toBe(600);
  await key('Tab'); expect(api.width.value).toBe(600);
  handle.dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); await nextTick();
  expect(api.width.value).toBe(380);
 });

 it('stops dragging on mobile and rejects new mobile, closed and secondary-button drags', async () => {
  await mount(); await pointer('pointerdown');
  small.value = true; await nextTick(); expect(api.dragging.value).toBe(false);
  await pointer('pointerdown'); expect(api.dragging.value).toBe(false);
  small.value = false; await pointer('pointerdown', 600, 1, {button: 2}); expect(api.dragging.value).toBe(false);
  open.value = false; await pointer('pointerdown'); expect(api.dragging.value).toBe(false);
 });

 it.each(['pointerup', 'pointercancel', 'lostpointercapture', 'blur', 'close', 'unmount'])('clears a drag on %s', async event => {
  await mount(); await pointer('pointerdown');
  if (event === 'blur') window.dispatchEvent(new Event('blur'));
  else if (event === 'close') open.value = false;
  else if (event === 'unmount') {app.unmount(); app = null; expect(disconnect).toHaveBeenCalledOnce();}
  else await pointer(event);
  await nextTick(); expect(api.dragging.value).toBe(false);
  expect(handle.releasePointerCapture).toHaveBeenCalledWith(1);
 });
});
