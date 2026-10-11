<template>
 <AuthLayout>
  <span class="challenge-icon"><Icon :name="message?'success':'lock'"/></span>
  <h1 id="challenge-title">{{ message?'密码已更新':'设置新密码' }}</h1>
  <p class="auth-intro">{{ message?'现在可以返回登录，进入你的知识空间。':'重设后，其他设备上的登录将失效。' }}</p>
  <p v-if="error" class="error-item" role="alert">{{ error }}</p><p v-if="message" class="auth-success" role="status">{{ message }}</p>
  <form v-if="!message&&token" @submit.prevent="submit">
   <div class="field"><label for="new-password">登录密码</label><div class="password-field"><input id="new-password" v-model="password" class="input" :type="showPassword?'text':'password'" autocomplete="new-password" required minlength="8" maxlength="20" pattern="[A-Za-z0-9]{8,20}" :disabled="busy"/><button type="button" class="btn-icon password-toggle" :disabled="busy" :aria-label="showPassword?'隐藏密码':'显示密码'" :aria-pressed="showPassword" @click="showPassword=!showPassword"><Icon :name="showPassword?'eyeOff':'eye'"/></button></div></div>
   <div class="field"><label for="confirm-password">再次输入密码</label><div class="password-field"><input id="confirm-password" v-model="confirmation" class="input" :type="showConfirmation?'text':'password'" autocomplete="new-password" required minlength="8" maxlength="20" pattern="[A-Za-z0-9]{8,20}" :disabled="busy"/><button type="button" class="btn-icon password-toggle" :disabled="busy" :aria-label="showConfirmation?'隐藏确认密码':'显示确认密码'" :aria-pressed="showConfirmation" @click="showConfirmation=!showConfirmation"><Icon :name="showConfirmation?'eyeOff':'eye'"/></button></div></div>
   <p class="field-hint">8–20 个字符，只能包含数字和英文字母。</p>
   <button class="btn btn-primary auth-submit" type="submit" :disabled="busy">{{ busy?'正在处理…':'保存新密码' }}</button>
  </form>
  <RouterLink v-if="error" :to="{path:'/login',query:{mode:'forgot'}}" class="btn btn-ghost auth-submit">重新申请重设密码邮件</RouterLink>
  <RouterLink to="/login" class="auth-back"><Icon name="chevronLeft"/>返回登录</RouterLink>
 </AuthLayout>
</template>
<script setup lang="ts">
import {ref} from 'vue';
import {useRoute} from 'vue-router';
import AuthLayout from '../../components/auth/AuthLayout.vue';
import Icon from '../../components/common/Icon.vue';
import {http,apiErrorMessage} from '../../api/http';
import {useWorkbenchAuth} from '../../composables/useWorkbench';
const route=useRoute(),auth=useWorkbenchAuth();
const token=ref(new URLSearchParams(route.hash.replace(/^#/, '')).get('token')||'');
const password=ref(''),confirmation=ref(''),showPassword=ref(false),showConfirmation=ref(false),busy=ref(false),message=ref('');
const error=ref(token.value?'':'链接缺少验证信息，请重新申请邮件。');
async function submit(){
 if(busy.value)return;if(password.value!==confirmation.value){error.value='两次输入的密码不同。';return}
 if(!/^[A-Za-z0-9]{8,20}$/.test(password.value)){error.value='密码须为 8–20 个字符，只能包含数字和英文字母。';return}
 busy.value=true;error.value='';
 try{message.value=(await http.post('/auth/reset-password',{token:token.value,password:password.value})).data.message;token.value=password.value=confirmation.value='';showPassword.value=showConfirmation.value=false;auth.clearAccount();window.history.replaceState(window.history.state,'',route.path)}
 catch(err){error.value=apiErrorMessage(err)}
 finally{busy.value=false}
}
</script>
