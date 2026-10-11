<template>
 <div class="ui-progress" role="progressbar" :aria-label="label" :aria-valuenow="percentage" aria-valuemin="0" aria-valuemax="100"><div class="ui-progress__fill" :style="{transform:'scaleX('+percentage/100+')'}"/></div>
</template>
<script setup lang="ts">
import {computed} from 'vue';
const props=defineProps<{value:number;label:string}>();
const percentage=computed(()=>Math.max(0,Math.min(100,Number.isFinite(props.value)?props.value:0)));
</script>
