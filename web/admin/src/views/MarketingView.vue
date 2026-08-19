<script setup>
import { onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'

const tab = ref('discounts')
const discounts = ref([])
const rates = ref([])
const bundles = reactive({ b2: 15, b3: 20 })
const loaded = ref(false)
const newCode = reactive({ code: '', type: 'pct', value: 20, min: 0, max: 10, active: true })

async function load() {
  loaded.value = false
  try { discounts.value = (await req('GET', '/api/admin/ops/discounts?page=1&size=100')).items || [] } catch (_) { /* */ }
  try { rates.value = (await req('GET', '/api/admin/trade/shipping-rates')).items || [] } catch (_) { /* */ }
  try {
    const s = await req('GET', '/api/admin/ops/settings')
    if (s.bundle_2_off != null) bundles.b2 = s.bundle_2_off
    if (s.bundle_3_off != null) bundles.b3 = s.bundle_3_off
  } catch (_) { /* */ }
  loaded.value = true
}
onMounted(load)

async function toggleCode(c) {
  await req('PUT', '/api/admin/ops/discounts/' + c.id, { active: c.active ? 0 : 1 })
  c.active = c.active ? 0 : 1
  window.$gmToast('已' + (c.active ? '启用' : '停用') + ' ✓', 'success')
}
async function addCode() {
  if (!newCode.code) { window.$gmToast('折扣码必填', 'error'); return }
  try {
    await req('POST', '/api/admin/ops/discounts', { ...newCode })
    newCode.code = ''
    discounts.value = (await req('GET', '/api/admin/ops/discounts?page=1&size=100')).items || []
    window.$gmToast('折扣码已创建 ✓', 'success')
  } catch (e) { window.$gmToast('创建失败：' + (e.message || ''), 'error') }
}
async function saveBundles() {
  try {
    await req('PUT', '/api/admin/ops/settings', { bundle_2_off: bundles.b2, bundle_3_off: bundles.b3 })
    window.$gmToast('捆绑折扣已保存（结算即时生效）✓', 'success')
  } catch (e) { window.$gmToast('保存失败：' + (e.message || ''), 'error') }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">营销工具</h1>
      <span style="font-size:12.5px;color:var(--gray)">折扣码 / 运费模板 / 捆绑折扣</span>
    </div>
  </div>

  <div class="otab" style="display:flex;gap:4px;border-bottom:1.5px solid var(--gray-light);margin-bottom:14px">
    <button
      v-for="[k, label] in [['discounts', '折扣码'], ['rates', '运费模板'], ['bundles', '捆绑折扣']]"
      :key="k"
      style="padding:9px 16px;font-size:13.5px;font-weight:600;border:none;background:none;cursor:pointer"
      :style="{ color: tab === k ? 'var(--plum)' : 'var(--gray)', borderBottom: tab === k ? '2.5px solid var(--plum)' : '2.5px solid transparent' }"
      @click="tab = k"
    >{{ label }}</button>
  </div>

  <!-- 折扣码 -->
  <template v-if="tab === 'discounts'">
    <div class="card" style="padding:18px;margin-bottom:14px">
      <h3 style="font-size:14.5px;margin-bottom:12px">➕ 新建折扣码</h3>
      <div style="display:grid;grid-template-columns:1.2fr .9fr .6fr .6fr .6fr auto;gap:10px;align-items:end">
        <div class="field"><label>码</label><input v-model="newCode.code" class="input" placeholder="SUMMER30" style="text-transform:uppercase"></div>
        <div class="field"><label>类型</label>
          <select v-model="newCode.type" class="input"><option value="pct">百分比</option><option value="fixed">固定减免</option><option value="ship">免邮</option></select>
        </div>
        <div class="field"><label>值</label><input v-model.number="newCode.value" class="input" type="number"></div>
        <div class="field"><label>门槛</label><input v-model.number="newCode.min" class="input" type="number"></div>
        <div class="field"><label>上限</label><input v-model.number="newCode.max" class="input" type="number"></div>
        <button class="btn btn-primary" @click="addCode">创建</button>
      </div>
    </div>
    <div class="card" style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:10px">码</th><th>规则</th><th>已用</th><th>状态</th><th style="text-align:right">操作</th></tr></thead>
        <tbody>
          <tr v-for="c in discounts" :key="c.id" style="border-top:1px solid var(--gray-light)">
            <td style="padding:11px 10px"><b>{{ c.code }}</b></td>
            <td>{{ c.type === 'pct' ? `${c.value}% off` : c.type === 'fixed' ? `$${(c.value / 100).toFixed(2)} off` : 'Free shipping' }}{{ c.min_subtotal ? ` · 满 $${(c.min_subtotal / 100).toFixed(2)}` : '' }}</td>
            <td style="color:var(--gray)">{{ c.used_count ?? 0 }}</td>
            <td><span class="tag" :class="c.active ? 'tag-paid' : 'tag-pending'">{{ c.active ? '启用' : '停用' }}</span></td>
            <td style="text-align:right"><button class="btn btn-ghost btn-sm" @click="toggleCode(c)">{{ c.active ? '停用' : '启用' }}</button></td>
          </tr>
        </tbody>
      </table>
      <div v-if="loaded && !discounts.length" style="text-align:center;color:var(--gray);padding:24px 0">暂无折扣码</div>
    </div>
  </template>

  <!-- 运费模板 -->
  <div v-else-if="tab === 'rates'" class="card" style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:10px">目的地</th><th>承运</th><th>方式</th><th>运费</th><th>免邮门槛</th><th>时效</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="r in rates" :key="r.id" style="border-top:1px solid var(--gray-light)">
          <td style="padding:11px 10px"><b>{{ r.dest_country || '*' }}</b></td>
          <td>{{ r.carrier }}</td>
          <td>{{ r.method }}</td>
          <td><b>${{ ((r.rate || 0) / 100).toFixed(2) }}</b></td>
          <td style="color:var(--gray)">{{ r.free_over ? '$' + (r.free_over / 100).toFixed(2) : '—' }}</td>
          <td style="color:var(--gray)">{{ r.eta_days || '—' }}</td>
          <td><span class="tag" :class="r.active ? 'tag-paid' : 'tag-pending'">{{ r.active ? '启用' : '停用' }}</span></td>
        </tr>
      </tbody>
    </table>
    <div v-if="loaded && !rates.length" style="text-align:center;color:var(--gray);padding:24px 0">暂无运费模板（使用默认运费）</div>
  </div>

  <!-- 捆绑折扣 -->
  <div v-else class="card" style="padding:20px;max-width:460px">
    <h3 style="font-size:14.5px;margin-bottom:6px">🎁 捆绑折扣（结算即时生效）</h3>
    <p style="font-size:12.5px;color:var(--gray);margin-bottom:14px">两件 / 三件及以上的购物车整单折扣比例（%，0 = 关闭该档）。</p>
    <div class="field"><label>买 2 件折扣 %</label><input v-model.number="bundles.b2" class="input" type="number" min="0" max="50"></div>
    <div class="field"><label>买 3+ 件折扣 %</label><input v-model.number="bundles.b3" class="input" type="number" min="0" max="50"></div>
    <button class="btn btn-primary" style="margin-top:12px" @click="saveBundles">保存</button>
  </div>
</template>
