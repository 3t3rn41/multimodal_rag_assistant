<template>
 <section class="model-settings page-width">
  <header class="page-head"><div><h1>模型状态</h1><p>问答、检索和精排由服务器统一配置。</p></div><span class="settings-owner"><Icon name="shield"/>系统配置 · 只读</span></header>
  <p v-if="error" class="error-item" role="alert">{{ error }}<button class="btn btn-ghost btn-sm" @click="load">重新加载</button></p>
  <div v-if="models.loading" class="settings-loading" role="status" aria-label="正在读取模型配置"><div class="skeleton"/><div class="skeleton"/></div>
  <section v-if="models.config" class="model-panel">
   <div class="model-description"><span class="model-section-icon"><Icon name="chat"/></span><h2>回答模型</h2><p>阅读检索到的资料，生成有依据的回答。</p><span class="key-state" :class="{configured:models.config.llm_key_configured}">{{ models.config.llm_key_configured?'密钥已配置':'密钥未配置' }}</span></div>
   <div class="model-form">
    <dl class="readonly-config"><dt>模型名称</dt><dd>{{ models.config.llm_model||'尚未配置' }}</dd><dt>服务地址</dt><dd>{{ models.config.llm_base_url||'地址配置无效' }}</dd></dl>
    <p v-if="!models.config.configured" class="test-failure" role="status">问答模型尚未就绪，请联系管理员配置服务器并重启服务。</p>
    <div class="model-test"><button type="button" class="btn btn-ghost btn-sm" :disabled="busy||!models.config.configured" @click="test"><Icon name="plug"/>{{ busy?'正在测试…':'测试连接' }}</button><span v-if="result.text" :class="result.ok?'test-success':'test-failure'" role="status">{{ result.text }}</span><span v-else>测试当前系统回答模型</span></div>
   </div>
  </section>
  <section class="model-help"><h2>系统检索模型</h2><p>向量模型：<code>jina-embeddings-v5-omni-small</code> · 1024 维</p><p>精排模型：<code>jina-reranker-v3</code></p><p>更换回答模型不会改变文档向量。</p><p v-if="models.config?.system_models?.configured===false" class="test-failure" role="status">系统检索配置尚未就绪，请联系管理员检查服务器配置。</p></section>
  <section class="model-help"><h2>使用说明</h2><p>密钥由服务器保存，网页仅显示配置状态。</p><p>测试和问答会调用模型服务，可能产生费用；相关文档片段会发送给检索、精排和问答服务。</p><p>文档处理服务：<span :class="worker?.online?'test-success':''">{{ worker?worker.online?'在线':'暂未连接':'状态暂不可用' }}</span>。</p></section>
 </section>
</template>
<script setup lang="ts">
import {ref,reactive,onMounted} from 'vue';
import Icon from '../../components/common/Icon.vue';
import {http,apiErrorMessage} from '../../api/http';
import {useWorkbenchModels} from '../../composables/useWorkbench';
const models=useWorkbenchModels();
const busy=ref(false),error=ref(''),worker=ref<{online:boolean}|null>(null);
const result=reactive({ok:false,text:''});
async function test(){
 if(busy.value||!models.configured)return;busy.value=true;error.value=result.text='';result.ok=false;
 try{result.text=(await http.post('/users/me/models/test-llm')).data.message;result.ok=true}
 catch(err){result.text=apiErrorMessage(err,'连接测试失败')}
 finally{busy.value=false}
}
async function load(){error.value='';try{await models.load()}catch(err){error.value=apiErrorMessage(err,'配置读取失败')}try{worker.value=(await http.get('/system/worker')).data}catch{worker.value=null}}
onMounted(load);
</script>
<style scoped>
.readonly-config{margin-bottom:20px}.readonly-config dt{font-size:12px;color:var(--ink-mute);margin-bottom:6px}.readonly-config dd{margin:0 0 18px;overflow-wrap:anywhere;font-size:14px}

.model-settings{max-width:960px}.settings-owner{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--ink-mute);padding-top:8px;white-space:nowrap}.settings-owner svg{width:15px;height:15px}
.model-settings>.error-item{margin-bottom:20px}.model-panel{display:grid;grid-template-columns:220px minmax(0,1fr);gap:40px;padding:32px 0;border:0;border-top:1px solid var(--line);min-width:0}
.model-section-icon{display:grid;place-items:center;width:38px;height:38px;background:var(--bg);border:1px solid var(--line-soft);border-radius:10px;color:var(--ink-mute);margin-bottom:16px}.model-section-icon svg{width:18px;height:18px}.model-description h2{font-size:18px;font-weight:600}.model-description p{font-size:13px;line-height:1.8;color:var(--ink-mute);margin-top:10px;max-width:24ch}.key-state{display:inline-block;font-size:11px;color:var(--ink-faint);margin-top:18px}.key-state.configured{color:var(--ok)}
.model-form{max-width:540px;width:100%}
.model-test{display:flex;align-items:center;gap:12px;margin-top:20px;font-size:11px;color:var(--ink-faint);flex-wrap:wrap}.model-test>span{flex:1;min-width:160px;overflow-wrap:anywhere;line-height:1.8}.test-success{color:var(--ok)}.test-failure{color:var(--err)}
.model-help{background:var(--bg);padding:24px;border-radius:12px;margin-top:12px;font-size:12px;line-height:1.9;color:var(--ink-mute)}.model-help h2{font-size:13px;font-weight:600;color:var(--ink-soft);margin-bottom:10px}.model-help p+p{margin-top:6px}.model-help code{font-size:11px;overflow-wrap:anywhere}
.settings-loading{display:flex;flex-direction:column;gap:24px}.settings-loading .skeleton{height:84px}
@media(max-width:1023px){.model-panel{grid-template-columns:170px minmax(0,1fr);gap:28px}}
@media(max-width:767px){.model-panel{grid-template-columns:minmax(0,1fr);gap:24px;padding:28px 0}.model-description{display:grid;grid-template-columns:38px 1fr;gap:6px 12px}.model-section-icon{grid-row:1/3;margin:0}.model-description p{grid-column:2;max-width:none;margin:0}.key-state{grid-column:2;margin:4px 0 0}.model-form{max-width:none}.settings-owner{display:none}}
</style>
