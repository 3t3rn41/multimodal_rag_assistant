<template>
  <AuthLayout>
    <nav v-if="step === 'form' && mode !== 'forgot'" class="auth-tabs" aria-label="登录方式">
      <button :class="{ active: mode === 'login' }" :disabled="busy" @click="switchMode('login')">登录</button>
      <button :class="{ active: mode === 'register' }" :disabled="busy" @click="switchMode('register')">创建账号</button>
    </nav>
    <span v-if="step !== 'form'" class="challenge-icon"><Icon :name="step === 'registered' ? 'success' : 'mail'" /></span>
    <h1 id="auth-title">{{ title }}</h1><p class="auth-intro">{{ introduction }}</p>
    <p v-if="error || codeError || auth.error" id="registration-code-error" class="error-item" role="alert">{{ error || codeError || auth.error }}</p>
    <template v-if="step === 'code'">
      <span class="registration-email">{{ registrationEmail }}</span>
      <form class="registration-code-form" @submit.prevent="verifyCode">
        <label class="registration-code-label" for="registration-code-1">邮箱验证码</label>
        <RegistrationCodeInput ref="codeInput" v-model="code" :disabled="busy && !sending" :error="!!codeError" />
        <p v-if="registrationToken && !sending" class="field-hint">{{ Math.ceil(expiresIn / 60) }} 分钟内有效，请使用最新邮件中的验证码。</p>
        <p v-if="sending" class="registration-code-status" role="status">正在发送验证码…</p>
        <p v-else-if="message" class="auth-success registration-code-status" role="status">{{ message }}</p>
        <button class="btn btn-primary auth-submit" type="submit" :disabled="busy || !registrationToken || code.length !== 6">
          {{ busy && !sending ? '正在验证…' : '验证并完成注册' }}
        </button>
      </form>
      <div class="auth-links">
        <button class="auth-text-button" :disabled="busy || resendRemaining > 0" @click="sendRegistrationCode">{{ resendLabel }}</button>
        <button class="auth-text-button" :disabled="busy" @click="switchMode('register')">修改邮箱或密码</button>
      </div>
    </template>
    <template v-else-if="step === 'registered'">
      <p class="auth-success" role="status">邮箱已验证，使用刚才设置的密码登录即可。</p>
      <button class="btn btn-primary auth-submit" @click="switchMode('login')">前往登录</button>
    </template>
    <template v-else>
      <div v-if="sent" class="mail-waiting" role="status"><span class="mail-icon"><Icon name="mail" /></span><h2>查看重设密码邮件</h2><p>{{ message }}</p><span class="waiting-email">{{ email }}</span></div>
      <p v-else-if="message" class="auth-success" role="status">{{ message }}</p>
      <form v-if="!sent" @submit.prevent="submit">
        <div class="field"><label for="email">邮箱</label><input id="email" v-model.trim="email" type="email" autocomplete="email" required maxlength="255" class="input" /></div>
        <template v-if="mode !== 'forgot'">
          <div class="field">
            <label for="password">密码</label>
            <div class="password-field">
              <input id="password" v-model="password" :type="showPassword ? 'text' : 'password'" :autocomplete="mode === 'register' ? 'new-password' : 'current-password'" required minlength="8" maxlength="20" pattern="[A-Za-z0-9]{8,20}" class="input" :disabled="busy" />
              <button type="button" class="btn-icon password-toggle" :disabled="busy" :aria-label="showPassword ? '隐藏密码' : '显示密码'" :aria-pressed="showPassword" @click="showPassword = !showPassword"><Icon :name="showPassword ? 'eyeOff' : 'eye'" /></button>
            </div>
            <p class="field-hint">8–20 个字符，只能包含数字和英文字母。</p>
          </div>
          <div v-if="mode === 'register'" class="field">
            <label for="registration-confirm">确认密码</label>
            <div class="password-field">
              <input id="registration-confirm" v-model="confirmation" class="input" :type="showConfirmation ? 'text' : 'password'" autocomplete="new-password" required minlength="8" maxlength="20" pattern="[A-Za-z0-9]{8,20}" :disabled="busy" :aria-invalid="!!confirmationError" />
              <button type="button" class="btn-icon password-toggle" :disabled="busy" :aria-label="showConfirmation ? '隐藏确认密码' : '显示确认密码'" :aria-pressed="showConfirmation" @click="showConfirmation = !showConfirmation"><Icon :name="showConfirmation ? 'eyeOff' : 'eye'" /></button>
            </div>
            <p v-if="confirmationError" class="field-error" role="alert">{{ confirmationError }}</p>
          </div>
        </template>
        <button type="submit" class="btn btn-primary auth-submit" :disabled="busy">{{ busy ? '正在处理…' : mode === 'register' ? '注册并发送验证码' : mode === 'forgot' ? '发送重设密码邮件' : '登录' }}</button>
      </form>
      <div class="auth-links">
        <button v-if="mode === 'login'" class="auth-text-button" :disabled="busy" @click="switchMode('forgot')">忘记密码</button>
        <button v-if="mode === 'forgot' || sent" class="auth-text-button" :disabled="busy" @click="switchMode('login')">返回登录</button>
      </div>
    </template>
  </AuthLayout>
</template>
<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import AuthLayout from '../../components/auth/AuthLayout.vue';
import RegistrationCodeInput from '../../components/auth/RegistrationCodeInput.vue';
import Icon from '../../components/common/Icon.vue';
import { useWorkbenchAuth } from '../../composables/useWorkbench';
import { http, apiErrorMessage, apiReadErrorMessage, isCanceledRequest } from '../../api/http';
type Mode = 'login' | 'register' | 'forgot';
const auth = useWorkbenchAuth(), router = useRouter(), route = useRoute();
const mode = ref<Mode>(route.query.mode === 'forgot' ? 'forgot' : route.query.mode === 'register' ? 'register' : 'login');
const step = ref<'form' | 'code' | 'registered'>('form');
const email = ref(''), password = ref(''), confirmation = ref('');
const showPassword = ref(false), showConfirmation = ref(false), busy = ref(false);
const error = ref(''), message = ref(''), confirmationError = ref(''), sent = ref(false);
const registrationEmail = ref(''), registrationToken = ref(''), code = ref(''), codeError = ref('');
const sending = ref(false), expiresIn = ref(600);
const codeInput = ref<InstanceType<typeof RegistrationCodeInput> | null>(null);
const resendDeadline = ref(0), clock = ref(Date.now());
let pendingRegistration: { email: string; password: string } | null = null;
let registrationRequest: AbortController | null = null;
let countdown: ReturnType<typeof setInterval> | undefined;
const resendRemaining = computed(() => Math.max(0, Math.ceil((resendDeadline.value - clock.value) / 1000)));
const title = computed(() => {
  if (step.value === 'registered') return '注册成功';
  if (step.value === 'code') return '验证你的邮箱';
  if (sent.value) return '查看你的邮箱';
  if (mode.value === 'register') return '建立你的知识空间';
  if (mode.value === 'forgot') return '重设密码';
  return '欢迎回来';
});
const introduction = computed(() => {
  if (step.value === 'registered') return '你的知识空间已经准备好了。';
  if (step.value === 'code') return '请在收到邮件后输入 6 位数字验证码。';
  if (mode.value === 'register') return '创建账号后，通过邮箱验证码启用你的知识空间。';
  if (mode.value === 'forgot') return '向已验证的邮箱发送重设密码链接。';
  return '继续你的资料、问题与知识连接。';
});
const resendLabel = computed(() => {
  if (sending.value) return '正在发送…';
  if (resendRemaining.value > 0) return `${resendRemaining.value} 秒后可重新发送`;
  return registrationToken.value ? '重新发送验证码' : '重试发送';
});
function stopCountdown() {
  if (countdown !== undefined) clearInterval(countdown);
  countdown = undefined;
  resendDeadline.value = 0;
}
function startCountdown(seconds: number) {
  stopCountdown(); clock.value = Date.now(); resendDeadline.value = clock.value + seconds * 1000;
  countdown = setInterval(() => { clock.value = Date.now(); if (!resendRemaining.value) stopCountdown(); }, 1000);
}
function clearPasswords() { password.value = confirmation.value = ''; showPassword.value = showConfirmation.value = false; }
function isCurrentRequest(controller: AbortController) {
  return registrationRequest === controller && !controller.signal.aborted;
}
function clearRegistration() {
  registrationRequest?.abort();
  registrationRequest = null;
  pendingRegistration = null;
  registrationEmail.value = registrationToken.value = code.value = codeError.value = '';
  busy.value = sending.value = false;
  stopCountdown();
}
function switchMode(value: Mode) {
  clearRegistration();
  mode.value = value; step.value = 'form'; clearPasswords();
  error.value = message.value = confirmationError.value = '';
  auth.error = null; sent.value = false;
}
async function submit() {
  if (busy.value) return;
  error.value = message.value = confirmationError.value = ''; auth.error = null;
  if (mode.value !== 'forgot' && !/^[A-Za-z0-9]{8,20}$/.test(password.value)) { error.value = '密码须为 8–20 个字符，只能包含数字和英文字母。'; return; }
  if (mode.value === 'register') {
    if (password.value !== confirmation.value) { confirmationError.value = '两次输入的密码不同。'; return; }
    pendingRegistration = { email: email.value, password: password.value };
    registrationEmail.value = email.value;
    clearPasswords();
    step.value = 'code';
    await sendRegistrationCode();
    return;
  }
  busy.value = true;
  try {
    if (mode.value === 'login') { await auth.login(email.value, password.value); await router.replace('/app/kbs'); }
    else { message.value = (await http.post('/auth/forgot-password', { email: email.value })).data.message; sent.value = true; }
    clearPasswords();
  } catch (err) { error.value = apiErrorMessage(err, '操作失败，请稍后重试'); }
  finally { busy.value = false; }
}
async function sendRegistrationCode() {
  if (busy.value || step.value !== 'code' || resendRemaining.value > 0) return;
  const resending = !!registrationToken.value;
  if (!resending && !pendingRegistration) return;
  const controller = new AbortController();
  registrationRequest = controller;
  busy.value = sending.value = true;
  error.value = codeError.value = message.value = code.value = '';
  void nextTick(() => { if (isCurrentRequest(controller) && !code.value) codeInput.value?.focusFirst(); });
  try {
    const url = resending ? '/auth/resend-verification' : '/auth/register';
    const payload = resending
      ? { email: registrationEmail.value, registration_token: registrationToken.value }
      : pendingRegistration;
    const { data } = await http.post(url, payload, { signal: controller.signal });
    if (!isCurrentRequest(controller)) return;
    if (!resending) {
      if (typeof data?.registration_token !== 'string' || !/^[A-Za-z0-9_-]{32,128}$/.test(data.registration_token)) {
        error.value = '验证码发送响应无效，请重试发送。';
        return;
      }
      registrationToken.value = data.registration_token;
      pendingRegistration = null;
    }
    expiresIn.value = data.expires_in || 600;
    message.value = data.message || '验证码已发送，请查看邮箱，并使用最新邮件中的验证码。';
    startCountdown(data.resend_after ?? 60);
  } catch (err) {
    if (isCurrentRequest(controller) && !isCanceledRequest(err)) {
      error.value = apiReadErrorMessage(err, '验证码发送失败，请稍后重试。');
    }
  } finally {
    if (isCurrentRequest(controller)) {
      registrationRequest = null;
      busy.value = sending.value = false;
    }
  }
}
async function verifyCode() {
  if (busy.value || step.value !== 'code' || !registrationToken.value || !/^[0-9]{6}$/.test(code.value)) return;
  const controller = new AbortController();
  registrationRequest = controller;
  busy.value = true;
  error.value = codeError.value = message.value = '';
  try {
    await http.post('/auth/verify-registration', {
      email: registrationEmail.value, registration_token: registrationToken.value, code: code.value,
    }, { signal: controller.signal });
    if (!isCurrentRequest(controller)) return;
    step.value = 'registered';
    clearRegistration();
    clearPasswords();
  } catch (err) {
    if (isCurrentRequest(controller) && !isCanceledRequest(err)) {
      codeError.value = apiReadErrorMessage(err, '验证码验证失败，请稍后重试。');
    }
  } finally {
    if (isCurrentRequest(controller)) {
      registrationRequest = null;
      busy.value = false;
    }
  }
}
watch(code, () => { codeError.value = ''; });
onUnmounted(() => { clearRegistration(); clearPasswords(); });
</script>

