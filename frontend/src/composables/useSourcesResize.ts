import {onBeforeUnmount, onMounted, nextTick, ref, watch, type Ref} from 'vue';

const MIN_WIDTH = 320;
const MAX_WIDTH = 800;
const CHAT_WIDTH = 400;

export function useSourcesResize(open: Readonly<Ref<boolean>>, smallScreen: Readonly<Ref<boolean>>, layout: Ref<HTMLElement | null>) {
  const width = ref(defaultWidth());
  const maxWidth = ref(MAX_WIDTH);
  const dragging = ref(false);
  let observer: ResizeObserver | null = null;
  let containerWidth = 0;
  let drag: {pointerId: number; x: number; width: number; handle: HTMLElement} | null = null;

  function defaultWidth() {return window.innerWidth >= 1280 ? 380 : 340;}
  function clamp(value: number) {return Math.max(MIN_WIDTH, Math.min(maxWidth.value, Math.round(value)));}

  function endResize(event?: PointerEvent) {
    if (!drag || (event && event.pointerId !== drag.pointerId)) return;
    const {handle, pointerId} = drag;
    drag = null;
    dragging.value = false;
    if (handle.hasPointerCapture(pointerId)) handle.releasePointerCapture(pointerId);
  }

  function updateBounds() {
    if (!layout.value) return;
    const measured = layout.value.getBoundingClientRect().width;
    if (measured !== containerWidth) endResize();
    containerWidth = measured;
    maxWidth.value = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, Math.floor(measured - CHAT_WIDTH)));
    width.value = clamp(width.value);
  }

  function resetWidth() {
    endResize();
    updateBounds();
    width.value = clamp(defaultWidth());
  }

  function startResize(event: PointerEvent) {
    if (!open.value || smallScreen.value || event.button !== 0 || event.isPrimary === false) return;
    endResize();
    updateBounds();
    const handle = event.currentTarget as HTMLElement;
    event.preventDefault();
    handle.focus();
    handle.setPointerCapture(event.pointerId);
    drag = {pointerId: event.pointerId, x: event.clientX, width: width.value, handle};
    dragging.value = true;
  }

  function moveResize(event: PointerEvent) {
    if (drag?.pointerId === event.pointerId) width.value = clamp(drag.width + drag.x - event.clientX);
  }

  function keyboardResize(event: KeyboardEvent) {
    if (!open.value || smallScreen.value) return;
    updateBounds();
    const values: Record<string, number> = {
      ArrowLeft: width.value + 10, ArrowRight: width.value - 10, Home: MIN_WIDTH, End: maxWidth.value,
    };
    if (!(event.key in values)) return;
    event.preventDefault();
    width.value = clamp(values[event.key]);
  }

  function blur() {endResize();}
  watch(open, async visible => {
    endResize();
    width.value = defaultWidth();
    if (visible) {
      await nextTick();
      if (open.value) updateBounds();
    }
  }, {flush: 'sync'});
  watch(smallScreen, () => endResize(), {flush: 'sync'});

  onMounted(() => {
    observer = new ResizeObserver(updateBounds);
    if (layout.value) observer.observe(layout.value);
    window.addEventListener('resize', updateBounds);
    window.addEventListener('blur', blur);
  });
  onBeforeUnmount(() => {
    endResize();
    observer?.disconnect();
    window.removeEventListener('resize', updateBounds);
    window.removeEventListener('blur', blur);
  });

  return {width, maxWidth, dragging, startResize, moveResize, endResize, keyboardResize, resetWidth};
}
