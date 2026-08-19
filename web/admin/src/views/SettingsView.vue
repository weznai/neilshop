<script setup>
import { onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'

const tab = ref('shipping')
const settings = ref({})
const templates = ref([])
const loaded = ref(false)
const edited = reactive({})

onMounted(async () => {
  try {
    settings.value = await req('GET', '/api/admin/ops/settings')
    Object.assign(edited, settings.value)
  } catch (_) { /* */ }
  try { templates.value = (await req('GET', '/api/admin/ops/email-templates')).items || [] } catch (_) { /* */ }
  loaded.value = true
})

async function save() {
  try {
    await req('PUT', '/api/admin/ops/settings', { ...edited })
    settings.value = { ...edited }
    window.$gmToast('设置已保存 ✓', 'success')
  } catch (e) { window.$gmToast('保存失败：' + (e.message || ''), 'error') }
}
async function preview(t) {
  try {
    const d = await req('POST', `/api/admin/ops/email-templates/${t.code}/preview`, { to: 'preview@glowmag.com' })
    window.open('data:text/html;charset=utf-8,' + encodeURIComponent(d.html || d.body || ''), '_blank')
  } catch (e) { window.$gmToast('预览失败：' + (e.message || ''), 'error') }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">系统设置</h1>
      <span style="font-size:12.5px;color:var(--gray)">运费 / 支付 / 税费 / 邮件</span>
    </div>
    <button class="btn btn-primary" @click="save">保存全部</button>
  </div>

  <div class="otab" style="display:flex;gap:4px;border-bottom:1.5px solid var(--gray-light);margin-bottom:14px">
    <button
      v-for="[k, label] in [['shipping', '运费与履约'], ['payment', '支付'], ['tax', '税费'], ['email', '邮件模板']]"
      :key="k"
      style="padding:9px 16px;font-size:13.5px;font-weight:600;border:none;background:none;cursor:pointer"
      :style="{ color: tab === k ? 'var(--plum)' : 'var(--gray)', borderBottom: tab === k ? '2.5px solid var(--plum)' : '2.5px solid transparent' }"
      @click="tab = k"
    >{{ label }}</button>
  </div>

  <div v-if="tab === 'shipping'" class="card" style="padding:20px;max-width:560px">
    <div class="setrow field"><label>免邮门槛（分）</label><input v-model.number="edited.free_ship_over" class="input" type="number" style="width:160px"></div>
    <div class="setrow field"><label>标准运费（分）</label><input v-model.number="edited.std_shipping" class="input" type="number" style="width:160px"></div>
    <div class="setrow field"><label>快递运费（分）</label><input v-model.number="edited.exp_shipping" class="input" type="number" style="width:160px"></div>
    <div class="setrow field"><label>超时关单（分钟）</label><input v-model.number="edited.order_expire_min" class="input" type="number" style="width:160px"></div>
  </div>

  <div v-else-if="tab === 'payment'" class="card" style="padding:20px;max-width:560px">
    <div class="setrow"><div><b>Stripe</b><div style="font-size:12px;color:var(--gray)">卡支付主通道（密钥走 GM_STRIPE_KEY 环境变量，界面不可见）</div></div>
      <span class="tag tag-done">已配置/模拟</span></div>
    <div class="setrow"><div><b>PayPal</b><div style="font-size:12px;color:var(--gray)">沙箱模式 · GM_PAYPAL_* 环境变量</div></div>
      <span class="tag tag-paid">沙箱</span></div>
    <div class="setrow"><div><b>Klarna</b><div style="font-size:12px;color:var(--gray)">先买后付（经 Stripe）</div></div>
      <span class="tag" :class="edited.klarna_enabled ? 'tag-done' : 'tag-pending'">{{ edited.klarna_enabled ? '启用' : '关闭' }}</span></div>
  </div>

  <div v-else-if="tab === 'tax'" class="card" style="padding:20px;max-width:560px">
    <div class="setrow field"><label>默认税率 %</label><input v-model.number="edited.tax_default" class="input" type="number" step="0.01" style="width:160px"></div>
    <p style="font-size:12.5px;color:var(--gray)">州级税表按收货州自动匹配（测试口径：NY 8.875% / CA 9.5% / TX 8.25%…）。</p>
  </div>

  <div v-else class="card" style="padding:0">
    <div v-for="t in templates" :key="t.code" class="setrow" style="padding:14px 18px;border-bottom:1px solid var(--gray-light)">
      <div><b>{{ t.name || t.code }}</b><div style="font-size:12px;color:var(--gray)">{{ t.code }} · 触发：{{ t.trigger || '—' }}</div></div>
      <button class="btn btn-secondary btn-sm" @click="preview(t)">👁 预览</button>
    </div>
    <div v-if="loaded && !templates.length" style="text-align:center;color:var(--gray);padding:24px 0">暂无模板</div>
  </div>
</template>
