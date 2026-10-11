<template>
 <Teleport to="body"><Transition name="fade">
  <div v-if="open" class="modal-mask" @click.self="emit('close')">
   <section ref="dialog" class="modal" :class="{'modal-wide':wide}" role="dialog" aria-modal="true" :aria-label="title" tabindex="-1">
    <header class="modal-head"><h2 class="modal-title">{{ title }}</h2><button type="button" class="btn-icon" aria-label="关闭弹窗" @click="emit('close')"><Icon name="x"/></button></header>
    <div class="modal-body"><slot/></div><footer v-if="$slots.footer" class="modal-foot"><slot name="footer"/></footer>
   </section>
  </div>
 </Transition></Teleport>
</template>
<script setup lang="ts">
import {ref,toRef} from 'vue';
import Icon from './Icon.vue';
import {useOverlayFocus} from '../../composables/useOverlayFocus';
const props=withDefaults(defineProps<{open:boolean;title:string;wide?:boolean}>(),{wide:false}),emit=defineEmits<{close:[]}>();
const dialog=ref<HTMLElement|null>(null);
useOverlayFocus(toRef(props,'open'),dialog,()=>emit('close'));
</script>
