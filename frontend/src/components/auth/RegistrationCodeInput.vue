<template>
  <div class="registration-code-input" role="group" aria-label="6 位数字验证码">
    <input v-for="(_, index) in digits" :id="`registration-code-${index + 1}`" :key="index"
      :ref="element => setInput(element, index)" :value="digits[index]"
      class="input registration-code-cell" type="text" inputmode="numeric"
      :autocomplete="index === 0 ? 'one-time-code' : 'off'" maxlength="1" pattern="[0-9]" required
      :disabled="disabled" :aria-label="`验证码第 ${index + 1} 位`"
      :aria-invalid="error || undefined" :aria-describedby="error ? 'registration-code-error' : undefined"
      @input="enterDigits($event, index)" @paste="pasteDigits($event, index)" @keydown="navigate($event, index)"
      @focus="($event.target as HTMLInputElement).select()" />
  </div>
</template>
<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue';
import type { ComponentPublicInstance } from 'vue';
const props = defineProps<{ modelValue: string; disabled?: boolean; error?: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();
const digits = ref(Array.from({ length: 6 }, () => ''));
const inputs: (HTMLInputElement | null)[] = [];
function setInput(element: Element | ComponentPublicInstance | null, index: number) {
  inputs[index] = element instanceof HTMLInputElement ? element : null;
}
function focus(index: number) { inputs[Math.max(0, Math.min(5, index))]?.focus(); }
function focusFirst() { focus(0); }
function publish() { emit('update:modelValue', digits.value.join('')); }
function fill(value: string, index: number) {
  const clean = value.replace(/[^0-9]/g, '').slice(0, 6);
  if (!clean) return;
  const start = clean.length === 6 ? 0 : index;
  if (clean.length === 6) digits.value = Array.from({ length: 6 }, () => '');
  [...clean].forEach((digit, offset) => { if (start + offset < 6) digits.value[start + offset] = digit; });
  publish(); void nextTick(() => focus(start + clean.length));
}
function enterDigits(event: Event, index: number) {
  const input = event.target as HTMLInputElement;
  if (!input.value) { digits.value[index] = ''; publish(); return; }
  fill(input.value, index); input.value = digits.value[index];
}
function pasteDigits(event: ClipboardEvent, index: number) {
  event.preventDefault(); fill(event.clipboardData?.getData('text') || '', index);
}
function navigate(event: KeyboardEvent, index: number) {
  if (event.key === 'Backspace') {
    event.preventDefault();
    const target = digits.value[index] ? index : Math.max(0, index - 1);
    digits.value[target] = ''; publish(); focus(target);
  } else if (event.key === 'Delete') {
    event.preventDefault(); digits.value[index] = ''; publish();
  } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    event.preventDefault(); focus(index + (event.key === 'ArrowLeft' ? -1 : 1));
  } else if (event.key.length === 1 && !/[0-9]/.test(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault();
  }
}
watch(() => props.modelValue, value => {
  if (value === digits.value.join('')) return;
  const clean = value.replace(/[^0-9]/g, '').slice(0, 6);
  digits.value = Array.from({ length: 6 }, (_, index) => clean[index] || '');
}, { immediate: true });
onMounted(() => { if (!props.disabled) focusFirst(); });
defineExpose({ focusFirst });
</script>
