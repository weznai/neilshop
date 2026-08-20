<script setup>
import { onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'

const tab = ref('discounts')
const discounts = ref([])
const rates = ref([])
const popups = ref([])
const loaded = ref(false)
const loadErr = ref(false)

/* settings 是 k-v 列表 → 转对象（bundle 缺省回退 pricing.py 默认 15/20，避免 undefined 保存 422） */
const settings = reactive({ bundle_2_off: 15, bundle_3_off: 20 })
const BUNDLE_KEYS = { b2: 'bundle_2_off', b3: 'bundle_3_off' }

const showNew = ref(false)
/* DiscountCreateIn: type int 1-3（1=pct 2=fixed 3=ship）、value 分、starts_at 必填 */
const NEW_CODE = { code: '', type: 1, value: 20, min_subtotal: 0, max_discount: null, usage_limit: null, per_user_limit: 1, first_order_only: 0, days: 30 }
const newCode = reactive({ ...NEW_CODE })
/* 弹窗开关整体重置（对齐 newPopup 的做法，避免残留上次输入） */
function openNew() { Object.assign(newCode, NEW_CODE); showNew.value = true }
function closeNew() { Object.assign(newCode, NEW_CODE); showNew.value = false }

/* 弹窗（PopupCreateIn/PopupUpdateIn）：trigger_rules 为 JSON dict {delaySec,exitIntent,mobileOnly} */
const POPUP_SCENES = { welcome: '欢迎订阅', exit_intent: '离开挽留', newsletter: '邮件引导' }
const sceneLabel = (s) => POPUP_SCENES[s] || s
const popupDlg = ref(false)
const popupForm = reactive({ id: null, scene: 'welcome', title: '', content_md: '', coupon_code: '', delaySec: 7, exitIntent: false, mobileOnly: false, start_at: '', end_at: '', active: 0 })
/* datetime-local 值 YYYY-MM-DDTHH:mm ↔ 后端 naive ISO（YYYY-MM-DDTHH:mm:ss）直通，避免时区二次偏移 */
const dtIn = (iso) => (iso || '').slice(0, 16)
const dtOut = (v) => (v ? v + ':00' : null)

async function load() {
  loaded.value = false
  loadErr.value = false
  let failed = 0
  try { discounts.value = (await req('GET', '/api/admin/ops/discounts?page=1&size=100')).items || [] }
  catch (e) { failed++; toast('折扣码加载失败：' + (e.message || ''), 'error') }
  try { rates.value = (await req('GET', '/api/admin/trade/shipping-rates')).items || [] }
  catch (e) { failed++; toast('运费模板加载失败：' + (e.message || ''), 'error') }
  try { popups.value = (await req('GET', '/api/admin/ops/popups')).items || [] }
  catch (e) { failed++; toast('弹窗配置加载失败：' + (e.message || ''), 'error') }
  try {
    const rows = (await req('GET', '/api/admin/ops/settings')).items || []
    for (const r of rows) if (r.key in settings) settings[r.key] = r.value
  } catch (e) { failed++; toast('捆绑折扣参数加载失败：' + (e.message || ''), 'error') }
  if (failed) loadErr.value = true
  loaded.value = true
}
onMounted(load)

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
const TYPE_LABEL = { 1: (v) => `${v}% off`, 2: (v) => `${money(v)} off`, 3: () => '免邮' }
/* ends_at 为 naive UTC：按 UTC 日期比较判定「已过期」（天级，避免本地时区偏移误标） */
const todayUtc = () => new Date().toISOString().slice(0, 10)
const isExpired = (c) => !!(c.ends_at && c.ends_at.slice(0, 10) < todayUtc())

async function toggleCode(c) {
  try {
    await req('POST', `/api/admin/ops/discounts/${c.id}/toggle`)
    c.is_active = c.is_active ? 0 : 1
    toast(c.is_active ? '已启用 ✓' : '已停用 ✓', 'success')
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}
async function addCode() {
  if (!newCode.code) { toast('折扣码必填', 'error'); return }
  if (newCode.type === 1 && (newCode.value <= 0 || newCode.value > 100)) { toast('百分比折扣需在 1-100 之间', 'error'); return }
  try {
    await req('POST', '/api/admin/ops/discounts', {
      code: newCode.code.toUpperCase().trim(),
      type: newCode.type,
      /* 免邮码 value 恒为 0（后端校验 ge=0，且计价只看 free_shipping 标记） */
      value: newCode.type === 1 ? Math.round(newCode.value) : newCode.type === 2 ? Math.round(newCode.value * 100) : 0,
      min_subtotal: Math.round((newCode.min_subtotal || 0) * 100),
      max_discount: newCode.type === 1 && newCode.max_discount ? Math.round(newCode.max_discount * 100) : null,
      usage_limit: newCode.usage_limit ? Math.round(newCode.usage_limit) : null,
      per_user_limit: Math.round(newCode.per_user_limit || 1),
      first_order_only: newCode.first_order_only ? 1 : 0,
      starts_at: new Date().toISOString().slice(0, 19),
      ends_at: newCode.days > 0 ? new Date(Date.now() + newCode.days * 864e5).toISOString().slice(0, 19) : null,
    })
    showNew.value = false
    Object.assign(newCode, NEW_CODE)
    discounts.value = (await req('GET', '/api/admin/ops/discounts?page=1&size=100')).items || []
    toast('折扣码已创建 ✓', 'success')
  } catch (e) { toast('创建失败：' + (JSON.stringify(e.data?.detail || e.message)).slice(0, 120), 'error') }
}

/* 一键复制折扣码（clipboard API 失败降级 execCommand，再失败提示手动复制） */
async function copyCode(c) {
  try {
    await navigator.clipboard.writeText(c.code)
    toast('已复制 ' + c.code + ' ✓', 'success')
  } catch (_) {
    try {
      const ta = document.createElement('textarea')
      ta.value = c.code
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      toast('已复制 ' + c.code + ' ✓', 'success')
    } catch (_) { toast('复制失败，请手动复制 ' + c.code, 'error') }
  }
}

/* 编辑折扣码（PUT DiscountUpdateIn 全可选：value/门槛/封顶/次数/有效期） */
const editDlg = ref(false)
const editCode = reactive({ id: null, code: '', type: 1, value: 20, min_subtotal: 0, max_discount: null, usage_limit: null, per_user_limit: 1, starts_at: '', ends_at: '' })
function editDiscount(c) {
  Object.assign(editCode, {
    id: c.id,
    code: c.code,
    type: c.type,
    value: c.type === 2 ? (c.value || 0) / 100 : (c.value || 0),
    min_subtotal: (c.min_subtotal || 0) / 100,
    max_discount: c.max_discount ? c.max_discount / 100 : null,
    usage_limit: c.usage_limit ?? null,
    per_user_limit: c.per_user_limit ?? 1,
    starts_at: dtIn(c.starts_at),
    ends_at: dtIn(c.ends_at),
  })
  editDlg.value = true
}
async function saveEdit() {
  if (editCode.type === 1 && (editCode.value <= 0 || editCode.value > 100)) { toast('百分比折扣需在 1-100 之间', 'error'); return }
  try {
    await req('PUT', '/api/admin/ops/discounts/' + editCode.id, {
      value: editCode.type === 1 ? Math.round(editCode.value) : editCode.type === 2 ? Math.round(editCode.value * 100) : 0,
      min_subtotal: Math.round((editCode.min_subtotal || 0) * 100),
      max_discount: editCode.type === 1 && editCode.max_discount ? Math.round(editCode.max_discount * 100) : null,
      usage_limit: editCode.usage_limit ? Math.round(editCode.usage_limit) : null,
      per_user_limit: Math.round(editCode.per_user_limit || 1),
      starts_at: dtOut(editCode.starts_at),
      ends_at: dtOut(editCode.ends_at),
    })
    editDlg.value = false
    discounts.value = (await req('GET', '/api/admin/ops/discounts?page=1&size=100')).items || []
    toast('折扣码已保存 ✓', 'success')
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}

/* ===== 弹窗管理（GET/POST /api/admin/ops/popups + PUT/{id} + /{id}/toggle，stats 保留不清零） ===== */
function newPopup() {
  Object.assign(popupForm, { id: null, scene: 'welcome', title: '', content_md: '', coupon_code: '', delaySec: 7, exitIntent: false, mobileOnly: false, start_at: '', end_at: '', active: 0 })
  popupDlg.value = true
}
function editPopup(p) {
  Object.assign(popupForm, {
    id: p.id,
    scene: p.scene,
    title: p.title || '',
    content_md: p.content_md || '',
    coupon_code: p.coupon_code || '',
    delaySec: p.trigger_rules?.delaySec ?? 7,
    exitIntent: !!p.trigger_rules?.exitIntent,
    mobileOnly: !!p.trigger_rules?.mobileOnly,
    start_at: dtIn(p.start_at),
    end_at: dtIn(p.end_at),
    active: p.active ? 1 : 0,
  })
  popupDlg.value = true
}
async function savePopup() {
  if (!popupForm.title.trim()) { toast('标题必填', 'error'); return }
  const body = {
    scene: popupForm.scene.trim().toLowerCase(),
    title: popupForm.title.trim(),
    content_md: popupForm.content_md || null,
    coupon_code: popupForm.coupon_code ? popupForm.coupon_code.trim().toUpperCase() : null,
    trigger_rules: { delaySec: Math.round(popupForm.delaySec || 0), exitIntent: !!popupForm.exitIntent, mobileOnly: !!popupForm.mobileOnly },
    start_at: dtOut(popupForm.start_at),
    end_at: dtOut(popupForm.end_at),
    active: popupForm.active ? 1 : 0,
  }
  try {
    if (popupForm.id) await req('PUT', '/api/admin/ops/popups/' + popupForm.id, body)
    else await req('POST', '/api/admin/ops/popups', body)
    popupDlg.value = false
    popups.value = (await req('GET', '/api/admin/ops/popups')).items || []
    toast(popupForm.id ? '弹窗已保存 ✓' : '弹窗已创建 ✓', 'success')
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}
async function togglePopup(p) {
  try {
    await req('POST', `/api/admin/ops/popups/${p.id}/toggle`)
    p.active = p.active ? 0 : 1
    toast(p.active ? '已启用 ✓' : '已停用 ✓', 'success')
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}
async function saveBundle(key) {
  try {
    await req('PUT', '/api/admin/ops/settings', { key: BUNDLE_KEYS[key], value: Number(settings[BUNDLE_KEYS[key]]) || 0 })
    toast('已保存（结算即时生效）✓', 'success')
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}

/* ===== 运费模板管理（后端：GET/POST + PUT price/free_over/eta/active） ===== */
async function toggleRate(r) {
  try {
    await req('PUT', `/api/admin/trade/shipping-rates/${r.id}`, { active: !r.active })
    r.active = !r.active
    toast(r.active ? '已启用 ✓' : '已停用 ✓', 'success')
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}

const rateDlg = ref(false)
const rateForm = reactive({ id: null, dest_country: 'US', carrier: 'usps', method: 'standard', price: 499, free_over: null, eta_min_days: 3, eta_max_days: 7, max_weight_g: 500 })
function newRate() {
  Object.assign(rateForm, { id: null, dest_country: 'US', carrier: 'usps', method: 'standard', price: 499, free_over: null, eta_min_days: 3, eta_max_days: 7, max_weight_g: 500 })
  rateDlg.value = true
}
function editRate(r) {
  Object.assign(rateForm, {
    id: r.id, dest_country: r.dest_country, carrier: r.carrier, method: r.method,
    price: r.price, free_over: r.free_over, eta_min_days: r.eta_min_days, eta_max_days: r.eta_max_days,
  })
  rateDlg.value = true
}
async function saveRate() {
  if (rateForm.eta_max_days < rateForm.eta_min_days) { toast('最大时效不能小于最小时效', 'error'); return }
  try {
    if (rateForm.id) {
      await req('PUT', `/api/admin/trade/shipping-rates/${rateForm.id}`, {
        price: Math.round(rateForm.price), free_over: rateForm.free_over ? Math.round(rateForm.free_over) : null,
        eta_min_days: rateForm.eta_min_days | 0, eta_max_days: rateForm.eta_max_days | 0,
      })
      toast('运费模板已保存 ✓', 'success')
    } else {
      await req('POST', '/api/admin/trade/shipping-rates', {
        dest_country: rateForm.dest_country.trim().toUpperCase(), carrier: rateForm.carrier.trim().toLowerCase(),
        method: rateForm.method, price: Math.round(rateForm.price),
        free_over: rateForm.free_over ? Math.round(rateForm.free_over) : null,
        eta_min_days: rateForm.eta_min_days | 0, eta_max_days: rateForm.eta_max_days | 0,
        max_weight_g: rateForm.max_weight_g | 0 || 500,
      })
      toast('运费模板已创建 ✓', 'success')
    }
    rateDlg.value = false
    rates.value = (await req('GET', '/api/admin/trade/shipping-rates')).items || []
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">营销工具</h1>
      <span style="font-size:12.5px;color:var(--gray)">折扣码 / 运费模板 / 捆绑折扣 / 弹窗</span>
    </div>
  </div>

  <div class="otab" style="display:flex;gap:4px;border-bottom:1.5px solid var(--gray-light);margin-bottom:14px">
    <button
      v-for="[k, label] in [['discounts', '折扣码'], ['rates', '运费模板'], ['bundles', '捆绑折扣'], ['popups', '弹窗']]"
      :key="k"
      style="padding:9px 16px;font-size:13.5px;font-weight:600;border:none;background:none;cursor:pointer"
      :style="{ color: tab === k ? 'var(--plum)' : 'var(--gray)', borderBottom: tab === k ? '2.5px solid var(--plum)' : '2.5px solid transparent' }"
      @click="tab = k"
    >{{ label }}</button>
  </div>

  <!-- 折扣码 -->
  <template v-if="tab === 'discounts'">
    <div class="card" style="padding:16px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:13.5px;color:var(--gray)">共 {{ discounts.length }} 个码 · 启用 {{ discounts.filter((c) => c.is_active).length }}<span v-if="discounts.some((c) => isExpired(c))"> · {{ discounts.filter((c) => isExpired(c)).length }} 个已过期</span></span>
      <button class="btn btn-primary btn-sm" @click="openNew">＋ 新建折扣码</button>
    </div>
    <div v-if="loadErr" style="width:100%;display:flex;justify-content:space-between;align-items:center;padding:10px 14px;background:#FDECEC;border:1px solid var(--error);border-radius:10px;font-size:12.5px;color:var(--error)">
      <span>⚠️ 部分数据加载失败，展示的可能不是最新配置</span>
      <button class="btn btn-secondary btn-sm" @click="load">重试</button>
    </div>
    <div v-if="!loaded" class="card skeleton" style="min-height:220px"></div>
    <div v-else class="card tbl-wrap">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:10px">码</th><th>规则</th><th>门槛/上限</th><th>已用</th><th>有效期</th><th>状态</th><th style="text-align:right">操作</th></tr></thead>
        <tbody>
          <tr v-for="c in discounts" :key="c.id" style="border-top:1px solid var(--gray-light)">
            <td style="padding:11px 10px;white-space:nowrap"><b>{{ c.code }}</b>
              <button class="btn btn-ghost btn-sm" style="margin-left:4px;padding:2px 7px" title="复制折扣码" @click="copyCode(c)">⧉</button>
            </td>
            <td>{{ (TYPE_LABEL[c.type] || (() => '—'))(c.value) }}</td>
            <td style="color:var(--gray)">
              {{ c.min_subtotal ? '满 ' + money(c.min_subtotal) : '无门槛' }}
              <span v-if="c.max_discount">· 封顶 {{ money(c.max_discount) }}</span>
              <span v-if="c.per_user_limit > 1">· 限{{ c.per_user_limit }}次/人</span>
              <span v-if="c.first_order_only">· 仅首单</span>
            </td>
            <td style="color:var(--gray)">{{ c.used_count ?? 0 }}<span v-if="c.usage_limit">/{{ c.usage_limit }}</span></td>
            <td style="color:var(--gray);font-size:12px">{{ (c.starts_at || '').slice(0, 10) }} ~ {{ c.ends_at ? c.ends_at.slice(0, 10) : '∞' }}</td>
            <td style="white-space:nowrap">
              <span v-if="c.is_active && isExpired(c)" class="tag tag-error">已过期</span>
              <span v-else class="tag" :class="c.is_active ? 'tag-paid' : 'tag-pending'">{{ c.is_active ? '启用' : '停用' }}</span>
            </td>
            <td style="text-align:right;white-space:nowrap">
              <button class="btn btn-secondary btn-sm" @click="editDiscount(c)">编辑</button>
              <button class="btn btn-ghost btn-sm" style="margin-left:4px" @click="toggleCode(c)">{{ c.is_active ? '停用' : '启用' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="loaded && !discounts.length" style="text-align:center;color:var(--gray);padding:28px 0">🏷️ 暂无折扣码，点击右上角「新建折扣码」创建第一个</div>
    </div>

    <div v-if="showNew" class="modal open" @click.self="closeNew">
      <div class="modal-box" style="max-width:520px">
        <button class="modal-x" @click="closeNew">×</button>
        <h3 style="font-family:var(--font-title);margin-bottom:6px">➕ 新建折扣码</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div class="field"><label>码</label><input v-model="newCode.code" class="input" placeholder="SUMMER30" style="text-transform:uppercase"></div>
          <div class="field"><label>类型</label>
            <select v-model.number="newCode.type" class="input">
              <option :value="1">百分比（%）</option><option :value="2">固定减免（$）</option><option :value="3">免邮</option>
            </select>
          </div>
          <div v-if="newCode.type !== 3" class="field"><label>{{ newCode.type === 1 ? '折扣 %' : '减免 $' }}</label>
            <input v-model.number="newCode.value" class="input" type="number"></div>
          <div class="field"><label>门槛 $（0=无）</label><input v-model.number="newCode.min_subtotal" class="input" type="number"></div>
          <div v-if="newCode.type === 1" class="field"><label>封顶 $（可选，%码适用）</label><input v-model.number="newCode.max_discount" class="input" type="number"></div>
          <div class="field"><label>有效天数（0=永久）</label><input v-model.number="newCode.days" class="input" type="number"></div>
          <div class="field"><label>总次数（空=不限）</label><input v-model.number="newCode.usage_limit" class="input" type="number" min="1"></div>
          <div class="field"><label>每人限用次数</label><input v-model.number="newCode.per_user_limit" class="input" type="number" min="1"></div>
        </div>
        <label style="display:flex;gap:10px;align-items:center;font-size:13.5px;cursor:pointer;margin-top:10px">
          <input v-model="newCode.first_order_only" type="checkbox" style="width:16px;height:16px"> 仅限首单使用
        </label>
        <button class="btn btn-primary btn-block" style="margin-top:14px" @click="addCode">创建</button>
      </div>
    </div>

    <!-- 编辑折扣码（value/门槛/封顶/次数/有效期；code 与启停走行内/独立入口） -->
    <div v-if="editDlg" class="modal open" @click.self="editDlg = false">
      <div class="modal-box" style="max-width:520px">
        <button class="modal-x" @click="editDlg = false">×</button>
        <h3 style="font-family:var(--font-title);margin-bottom:6px">✏️ 编辑折扣码 {{ editCode.code }}</h3>
        <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">类型不可更改；金额单位为美元，保存时换算为美分。</p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div v-if="editCode.type !== 3" class="field"><label>{{ editCode.type === 1 ? '折扣 %' : '减免 $' }}</label>
            <input v-model.number="editCode.value" class="input" type="number"></div>
          <div class="field"><label>门槛 $（0=无）</label><input v-model.number="editCode.min_subtotal" class="input" type="number"></div>
          <div v-if="editCode.type === 1" class="field"><label>封顶 $（可选）</label><input v-model.number="editCode.max_discount" class="input" type="number"></div>
          <div class="field"><label>总次数（空=不限）</label><input v-model.number="editCode.usage_limit" class="input" type="number" min="1"></div>
          <div class="field"><label>每人限用次数</label><input v-model.number="editCode.per_user_limit" class="input" type="number" min="1"></div>
          <div class="field"><label>开始时间 (UTC)</label><input v-model="editCode.starts_at" class="input" type="datetime-local"></div>
          <div class="field"><label>结束时间 (UTC)（空=永久）</label><input v-model="editCode.ends_at" class="input" type="datetime-local"></div>
        </div>
        <button class="btn btn-primary btn-block" style="margin-top:14px" @click="saveEdit">保存</button>
      </div>
    </div>
  </template>

  <!-- 运费模板 -->
  <template v-else-if="tab === 'rates'">
    <div class="card" style="padding:16px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:13.5px;color:var(--gray)">共 {{ rates.length }} 条 · 启用 {{ rates.filter((r) => r.active).length }} · 结算按「国家→方式」取启用模板</span>
      <button class="btn btn-primary btn-sm" @click="newRate">＋ 新建模板</button>
    </div>
    <div v-if="!loaded" class="card skeleton" style="min-height:220px"></div>
    <div v-else class="card tbl-wrap">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)">
          <th style="padding:10px">目的地</th><th>承运</th><th>方式</th><th>运费</th><th>免邮门槛</th><th>时效（天）</th><th>限重(g)</th><th>状态</th><th style="text-align:right">操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in rates" :key="r.id" style="border-top:1px solid var(--gray-light)">
            <td style="padding:11px 10px"><b>{{ r.dest_country || '*' }}</b></td>
            <td>{{ r.carrier }}</td>
            <td>{{ r.method === 'express' ? '快递' : '标准' }}</td>
            <td><b>{{ money(r.price) }}</b></td>
            <td style="color:var(--gray)">{{ r.free_over ? money(r.free_over) : '—' }}</td>
            <td style="color:var(--gray)">{{ r.eta_min_days ?? '—' }}–{{ r.eta_max_days ?? '—' }}</td>
            <td style="color:var(--gray)">{{ r.max_weight_g ?? '—' }}</td>
            <td><span class="tag" :class="r.active ? 'tag-paid' : 'tag-pending'">{{ r.active ? '启用' : '停用' }}</span></td>
            <td style="text-align:right;white-space:nowrap">
              <button class="btn btn-secondary btn-sm" @click="editRate(r)">编辑</button>
              <button class="btn btn-ghost btn-sm" style="margin-left:4px" @click="toggleRate(r)">{{ r.active ? '停用' : '启用' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="loaded && !rates.length" style="text-align:center;color:var(--gray);padding:28px 0">🚚 暂无运费模板（结算将使用 settings 默认运费）</div>
    </div>

    <div v-if="rateDlg" class="modal open" @click.self="rateDlg = false">
      <div class="modal-box" style="max-width:520px">
        <button class="modal-x" @click="rateDlg = false">×</button>
        <h3 style="font-family:var(--font-title);margin-bottom:6px">{{ rateForm.id ? '编辑运费模板 #' + rateForm.id : '新建运费模板' }}</h3>
        <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">金额单位为美分（分），时效为天。</p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div v-if="!rateForm.id" class="field"><label>目的地（国家码）</label>
            <select v-model="rateForm.dest_country" class="input">
              <option v-for="c in ['US', 'CA', 'GB', 'AU', 'DE', 'FR', 'JP']" :key="c">{{ c }}</option>
            </select>
          </div>
          <div v-if="!rateForm.id" class="field"><label>承运商</label>
            <select v-model="rateForm.carrier" class="input">
              <option>usps</option><option>ups</option><option>fedex</option><option>dhl</option>
            </select>
          </div>
          <div v-if="!rateForm.id" class="field"><label>方式</label>
            <select v-model="rateForm.method" class="input">
              <option value="standard">标准</option><option value="express">快递</option>
            </select>
          </div>
          <div class="field"><label>运费（分）</label><input v-model.number="rateForm.price" class="input" type="number"></div>
          <div class="field"><label>免邮门槛（分，可空）</label><input v-model.number="rateForm.free_over" class="input" type="number"></div>
          <div class="field"><label>最小时效（天）</label><input v-model.number="rateForm.eta_min_days" class="input" type="number"></div>
          <div class="field"><label>最大时效（天）</label><input v-model.number="rateForm.eta_max_days" class="input" type="number"></div>
          <div v-if="!rateForm.id" class="field"><label>限重（g）</label><input v-model.number="rateForm.max_weight_g" class="input" type="number"></div>
        </div>
        <button class="btn btn-primary btn-block" style="margin-top:14px" @click="saveRate">保存</button>
      </div>
    </div>
  </template>

  <!-- 捆绑折扣 -->
  <div v-else-if="tab === 'bundles'" class="card" style="padding:20px;max-width:460px">
    <h3 style="font-size:14.5px;margin-bottom:6px">🎁 捆绑折扣（结算即时生效）</h3>
    <p style="font-size:12.5px;color:var(--gray);margin-bottom:14px">两件 / 三件及以上的购物车整单折扣比例（%，0 = 关闭该档）。</p>
    <div class="field"><label>买 2 件折扣 %</label>
      <div style="display:flex;gap:8px">
        <input v-model.number="settings.bundle_2_off" class="input" type="number" min="0" max="50">
        <button class="btn btn-secondary" @click="saveBundle('b2')">保存</button>
      </div>
    </div>
    <div class="field"><label>买 3+ 件折扣 %</label>
      <div style="display:flex;gap:8px">
        <input v-model.number="settings.bundle_3_off" class="input" type="number" min="0" max="50">
        <button class="btn btn-secondary" @click="saveBundle('b3')">保存</button>
      </div>
    </div>
  </div>

  <!-- 弹窗（PopupConfig 完整 CRUD + 启停；前台按 scene 拉取启用中的最新一条） -->
  <div v-else>
    <div class="card" style="padding:16px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:13.5px;color:var(--gray)">共 {{ popups.length }} 个 · 启用 {{ popups.filter((p) => p.active).length }} · 前台同场景取最新启用且在有效期内的一个</span>
      <button class="btn btn-primary btn-sm" @click="newPopup">＋ 新建弹窗</button>
    </div>
    <div v-if="!loaded" class="card skeleton" style="min-height:220px"></div>
    <div v-else class="card tbl-wrap">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)">
          <th style="padding:10px">场景</th><th>标题 / 券码</th><th>触发规则</th><th>有效期</th><th>曝光/转化</th><th>状态</th><th style="text-align:right">操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="p in popups" :key="p.id" style="border-top:1px solid var(--gray-light)">
            <td style="padding:11px 10px;white-space:nowrap"><b>{{ sceneLabel(p.scene) }}</b><span style="color:var(--gray);font-size:11px;margin-left:4px">{{ p.scene }}</span></td>
            <td style="min-width:180px">
              <b>{{ p.title }}</b>
              <div v-if="p.coupon_code" style="color:var(--plum);font-size:12px;margin-top:2px">🎫 {{ p.coupon_code }}</div>
            </td>
            <td style="color:var(--gray);font-size:12px">
              {{ p.trigger_rules?.delaySec ?? '—' }}s 延迟<span v-if="p.trigger_rules?.exitIntent"> · 离开触发</span><span v-if="p.trigger_rules?.mobileOnly"> · 仅移动端</span>
            </td>
            <td style="color:var(--gray);font-size:12px">{{ p.start_at ? p.start_at.slice(0, 10) : '—' }} ~ {{ p.end_at ? p.end_at.slice(0, 10) : '长期' }}</td>
            <td style="color:var(--gray);font-size:12px">{{ p.stats_shown ?? 0 }} / {{ p.stats_converted ?? 0 }}<span v-if="p.stats_shown">（{{ Math.round((p.stats_converted || 0) * 100 / p.stats_shown) }}%）</span></td>
            <td style="white-space:nowrap">
              <span v-if="p.active && p.end_at && p.end_at.slice(0, 10) < todayUtc()" class="tag tag-error">已到期</span>
              <span v-else class="tag" :class="p.active ? 'tag-paid' : 'tag-pending'">{{ p.active ? '启用' : '停用' }}</span>
            </td>
            <td style="text-align:right;white-space:nowrap">
              <button class="btn btn-secondary btn-sm" @click="editPopup(p)">编辑</button>
              <button class="btn btn-ghost btn-sm" style="margin-left:4px" @click="togglePopup(p)">{{ p.active ? '停用' : '启用' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="loaded && !popups.length" style="text-align:center;color:var(--gray);padding:28px 0">🪟 暂无弹窗配置，点击右上角「新建弹窗」创建</div>
    </div>

    <!-- 弹窗编辑（scene/title/content_md/coupon_code/trigger_rules/有效期/active） -->
    <div v-if="popupDlg" class="modal open" @click.self="popupDlg = false">
      <div class="modal-box" style="max-width:560px">
        <button class="modal-x" @click="popupDlg = false">×</button>
        <h3 style="font-family:var(--font-title);margin-bottom:6px">{{ popupForm.id ? '✏️ 编辑弹窗 #' + popupForm.id : '🪟 新建弹窗' }}</h3>
        <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">前台 GET /api/promo/popup?scene= 按「启用中 + 有效期内 + 最新」取一个展示。</p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div class="field"><label>场景 scene</label>
            <input v-model="popupForm.scene" class="input" list="popup-scenes" placeholder="welcome">
            <datalist id="popup-scenes">
              <option v-for="(name, s) in POPUP_SCENES" :key="s" :value="s">{{ name }}</option>
            </datalist>
          </div>
          <div class="field"><label>券码（可选，会展示给用户）</label><input v-model="popupForm.coupon_code" class="input" placeholder="WELCOME20" style="text-transform:uppercase"></div>
          <div class="field" style="grid-column:1/-1"><label>标题 *</label><input v-model="popupForm.title" class="input" placeholder="Get 20% off your first set"></div>
          <div class="field" style="grid-column:1/-1"><label>内容（Markdown）</label><textarea v-model="popupForm.content_md" class="input" rows="3"></textarea></div>
          <div class="field"><label>延迟秒数</label><input v-model.number="popupForm.delaySec" class="input" type="number" min="0"></div>
          <div class="field"><label>有效期开始 (UTC)（空=立即）</label><input v-model="popupForm.start_at" class="input" type="datetime-local"></div>
          <div class="field"><label>有效期结束 (UTC)（空=长期）</label><input v-model="popupForm.end_at" class="input" type="datetime-local"></div>
        </div>
        <div style="display:flex;gap:18px;flex-wrap:wrap;margin-top:10px;font-size:13.5px">
          <label style="display:flex;gap:8px;align-items:center;cursor:pointer">
            <input v-model="popupForm.exitIntent" type="checkbox" style="width:15px;height:15px"> 鼠标离开页面时触发
          </label>
          <label style="display:flex;gap:8px;align-items:center;cursor:pointer">
            <input v-model="popupForm.mobileOnly" type="checkbox" style="width:15px;height:15px"> 仅移动端展示
          </label>
          <label style="display:flex;gap:8px;align-items:center;cursor:pointer">
            <input v-model.number="popupForm.active" type="checkbox" :true-value="1" :false-value="0" style="width:15px;height:15px"> 立即启用
          </label>
        </div>
        <button class="btn btn-primary btn-block" style="margin-top:14px" @click="savePopup">保存</button>
      </div>
    </div>
  </div>
</template>
