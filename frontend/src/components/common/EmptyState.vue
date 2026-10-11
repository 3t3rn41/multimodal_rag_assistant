<template>
 <div class="ui-empty"><span class="ui-empty__icon"><Icon :name="icon"/></span><h2>{{ title }}</h2><p v-if="description">{{ description }}</p><slot/></div>
</template>
<script setup lang="ts">
import Icon from './Icon.vue';
withDefaults(defineProps<{title:string;description?:string;icon?:string}>(),{icon:'book',description:''});
</script>
