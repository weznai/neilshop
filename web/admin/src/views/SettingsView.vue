<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { req, API_BASE } from '../api/client'
import { useSessionStore } from '../stores/session'
import { toast } from '../composables/toast'
import { dt } from '../composables/format'
import { uploadMedia, uploadErrText } from '../composables/upload'
import { useQuerySync } from '../composables/useQuerySync'
import { ROLE_LABEL, ROLE_BADGE, ROLE_SCOPE_DESC } from '../constants/roles'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'

const TABS = [['shipping', '运费与运营'], ['email', '邮件模板'], ['payments', '支付通道'], ['ai', 'AI 客服'], ['admins', '管理员账号'], ['media', '媒体库'], ['raw', '全部参数']]
/* tab 进 URL（刷新/分享保持当前面板） */
const st = reactive({ tab: 'shipping' })
useQuerySync(st, { defaults: { tab: 'shipping' } })
if (!TABS.some(([k]) => k === st.tab)) st.tab = 'shipping'
const settings = reactive({})   /* key → {value, description} */
const templates = ref([])
const tplErr = ref(false)       /* 邮件模板加载失败：模板区横幅 + 重试（不再静默当空列表） */
const loaded = ref(false)
const settingsErr = ref(false)  /* 配置加载失败：禁用保存，防止默认值覆盖线上配置 */

/* 可编辑运营 key —— 必须与后端消费方一致：
 * pricing.py: free_shipping_threshold / shipping_standard / shipping_express / tax_rate
 * seed: return_days / points_per_dollar_earn（PUT 为 upsert，缺失 key 也能保存生效）
 * bundle_2_off/bundle_3_off 已收敛至「营销工具 · 捆绑折扣」单一数据源，此处不再编辑 */
const EDITABLE = {
  free_shipping_threshold: { label: '满额免邮（分）', type: 'number', def: 3500, min: 0 },
  shipping_standard: { label: '标准运费（分）', type: 'number', def: 499, min: 0 },
  shipping_express: { label: '快递运费（分）', type: 'number', def: 1499, min: 0 },
  tax_rate: { label: '综合税率', type: 'number', step: '0.0001', def: 0.0735, min: 0, max: 1 },
  return_days: { label: '退货窗口（天）', type: 'number', def: 30, min: 1, max: 90 },
  points_per_dollar_earn: { label: '消费 $1 赚积分', type: 'number', def: 10, min: 0 },
}
const drafts = reactive({})   /* key → 编辑值（数字） */
/* 轻量范围校验：超界返回中文提示（保存前拦截） */
function checkRange(key, n) {
  const meta = EDITABLE[key]
  if (!meta) return ''
  if (meta.min != null && n < meta.min) return `「${meta.label}」不能小于 ${meta.min}`
  if (meta.max != null && n > meta.max) return `「${meta.label}」不能大于 ${meta.max}`
  return ''
}

async function load() {
  /* loaded 置位后不再重置：重试/保存后刷新走旧数据模式，不闪骨架 */
  settingsErr.value = false
  try {
    const rows = (await req('GET', '/api/admin/ops/settings')).items || []
    for (const r of rows) {
      settings[r.key] = { value: r.value, description: r.description, updated_by: r.updated_by, updated_at: r.updated_at }
    }
  } catch (e) {
    settingsErr.value = true
    toast('配置加载失败：' + (e.message || ''), 'error')
  }
  for (const [key, meta] of Object.entries(EDITABLE)) {
    drafts[key] = key in settings ? settings[key].value : meta.def
  }
  tplErr.value = false
  try { templates.value = (await req('GET', '/api/admin/ops/email-templates')).items || [] }
  catch (_) { tplErr.value = true }
  loadPayStatus()
  loaded.value = true
}
/* 首载初始化（含直链 tab）：与下方 watch 懒加载合并为单个 onMounted，避免重复请求
 *（原先 onMounted(load) + onMounted(tab 懒加载) 两处各拉一遍） */

/* 模板区重试：单独重拉邮件模板（失败横幅保留） */
async function retryTemplates() {
  tplErr.value = false
  try { templates.value = (await req('GET', '/api/admin/ops/email-templates')).items || [] }
  catch (_) { tplErr.value = true }
}

/* ===== AI 客服大模型配置（settings key=llm_config，覆盖 GM_LLM_* 环境变量） ===== */
const aiCfg = reactive({ api_key_set: false, api_key_masked: '', base_url: '', model: '', timeout: 20, max_tokens: 500, temperature: 0.4, persona: '', prompt_extra: '', embedding_model: '', rag: { ready: false, embedded: 0, total: 0 }, source: '', updated_at: null })
const aiForm = reactive({ api_key: '', base_url: '', model: '', timeout: 20, max_tokens: 500, temperature: 0.4, persona: '', prompt_extra: '', embedding_model: '' })
const aiLoaded = ref(false)
const aiErr = ref(false)
const aiSaving = ref(false)
const aiTesting = ref(false)
const aiTest = reactive({ done: false, ok: false, msg: '' })
const aiPrev = ref(null)          /* 提示词预览 {prompt, default_persona, safety_rules} */
const aiPrevOpen = ref(false)
const aiPrevBusy = ref(false)
const aiReidx = ref(false)
/* RAG 全量重建：danger 确认弹窗（覆盖所有 FAQ 向量） */
const rebuildDlg = ref(false)
/* 用户是否输入了新 Key（空=沿用已保存的，不回传覆盖） */
const aiDirtyKey = computed(() => aiForm.api_key.trim().length > 0)

async function loadAi() {
  aiErr.value = false
  try {
    const d = await req('GET', '/api/admin/ai/config')
    Object.assign(aiCfg, d)
    aiForm.base_url = d.base_url || ''
    aiForm.model = d.model || ''
    aiForm.timeout = d.timeout || 20
    aiForm.max_tokens = d.max_tokens || 500
    aiForm.temperature = d.temperature ?? 0.4
    aiForm.persona = d.persona || ''
    aiForm.prompt_extra = d.prompt_extra || ''
    aiForm.embedding_model = d.embedding_model || ''
    aiForm.api_key = ''
    aiLoaded.value = true
  } catch (e) {
    aiErr.value = true
    toast('AI 配置加载失败：' + (e.message || ''), 'error')
  }
}

/* 保存 AI 配置：成功 true / 失败 false（内部已 toast 具体原因），供预览/测试前判断是否继续 */
async function saveAi() {
  const body = {
    base_url: aiForm.base_url.trim(), model: aiForm.model.trim(),
    timeout: aiForm.timeout | 0, max_tokens: aiForm.max_tokens | 0,
    temperature: aiForm.temperature, persona: aiForm.persona.trim(), prompt_extra: aiForm.prompt_extra.trim(),
    embedding_model: aiForm.embedding_model.trim(),
  }
  if (aiDirtyKey.value) body.api_key = aiForm.api_key.trim()
  if (!body.model) { toast('模型名必填', 'error'); return false }
  aiSaving.value = true
  try {
    await req('PUT', '/api/admin/ai/config', body)
    toast('AI 配置已保存，即时生效 ✓', 'success')
    aiForm.api_key = ''
    aiPrev.value = null /* 配置变了，旧预览失效 */
    await loadAi()
    return true
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error'); return false }
  finally { aiSaving.value = false }
}

async function loadPreview() {
  aiPrevBusy.value = true
  try {
    /* 预览前先保存未保存修改，保证看到的就是将生效的；保存失败即中止（避免预览到未生效配置） */
    if (aiDirtyKey.value || aiForm.model.trim() !== aiCfg.model || aiForm.base_url.trim() !== (aiCfg.base_url || '')
      || aiForm.persona.trim() !== (aiCfg.persona || '') || aiForm.prompt_extra.trim() !== (aiCfg.prompt_extra || '')) {
      if (!(await saveAi())) { toast('请先正确保存 AI 配置', 'error'); return }
    }
    aiPrev.value = await req('GET', '/api/admin/ai/prompt-preview')
    aiPrevOpen.value = true
  } catch (e) { toast('预览失败：' + (e.data?.detail || e.message), 'error') }
  finally { aiPrevBusy.value = false }
}

async function reindexRag(full) {
  if (!aiCfg.api_key_set) { toast('先配置 API Key 并保存，再建索引', 'error'); return }
  aiReidx.value = true
  try {
    /* 全量重建逐条调 embedding 接口，放宽超时至 120s（默认 30s 会中途 abort） */
    const d = await req('POST', '/api/admin/ai/rag/reindex', { full: !!full }, { timeout: 120000 })
    if (d.ok) toast(`索引完成 ✓ 新建 ${d.indexed} 条` + (d.failed ? ` · 失败 ${d.failed} 条` : ''), 'success')
    else toast('索引失败：' + (d.reason || `失败 ${d.failed} 条`), 'error')
    await loadAi()
  } catch (e) { toast('索引失败：' + (e.data?.detail || e.message), 'error') }
  finally { aiReidx.value = false }
}

/* 清除 API Key：danger 确认弹窗（回退规则引擎，服务面变更） */
const clearDlg = ref(false)
async function clearAiKey() {
  clearDlg.value = false
  aiSaving.value = true
  try {
    await req('PUT', '/api/admin/ai/config', { api_key: '' })
    toast('API Key 已清除 ✓', 'success')
    await loadAi()
  } catch (e) { toast('清除失败：' + (e.data?.detail || e.message), 'error') }
  finally { aiSaving.value = false }
}

async function testAi() {
  aiTesting.value = true
  aiTest.done = false
  try {
    /* 先保存未保存的修改再测试（保证测的是生效配置）；保存失败即中止 */
    if (aiDirtyKey.value || aiForm.model.trim() !== aiCfg.model || aiForm.base_url.trim() !== (aiCfg.base_url || '')) {
      if (!(await saveAi())) { toast('请先正确保存 AI 配置', 'error'); return }
    }
    const d = await req('POST', '/api/admin/ai/test')
    aiTest.done = true
    aiTest.ok = !!d.ok
    aiTest.msg = d.ok ? `连通 ✓ ${d.model} · ${d.latency_ms}ms ·「${d.reply}」` : (d.reason || '测试失败')
  } catch (e) { aiTest.done = true; aiTest.ok = false; aiTest.msg = e.data?.detail || e.message || '请求失败' }
  finally { aiTesting.value = false }
}

const saving = ref('')
/* 设置保存 403 detail → 中文（后端 key 白名单校验：只读 key / 未知 key） */
const SETTING_ERR = {
  'readonly setting key': '该配置项不允许在此修改',
  'unknown setting key': '未知配置项',
}
const serr = (e) => SETTING_ERR[e.data?.detail] || e.data?.detail || e.message
async function saveKey(key) {
  if (settingsErr.value) { toast('配置加载失败，已禁用保存（防止默认值覆盖线上配置），请先重试加载', 'error'); return }
  const n = Number(drafts[key])
  if (!Number.isFinite(n) || n < 0) { toast('请输入有效的非负数字', 'error'); return }
  const rangeMsg = checkRange(key, n)
  if (rangeMsg) { toast(rangeMsg + '，已阻止保存', 'error'); return }
  saving.value = key
  try {
    await req('PUT', '/api/admin/ops/settings', { key, value: n })
    settings[key] = { ...settings[key], value: n }   /* 展开保留 updated_by/updated_at 等旧值 */
    toast(`「${EDITABLE[key].label}」已保存 ✓`, 'success')
  } catch (e) { toast('保存失败：' + serr(e), 'error') }
  finally { saving.value = '' }
}

/* 保存全部：顺序 PUT 仅 dirty 的 key，完成后 toast + 静默重载 */
const savingAll = ref(false)
const dirtyKeys = computed(() => Object.keys(EDITABLE).filter((k) => Number(drafts[k]) !== (k in settings ? settings[k].value : EDITABLE[k].def)))
async function saveAll() {
  if (settingsErr.value) { toast('配置加载失败，已禁用保存（防止默认值覆盖线上配置），请先重试加载', 'error'); return }
  const keys = [...dirtyKeys.value]
  if (!keys.length) { toast('没有未保存的修改', 'error'); return }
  for (const k of keys) {
    const n = Number(drafts[k])
    if (!Number.isFinite(n) || n < 0) { toast(`「${EDITABLE[k].label}」需为有效的非负数字`, 'error'); return }
    const rangeMsg = checkRange(k, n)
    if (rangeMsg) { toast(rangeMsg + '，已阻止保存', 'error'); return }
  }
  savingAll.value = true
  let done = 0
  try {
    for (const k of keys) {
      const n = Number(drafts[k])
      await req('PUT', '/api/admin/ops/settings', { key: k, value: n })
      settings[k] = { ...settings[k], value: n }
      done++
    }
    toast(`已保存 ${done} 项修改 ✓`, 'success')
    load()
  } catch (e) {
    toast(`保存中断（${done}/${keys.length} 已保存）：` + serr(e), 'error')
    load()
  } finally { savingAll.value = false }
}

/* ===== 支付通道 · Mock 开关（settings key=mock_pay，优先于 GM_MOCK_PAY 环境变量；后端白名单外仅超管可写） ===== */
const payStatus = ref(null)   /* GET /api/payments/methods 实时生效状态（公开端点，前台同款视角） */
const payBusy = ref(false)
const mockOnDlg = ref(false)
const mockOffDlg = ref(false)
const mockVal = computed(() => ('mock_pay' in settings ? Number(settings.mock_pay.value) : null))
async function loadPayStatus() {
  try { payStatus.value = await req('GET', '/api/payments/methods') }
  catch (_) { payStatus.value = null }
}
async function setMockPay(v) {
  payBusy.value = true
  try {
    await req('PUT', '/api/admin/ops/settings', { key: 'mock_pay', value: v })
    settings.mock_pay = { ...(settings.mock_pay || {}), value: v }
    toast(v ? 'Mock 支付已开启，前台立即可下单 ✓' : 'Mock 支付已关闭 ✓', 'success')
    loadPayStatus()
  } catch (e) { toast('保存失败：' + serr(e), 'error') }
  finally { payBusy.value = false }
}

/* ===== 支付通道配置（settings key=payment_config，覆盖 GM_STRIPE_ 与 GM_PAYPAL_ 环境变量；保存即时生效） ===== */
const payCfg = reactive({
  stripe: { key_set: false, key_masked: '', key_mode: '', webhook_secret_set: false, webhook_secret_masked: '', klarna: false, source: '' },
  paypal: { client_id: '', secret_set: false, secret_masked: '', base: 'https://api-m.sandbox.paypal.com', webhook_id_set: false, webhook_id_masked: '', source: '' },
  package: { stripe: false, httpx: true },
  effective: { provider: 'mock', available: [], mock_pay: true, env: 'dev', webhook_url: '' },
  updated_at: null,
})
const payForm = reactive({ stripe_key: '', stripe_webhook_secret: '', klarna: false, paypal_client_id: '', paypal_secret: '', paypal_base: '', paypal_webhook_id: '' })
const payCfgLoaded = ref(false)
const payCfgErr = ref(false)
const paySaving = ref('')          /* 'stripe' | 'paypal' */
const payTesting = ref('')         /* 'stripe' | 'paypal' */
const payTest = reactive({ stripe: { done: false, ok: false, msg: '' }, paypal: { done: false, ok: false, msg: '' } })
/* 清除密钥确认弹窗（单弹窗多目标）：field=后端字段名 */
const payClearDlg = reactive({ open: false, field: '', title: '', body: '' })
const PP_SANDBOX = 'https://api-m.sandbox.paypal.com'
const PP_LIVE = 'https://api-m.paypal.com'
/* 状态带「默认走 X」文案：无真实凭据时 get_provider 兜底链对象恒为 mock，但开关关闭时
 * mock 不可用——真实语义是「无可用通道」，不能误导为「还在走 Mock」 */
const defaultChainText = computed(() => {
  const p = payCfg.effective.provider
  if (p === 'stripe') return 'Stripe'
  if (p === 'paypal') return 'PayPal'
  return payCfg.effective.mock_pay ? 'Mock（模拟收款）' : '无可用通道（Mock 已关闭，配置真实通道或开启 Mock）'
})

async function loadPayCfg() {
  payCfgErr.value = false
  try {
    const d = await req('GET', '/api/admin/trade/payments/config')
    Object.assign(payCfg, d)
    payForm.stripe_key = ''
    payForm.stripe_webhook_secret = ''
    payForm.klarna = !!d.stripe?.klarna
    payForm.paypal_client_id = d.paypal?.client_id || ''
    payForm.paypal_secret = ''
    payForm.paypal_base = d.paypal?.base || PP_SANDBOX
    payForm.paypal_webhook_id = ''
    payCfgLoaded.value = true
  } catch (e) {
    payCfgErr.value = true
    toast('支付配置加载失败：' + (e.message || ''), 'error')
  }
}

/* 分区 dirty：密钥看「是否输入」，非密钥字段看「是否与已保存值不同」 */
const stripeDirty = computed(() => payForm.stripe_key.trim() !== ''
  || payForm.stripe_webhook_secret.trim() !== ''
  || payForm.klarna !== !!payCfg.stripe.klarna)
const paypalDirty = computed(() => payForm.paypal_secret.trim() !== ''
  || payForm.paypal_webhook_id.trim() !== ''
  || payForm.paypal_client_id.trim() !== (payCfg.paypal.client_id || '')
  || (payForm.paypal_base.trim() || PP_SANDBOX) !== (payCfg.paypal.base || PP_SANDBOX))
const ppMode = computed(() => {
  const b = (payForm.paypal_base || '').trim()
  if (b === PP_SANDBOX) return 'sandbox'
  if (b === PP_LIVE) return 'live'
  return b ? 'custom' : ''
})

const PAY_ERR = {
  'stripe_key 需以 sk_ 开头（sk_test_ / sk_live_）': 'Stripe 密钥需以 sk_ 开头（sk_test_ / sk_live_），请完整复制',
  'stripe_webhook_secret 需以 whsec_ 开头': 'Webhook 签名密钥需以 whsec_ 开头，请完整复制',
  'superadmin required': '仅超管可修改支付配置',
}
const perr = (e) => PAY_ERR[e.data?.detail] || e.data?.detail || e.message

/* 保存单个通道：只回传该通道的 dirty 字段（未输入的密钥不回传 = 沿用已保存值） */
async function savePay(section) {
  if (!isSuper.value) { toast('仅超管可修改支付配置', 'error'); return }
  const body = {}
  if (section === 'stripe') {
    if (payForm.stripe_key.trim()) body.stripe_key = payForm.stripe_key.trim()
    if (payForm.stripe_webhook_secret.trim()) body.stripe_webhook_secret = payForm.stripe_webhook_secret.trim()
    if (payForm.klarna !== !!payCfg.stripe.klarna) body.stripe_klarna = payForm.klarna
  } else {
    if (payForm.paypal_client_id.trim() !== (payCfg.paypal.client_id || '')) body.paypal_client_id = payForm.paypal_client_id.trim()
    if (payForm.paypal_secret.trim()) body.paypal_secret = payForm.paypal_secret.trim()
    if ((payForm.paypal_base.trim() || PP_SANDBOX) !== (payCfg.paypal.base || PP_SANDBOX)) body.paypal_base = payForm.paypal_base.trim()
    if (payForm.paypal_webhook_id.trim()) body.paypal_webhook_id = payForm.paypal_webhook_id.trim()
  }
  if (!Object.keys(body).length) { toast('没有未保存的修改', 'error'); return }
  paySaving.value = section
  try {
    const d = await req('PUT', '/api/admin/trade/payments/config', body)
    Object.assign(payCfg, d)
    payForm.stripe_key = ''; payForm.stripe_webhook_secret = ''
    payForm.paypal_secret = ''; payForm.paypal_webhook_id = ''
    payForm.klarna = !!d.stripe?.klarna
    payForm.paypal_client_id = d.paypal?.client_id || ''
    payForm.paypal_base = d.paypal?.base || PP_SANDBOX
    payTest.stripe.done = false; payTest.paypal.done = false
    toast((section === 'stripe' ? 'Stripe' : 'PayPal') + ' 配置已保存，即时生效 ✓', 'success')
    loadPayStatus()
  } catch (e) { toast('保存失败：' + perr(e), 'error') }
  finally { paySaving.value = '' }
}

/* 清除已存密钥（db 来源才显示清除按钮；清除=回落环境变量配置） */
function openPayClear(field, title, body) {
  payClearDlg.field = field; payClearDlg.title = title; payClearDlg.body = body
  payClearDlg.open = true
}
async function payClearConfirm() {
  if (paySaving.value) return
  paySaving.value = 'clear'
  try {
    const d = await req('PUT', '/api/admin/trade/payments/config', { [payClearDlg.field]: '' })
    Object.assign(payCfg, d)
    payClearDlg.open = false
    payTest.stripe.done = false; payTest.paypal.done = false
    toast('已清除，该字段回落环境变量配置（如有）✓', 'success')
    loadPayStatus()
  } catch (e) { toast('清除失败：' + perr(e), 'error') }
  finally { paySaving.value = '' }
}

/* 连通性测试：用已保存配置真实外呼一次（表单有未保存修改时先提示保存） */
async function testPay(section) {
  if ((section === 'stripe' && stripeDirty.value) || (section === 'paypal' && paypalDirty.value)) {
    toast('有未保存的修改，请先保存再测试（测试使用已生效配置）', 'error'); return
  }
  payTesting.value = section
  payTest[section].done = false
  try {
    const d = await req('POST', '/api/admin/trade/payments/test', { provider: section })
    payTest[section].done = true
    payTest[section].ok = !!d.ok
    if (d.ok) {
      const modeTxt = d.mode === 'test' ? '测试模式' : d.mode === 'sandbox' ? '沙箱' : d.mode === 'live' ? '生产模式' : ''
      const bal = d.provider === 'stripe' && d.balance_cents != null ? ` · 可用余额 $${(d.balance_cents / 100).toFixed(2)}` : ''
      payTest[section].msg = `连通 ✓ ${modeTxt} · ${d.latency_ms}ms${bal}`
    } else {
      payTest[section].msg = d.reason || '测试失败'
    }
  } catch (e) {
    payTest[section].done = true; payTest[section].ok = false
    payTest[section].msg = e.data?.detail || e.message || '请求失败'
  }
  finally { payTesting.value = '' }
}

async function copyWebhookUrl() {
  const u = payCfg.effective?.webhook_url
  if (!u) { toast('未配置站点地址（系统设置 site_url），无法生成回调地址', 'error'); return }
  try { await navigator.clipboard.writeText(u); toast('已复制 ' + u, 'success') }
  catch (_) { toast(u, 'success') }
}

const previewTpl = ref(null)
function showTpl(t) { previewTpl.value = t }
const tplList = () => (Array.isArray(templates.value) ? templates.value : [])

/* 「全部参数」关键字过滤：匹配 key 或说明（不区分大小写） */
const rawFilter = ref('')
const rawRows = computed(() => {
  const k = rawFilter.value.trim().toLowerCase()
  const entries = Object.entries(settings)
  if (!k) return entries
  return entries.filter(([key, v]) => key.toLowerCase().includes(k) || String(v.description || '').toLowerCase().includes(k))
})

/* ===== 管理员账号 tab（写操作仅超管；列表接口 admin:read 可读，仅含启用中账号） ===== */
const session = useSessionStore()
const isSuper = computed(() => session.hasPerm('admin:manage'))
/* 角色文案/徽标配色收敛至 constants/roles.js（1客服 2运营 3仓库 4美甲师 9超管） */
const roleCls = (r) => ROLE_BADGE[r] || 'tag-done'
const admins = ref([])
const adminsLoaded = ref(false)
const adminsErr = ref('')
async function loadAdmins() {
  adminsErr.value = ''
  try { admins.value = (await req('GET', '/api/admin/ops/admins')).items || [] }
  catch (e) {
    adminsErr.value = e.message || ''
    toast('管理员列表加载失败：' + adminsErr.value, 'error')
  }
  adminsLoaded.value = true
}
/* 后端 detail → 中文（403/409/400/404 全收口） */
const ADMIN_ERR = {
  'superadmin required': '仅超管可执行该操作',
  'email exists': '邮箱已被占用',
  'cannot modify self': '不能修改自己的角色或停用自己',
  'admin not found': '账号不存在',
}
const aerr = (e) => ADMIN_ERR[e.data?.detail] || e.data?.detail || e.message

/* 新建表单：email/name/密码≥8/角色 1|2|3|9（权限口径见 ROLE_SCOPE_DESC） */
const adminForm = reactive({ email: '', name: '', password: '', role: '2' })
const creating = ref(false)
async function createAdmin() {
  if (creating.value) return
  const email = adminForm.email.trim().toLowerCase()
  const name = adminForm.name.trim()
  if (!email.includes('@')) { toast('请输入有效的邮箱地址', 'error'); return }
  if (!name) { toast('请填写姓名', 'error'); return }
  if (adminForm.password.length < 8) { toast('密码至少 8 位', 'error'); return }
  if (!['1', '2', '3', '9'].includes(adminForm.role)) { toast('请选择角色', 'error'); return }
  creating.value = true
  try {
    const r = await req('POST', '/api/admin/ops/admins', { email, name, password: adminForm.password, role: Number(adminForm.role) })
    toast(`管理员 ${r.name}（${ROLE_LABEL[r.role] || r.role}）已创建 ✓`, 'success')
    Object.assign(adminForm, { email: '', name: '', password: '', role: '2' })
    loadAdmins()
  } catch (e) { toast('创建失败：' + aerr(e), 'error') }
  finally { creating.value = false }
}

/* 行内编辑：name/role（自己行禁改角色，后端 400 兜底）；保存 PUT 增量字段 */
const editId = ref(0)
const editDraft = reactive({ name: '', role: '2' })
function openEditAdmin(a) { editId.value = a.id; editDraft.name = a.name || ''; editDraft.role = String(a.role) }
function cancelEditAdmin() { editId.value = 0 }
const savingAdmin = ref(0)   /* 正在保存/停用的行 id */
async function saveAdmin(a) {
  if (savingAdmin.value) return
  const name = editDraft.name.trim()
  if (!name) { toast('姓名不能为空', 'error'); return }
  const body = { name }
  if (String(a.role) !== editDraft.role) body.role = Number(editDraft.role)
  savingAdmin.value = a.id
  try {
    const r = await req('PUT', '/api/admin/ops/admins/' + a.id, body)
    admins.value = admins.value.map((x) => (x.id === a.id ? { ...x, ...r } : x))
    toast('已保存 ✓', 'success')
    editId.value = 0
  } catch (e) { toast('保存失败：' + aerr(e), 'error') }
  finally { savingAdmin.value = 0 }
}

/* 停用：danger 确认 → PUT status=0（列表仅含启用账号，停用后即从列表消失） */
const offDlg = ref(false)
const offTarget = ref(null)
function openOffAdmin(a) { offTarget.value = a; offDlg.value = true }
async function offAdminConfirm() {
  if (savingAdmin.value || !offTarget.value) return
  savingAdmin.value = offTarget.value.id
  try {
    await req('PUT', '/api/admin/ops/admins/' + offTarget.value.id, { status: 0 })
    toast(`已停用 ${offTarget.value.name}（该账号将无法登录后台）`, 'success')
    offDlg.value = false
    loadAdmins()
  } catch (e) { toast('停用失败：' + aerr(e), 'error') }
  finally { savingAdmin.value = 0 }
}

/* ===== 媒体库 tab：q 搜索 + 分页 + 缩略图表格 + 上传/删除 ===== */
const media = ref([])
const mTotal = ref(0)
const mPages = ref(1)
const mPage = ref(1)
const MSIZE = 24
const mLoaded = ref(false)
const mErr = ref('')
const mQ = ref('')
async function loadMedia(p = 1) {
  mErr.value = ''
  try {
    const params = new URLSearchParams({ page: p, size: MSIZE })
    const s = mQ.value.trim()
    if (s) params.set('q', s)
    const r = await req('GET', '/api/admin/media?' + params)
    media.value = r.items || []
    mTotal.value = r.total ?? 0
    mPages.value = Math.max(1, r.pages ?? 1)
    mPage.value = r.page || p
  } catch (e) {
    mErr.value = e.message || ''
    toast('媒体库加载失败：' + mErr.value, 'error')
  }
  mLoaded.value = true
}
function searchMedia() { loadMedia(1) }
/* 字节格式化：B/KB/MB */
function fmtBytes(n) {
  if (n == null) return '—'
  if (n < 1024) return n + ' B'
  if (n < 1048576) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1048576).toFixed(2) + ' MB'
}
/* 缩略图地址：url 为 /static/uploads/... 相对路径，拆 API 域时补前缀 */
const mediaSrc = (m) => (API_BASE || '') + m.url

/* 删除：danger 确认（被引用 409 不可删）；name 可能含 /，需 encodeURIComponent */
const delMDlg = ref(false)
const delMTarget = ref(null)
const delMBusy = ref(false)
function openDelMedia(m) { delMTarget.value = m; delMDlg.value = true }
async function delMediaConfirm() {
  if (delMBusy.value || !delMTarget.value) return
  delMBusy.value = true
  try {
    await req('DELETE', '/api/admin/media/' + encodeURIComponent(delMTarget.value.name))
    toast(`已删除 ${delMTarget.value.name}`, 'success')
    delMDlg.value = false
    /* 当前页删空后回退一页，避免停留在空页 */
    const last = media.value.length === 1 && mPage.value > 1
    loadMedia(last ? mPage.value - 1 : mPage.value)
  } catch (e) {
    const detail = e.data?.detail
    toast('删除失败：' + (detail === 'media in use' ? '文件正被商品引用，不可删除' : detail === 'invalid filename' ? '非法文件名' : detail === 'file not found' ? '文件不存在' : (detail || e.message)), 'error')
  }
  finally { delMBusy.value = false }
}

/* 上传：POST /api/admin/media/upload（统一走 composables/upload，401/403 全局兜底） */
const fileInput = ref(null)
const uploading = ref(false)
function pickFile() { if (!uploading.value) fileInput.value?.click() }
async function onPickFile(e) {
  const f = e.target.files && e.target.files[0]
  e.target.value = ''   /* 复位 value，否则重选同一文件不触发 change */
  if (!f) return
  uploading.value = true
  try {
    await uploadMedia(f)
    toast('上传成功 ✓（新文件排在最前）', 'success')
    loadMedia(1)
  } catch (err) {
    const m = uploadErrText(err)
    if (m) toast(m, 'error')
  }
  finally { uploading.value = false }
}

/* 新 tab 懒加载：首次切入才拉取（直链进入由下方合并的 onMounted 覆盖） */
watch(() => st.tab, (k) => {
  if (k === 'admins' && !adminsLoaded.value) loadAdmins()
  if (k === 'media' && !mLoaded.value) loadMedia(mPage.value)
  if (k === 'ai' && !aiLoaded.value) loadAi()
  if (k === 'payments' && !payCfgLoaded.value) loadPayCfg()
})
/* 唯一 onMounted：基础配置 + 直链 tab 懒加载（顺序同原两个钩子的注册执行顺序） */
onMounted(() => {
  load()
  if (st.tab === 'admins') loadAdmins()
  if (st.tab === 'media') loadMedia(mPage.value)
  if (st.tab === 'ai' && !aiLoaded.value) loadAi()
  if (st.tab === 'payments' && !payCfgLoaded.value) loadPayCfg()
})
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">系统设置</h1>
      <span class="page-sub">运费 / 税率 / 邮件模板 / 支付通道 / 管理员 / 媒体库</span>
    </div>
  </div>

  <div class="otab">
    <button
      v-for="[k, label] in TABS"
      :key="k"
      :class="{ on: st.tab === k }"
      style="background:none;border:none;cursor:pointer"
      @click="st.tab = k"
    >{{ label }}</button>
  </div>

  <!-- 运费与运营（常用 key 表单化；保存即 upsert，未初始化的 key 用默认值占位） -->
  <div v-if="st.tab === 'shipping'" class="card" style="padding:20px">
    <div class="dhead">
      <div class="dtitle">运营参数</div>
      <button class="btn btn-primary btn-sm" :class="{ loading: savingAll }" :disabled="savingAll || settingsErr" @click="saveAll">
        保存全部修改{{ dirtyKeys.length ? '（' + dirtyKeys.length + '）' : '' }}
      </button>
    </div>
    <div v-if="settingsErr" style="display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 14px;margin-bottom:16px;background:var(--pale-error);border:1px solid var(--error);border-radius:10px;font-size:12.5px;color:var(--error)">
      <span>⚠️ 配置加载失败，保存已禁用——防止默认值覆盖线上配置</span>
      <button class="btn btn-secondary btn-sm" @click="load">重试加载</button>
    </div>
    <div class="set-grid">
      <template v-for="(meta, key) in EDITABLE" :key="key">
        <div class="field">
          <label>{{ meta.label }} <small style="color:var(--gray)">（{{ key }}）</small>
            <span v-if="!settingsErr && !(key in settings)" class="tag tag-pending" style="margin-left:4px;font-size:10px">未设置·存默认</span>
          </label>
          <div style="display:flex;gap:8px">
            <input v-model.number="drafts[key]" class="input" :type="meta.type" :step="meta.step || 1" style="width:180px" :disabled="settingsErr">
            <button class="btn btn-secondary btn-sm" :class="{ loading: saving === key }" :disabled="saving === key || settingsErr" @click="saveKey(key)">保存</button>
          </div>
          <p v-if="settings[key]?.description" style="font-size:11.5px;color:var(--gray)">{{ settings[key].description }}</p>
        </div>
      </template>
    </div>
    <p style="font-size:12.5px;color:var(--gray);margin-top:12px">
      捆绑折扣参数已移至 <router-link :to="{ path: '/marketing', query: { tab: 'bundles' } }" style="color:var(--plum)">营销工具 · 捆绑折扣</router-link> 统一管理；
      支付通道（Stripe / PayPal / Mock）已移至本页 <a style="color:var(--plum);cursor:pointer" @click="st.tab = 'payments'">「支付通道」</a> 标签
    </p>
    <div v-if="loaded && !settingsErr && !Object.keys(settings).length" style="color:var(--gray);font-size:13px;margin-top:6px">
      服务端暂无预置参数，上方表单保存后将写入并即时生效。
    </div>
  </div>

  <!-- 邮件模板 -->
  <div v-else-if="st.tab === 'email'" class="card" style="padding:0">
    <!-- 加载失败：错误横幅 + 重试（对齐 settingsErr 横幅模式），旧数据（若有）保留 -->
    <div v-if="tplErr" style="display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 14px;margin:12px;background:var(--pale-error);border:1px solid var(--error);border-radius:10px;font-size:12.5px;color:var(--error)">
      <span>⚠️ 邮件模板加载失败，展示的可能不是最新列表</span>
      <button class="btn btn-secondary btn-sm" @click="retryTemplates">重试</button>
    </div>
    <div v-for="t in tplList()" :key="t.name" class="setrow" style="padding:14px 18px;border-bottom:1px solid var(--gray-light)">
      <div><b>{{ t.name }}</b><div style="font-size:12px;color:var(--gray)">主题：{{ t.subject }}</div></div>
      <button class="btn btn-secondary btn-sm" @click="showTpl(t)">👁 预览</button>
    </div>
    <EmptyState v-if="loaded && !tplErr && !tplList().length" icon="✉️" title="暂无邮件模板" sub="服务端未内置模板时此处为空" />
  </div>

  <!-- 支付通道：摘要条 + Stripe/PayPal 双通道卡 + Mock 条 + 机制说明（payment_config 后台可配，热生效） -->
  <div v-else-if="st.tab === 'payments'">
    <div v-if="payCfgErr" class="card" style="display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 16px;margin-bottom:16px;background:var(--pale-error);border:1px solid var(--error);border-radius:12px;font-size:12.5px;color:var(--error)">
      <span>⚠️ 支付配置加载失败</span>
      <button class="btn btn-secondary btn-sm" @click="loadPayCfg">重试</button>
    </div>
    <div v-if="!payCfgLoaded && !payCfgErr" class="card skeleton" style="min-height:320px" />
    <template v-else>
      <!-- 摘要条：默认链 + 前台可用 + 回调地址（一览全局，配色随通道状态） -->
      <div class="card pay-hero" :class="{ ok: payCfg.effective.provider !== 'mock' && payCfg.effective.available.length }">
        <div class="pay-hero-ico" :class="{ on: payCfg.effective.provider !== 'mock' && payCfg.effective.available.length }">💳</div>
        <div class="pay-hero-main">
          <div class="pay-hero-title">
            默认走 <b>{{ defaultChainText }}</b>
            <span v-if="payCfg.effective.env !== 'prod'" class="pay-hero-env">{{ payCfg.effective.env }}</span>
          </div>
          <div class="pay-hero-sub">
            前台可用：
            <template v-if="payCfg.effective.available.length">
              <span v-for="p in payCfg.effective.available" :key="p" class="pay-chip">{{ p === 'stripe(klarna)' ? 'Stripe + Klarna' : p === 'stripe' ? 'Stripe' : p === 'paypal' ? 'PayPal' : 'Mock' }}</span>
            </template>
            <span v-else class="pay-chip warn">无（前台结算按钮置灰）</span>
          </div>
        </div>
        <div class="pay-hero-side">
          <button class="btn btn-ghost btn-sm" @click="loadPayCfg">↻ 刷新</button>
          <button v-if="payCfg.effective.webhook_url" class="pay-hook" title="复制 Webhook 回调地址" @click="copyWebhookUrl">
            <code>{{ payCfg.effective.webhook_url }}</code>
          </button>
        </div>
      </div>

      <!-- 双通道卡（宽屏并排 / 窄屏堆叠） -->
      <div class="pay-cards">
        <!-- ===== Stripe ===== -->
        <section class="pay-card">
          <header class="pay-card-head">
            <span class="pay-brand-tile" style="background:linear-gradient(135deg,#7A73FF,#635BFF)">S</span>
            <div class="pay-card-head-txt">
              <div class="pay-card-name">Stripe <span class="pay-card-sub">信用卡 / 借记卡{{ payCfg.stripe.klarna ? ' / Klarna' : '' }}</span></div>
              <div class="pay-card-meta">
                密钥 <code v-if="payCfg.stripe.key_set">{{ payCfg.stripe.key_masked }}</code><code v-else>未配置</code>
                <template v-if="payCfg.stripe.source"> · {{ payCfg.stripe.source === 'db' ? '后台配置' : '环境变量' }}<template v-if="payCfg.updated_at && payCfg.stripe.source === 'db'"> · {{ dt(payCfg.updated_at) }}</template></template>
              </div>
            </div>
            <span v-if="payCfg.stripe.key_set && payCfg.stripe.key_mode === 'live'" class="tag tag-paid">live</span>
            <span v-else-if="payCfg.stripe.key_set" class="tag tag-ship">test</span>
            <span v-else class="tag tag-pending">未配置</span>
          </header>

          <!-- 缺包降级提示：有密钥但容器未装 stripe 包时仍为 mock -->
          <div v-if="payCfg.stripe.key_set && !payCfg.package.stripe" class="pay-warn">
            ⚠️ 已配置密钥，但服务端未安装 <code>stripe</code> 包——当前实际降级为 Mock。容器内 <code>pip install stripe</code> 后重启即切换。
          </div>

          <div class="pay-card-body">
            <div class="field" style="margin:0">
              <label>API 密钥 <span v-if="payCfg.stripe.key_set" class="pay-hint">（留空 = 沿用已保存密钥）</span></label>
              <div style="display:flex;gap:8px">
                <input v-model="payForm.stripe_key" class="input" type="password" style="flex:1;min-width:0" :disabled="!isSuper" :placeholder="payCfg.stripe.key_set ? payCfg.stripe.key_masked : 'sk_test_… 或 sk_live_…'" autocomplete="new-password">
                <button v-if="isSuper && payCfg.stripe.source === 'db' && payCfg.stripe.key_set" class="btn btn-ghost btn-sm" style="color:var(--error);flex:none" @click="openPayClear('stripe_key', '清除 Stripe 密钥', '确认清除后台保存的 Stripe 密钥？清除后回落环境变量 GM_STRIPE_KEY（如有），前台通道可能变化。')">清除</button>
              </div>
              <p class="pay-note">Stripe 后台 Developers → API keys 复制 Secret key（sk_ 开头）</p>
            </div>
            <div class="field" style="margin:0">
              <label>Webhook 签名密钥 <span v-if="payCfg.stripe.webhook_secret_set" class="pay-hint">（已存 {{ payCfg.stripe.webhook_secret_masked }}）</span></label>
              <div style="display:flex;gap:8px">
                <input v-model="payForm.stripe_webhook_secret" class="input" type="password" style="flex:1;min-width:0" :disabled="!isSuper" :placeholder="payCfg.stripe.webhook_secret_set ? 'whsec_***（留空沿用）' : 'whsec_…'" autocomplete="new-password">
                <button v-if="isSuper && payCfg.stripe.webhook_secret_set && payCfg.stripe.source === 'db'" class="btn btn-ghost btn-sm" style="color:var(--error);flex:none" @click="openPayClear('stripe_webhook_secret', '清除 Webhook 签名密钥', '确认清除？非 dev 环境下未配置验签密钥时 webhook 回调将被拒绝。')">清除</button>
              </div>
              <p class="pay-note">Developers → Webhooks 端点 Signing secret（whsec_ 开头）</p>
            </div>
            <label class="pay-switch-row">
              <span class="pay-switch" :class="{ on: payForm.klarna }" role="switch" :aria-checked="payForm.klarna" tabindex="0" @click="isSuper && (payForm.klarna = !payForm.klarna)" @keydown.enter.prevent="isSuper && (payForm.klarna = !payForm.klarna)"><i /></span>
              <span>启用 Klarna<span class="pay-hint"> —— 先买后付（US/UK/DE 等，需 Stripe 账户已开通）</span></span>
            </label>
          </div>

          <footer class="pay-card-foot">
            <button v-if="isSuper" class="btn btn-primary" :class="{ loading: paySaving === 'stripe' }" :disabled="paySaving !== ''" @click="savePay('stripe')">保存{{ stripeDirty ? ' *' : '' }}</button>
            <button class="btn btn-secondary" :class="{ loading: payTesting === 'stripe' }" :disabled="payTesting !== ''" title="用已保存密钥真实调用一次 Stripe API，验证密钥可用性" @click="testPay('stripe')">⚡ 测试连接</button>
            <span v-if="!isSuper" class="pay-hint">🔒 仅超管可修改，此处只读</span>
            <div v-if="payTest.stripe.done" class="pay-test" :class="payTest.stripe.ok ? 'ok' : 'err'">
              <span>{{ payTest.stripe.ok ? '✅' : '⚠️' }}</span><span style="flex:1">{{ payTest.stripe.msg }}</span>
            </div>
          </footer>
        </section>

        <!-- ===== PayPal ===== -->
        <section class="pay-card">
          <header class="pay-card-head">
            <span class="pay-brand-tile" style="background:linear-gradient(135deg,#1D8FE0,#0070BA)">P</span>
            <div class="pay-card-head-txt">
              <div class="pay-card-name">PayPal <span class="pay-card-sub">PayPal 余额 / 绑卡</span></div>
              <div class="pay-card-meta">
                Client ID <code v-if="payCfg.paypal.client_id">{{ payCfg.paypal.client_id.slice(0, 10) }}…</code><code v-else>未配置</code>
                <template v-if="payCfg.paypal.source"> · {{ payCfg.paypal.source === 'db' ? '后台配置' : '环境变量' }}</template>
              </div>
            </div>
            <span v-if="payCfg.paypal.client_id && payCfg.paypal.secret_set && ppMode === 'live'" class="tag tag-paid">live</span>
            <span v-else-if="payCfg.paypal.client_id && payCfg.paypal.secret_set" class="tag tag-ship">sandbox</span>
            <span v-else class="tag tag-pending">未配置</span>
          </header>

          <div v-if="(payCfg.paypal.client_id || payCfg.paypal.secret_set) && !payCfg.package.httpx" class="pay-warn">
            ⚠️ 已配置凭据，但服务端缺 <code>httpx</code> 包——PayPal 通道不可用（默认镜像已含，如缺失请检查依赖）。
          </div>

          <div class="pay-card-body">
            <div class="field" style="margin:0">
              <label>Client ID</label>
              <input v-model="payForm.paypal_client_id" class="input" :disabled="!isSuper" placeholder="PayPal Developer 应用的 Client ID">
            </div>
            <div class="field" style="margin:0">
              <label>Secret <span v-if="payCfg.paypal.secret_set" class="pay-hint">（留空 = 沿用已保存）</span></label>
              <div style="display:flex;gap:8px">
                <input v-model="payForm.paypal_secret" class="input" type="password" style="flex:1;min-width:0" :disabled="!isSuper" :placeholder="payCfg.paypal.secret_set ? payCfg.paypal.secret_masked : '应用 Secret'" autocomplete="new-password">
                <button v-if="isSuper && payCfg.paypal.source === 'db' && payCfg.paypal.secret_set" class="btn btn-ghost btn-sm" style="color:var(--error);flex:none" @click="openPayClear('paypal_secret', '清除 PayPal Secret', '确认清除后台保存的 PayPal Secret？清除后回落环境变量 GM_PAYPAL_SECRET（如有）。')">清除</button>
              </div>
            </div>
            <div class="field" style="margin:0">
              <label>API 环境 <span class="pay-hint">—— 先沙箱联调，切生产改这里</span></label>
              <div class="pay-seg">
                <button type="button" :class="{ on: ppMode === 'sandbox' }" :disabled="!isSuper" @click="payForm.paypal_base = PP_SANDBOX">🧪 沙箱</button>
                <button type="button" :class="{ on: ppMode === 'live' }" :disabled="!isSuper" @click="payForm.paypal_base = PP_LIVE">🚀 生产</button>
              </div>
              <p class="pay-note">基址 <code>{{ payForm.paypal_base || PP_SANDBOX }}</code>{{ ppMode === 'custom' ? '（自定义）' : '' }}</p>
            </div>
            <div class="field" style="margin:0">
              <label>Webhook ID <span class="pay-hint">（可选，非 dev 环境必配）</span></label>
              <div style="display:flex;gap:8px">
                <input v-model="payForm.paypal_webhook_id" class="input" type="password" style="flex:1;min-width:0" :disabled="!isSuper" :placeholder="payCfg.paypal.webhook_id_set ? payCfg.paypal.webhook_id_masked + '（留空沿用）' : '1XY…（Webhook 详情页 ID）'" autocomplete="new-password">
                <button v-if="isSuper && payCfg.paypal.webhook_id_set && payCfg.paypal.source === 'db'" class="btn btn-ghost btn-sm" style="color:var(--error);flex:none" @click="openPayClear('paypal_webhook_id', '清除 PayPal Webhook ID', '确认清除？非 dev 环境下未配置 Webhook ID 时回调将被拒绝。')">清除</button>
              </div>
            </div>
          </div>

          <footer class="pay-card-foot">
            <button v-if="isSuper" class="btn btn-primary" :class="{ loading: paySaving === 'paypal' }" :disabled="paySaving !== ''" @click="savePay('paypal')">保存{{ paypalDirty ? ' *' : '' }}</button>
            <button class="btn btn-secondary" :class="{ loading: payTesting === 'paypal' }" :disabled="payTesting !== ''" title="用已保存凭据真实获取一次 OAuth token，验证凭据可用性" @click="testPay('paypal')">⚡ 测试连接</button>
            <span v-if="!isSuper" class="pay-hint">🔒 仅超管可修改，此处只读</span>
            <div v-if="payTest.paypal.done" class="pay-test" :class="payTest.paypal.ok ? 'ok' : 'err'">
              <span>{{ payTest.paypal.ok ? '✅' : '⚠️' }}</span><span style="flex:1">{{ payTest.paypal.msg }}</span>
            </div>
          </footer>
        </section>
      </div>

      <!-- ===== Mock 模拟收款（联调用；settings key=mock_pay，优先于 GM_MOCK_PAY）紧凑条 -->
      <div class="card pay-mock">
        <span class="pay-brand-tile" style="background:linear-gradient(135deg,#B8B2B7,#9B949A)">M</span>
        <div style="flex:1;min-width:0">
          <div class="pay-card-name">Mock 模拟收款 <span class="pay-card-sub">联调 / 试运营</span></div>
          <div class="pay-card-meta">下单即视为支付成功，不发生真实资金——接入真实通道后请保持关闭</div>
        </div>
        <span class="tag" :class="mockVal === 1 ? 'tag-paid' : mockVal === 0 ? 'tag-done' : 'tag-pending'">
          {{ mockVal === 1 ? '已开启' : mockVal === 0 ? '已关闭' : '未设置 · 跟随环境' }}
        </span>
        <div class="pay-mock-ops">
          <template v-if="isSuper">
            <button v-if="mockVal !== 1" class="btn btn-primary btn-sm" :class="{ loading: payBusy }" :disabled="payBusy" @click="mockOnDlg = true">开启</button>
            <button v-else class="btn btn-secondary btn-sm" :class="{ loading: payBusy }" :disabled="payBusy" @click="mockOffDlg = true">关闭</button>
          </template>
          <span v-else class="pay-hint">🔒 仅超管可改</span>
        </div>
      </div>

      <!-- 机制说明（2 列小卡） -->
      <div class="pay-foot-card">
        <div class="pay-foot-item pay-foot-hook">
          <b>Webhook 回调</b>
          <span style="flex:1;min-width:0;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <code style="background:var(--gray-light);border-radius:5px;padding:2px 7px;font-size:11.5px;word-break:break-all">{{ payCfg.effective.webhook_url || '未配置站点地址（site_url），无法生成' }}</code>
            <button v-if="payCfg.effective.webhook_url" class="btn btn-secondary btn-sm" @click="copyWebhookUrl">复制</button>
          </span>
        </div>
        <div class="pay-foot-item"><b>优先级</b><span>本页配置 &gt; 环境变量（GM_STRIPE_* / GM_PAYPAL_*），保存即时生效；清除字段 = 回落环境变量</span></div>
        <div class="pay-foot-item"><b>选择链</b><span>Stripe &gt; PayPal &gt; Mock 逐级降级；Stripe 需 stripe 包，Klarna 需账户开通相应地区</span></div>
        <div class="pay-foot-item"><b>验签门禁</b><span>非 dev 环境必须配 Webhook 签名密钥（whsec_… / Webhook ID），否则回调一律 400</span></div>
        <div class="pay-foot-item"><b>安全</b><span>密钥仅存服务端，界面掩码；修改/清除记管理日志；写操作仅超管</span></div>
      </div>
    </template>
  </div>

  <!-- AI 客服大模型配置：状态带 + 分区表单（接入/风格/RAG）+ 操作区 + 说明区 -->
  <div v-else-if="st.tab === 'ai'" class="card" style="padding:0">
    <div v-if="aiErr" style="display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 14px;margin:12px;background:var(--pale-error);border:1px solid var(--error);border-radius:10px;font-size:12.5px;color:var(--error)">
      <span>⚠️ AI 配置加载失败</span>
      <button class="btn btn-secondary btn-sm" @click="loadAi">重试</button>
    </div>
    <div v-if="!aiLoaded && !aiErr" class="skeleton" style="min-height:200px" />
    <template v-else>
      <!-- 状态带 -->
      <div class="ai-status">
        <div class="ai-status-ico" :class="{ on: aiCfg.api_key_set }">🤖</div>
        <div style="flex:1;min-width:0">
          <b style="font-size:14px">AI 客服 · GlowBot</b>
          <div class="ai-status-sub">
            <template v-if="aiCfg.api_key_set">
              大模型已启用 · Key <code>{{ aiCfg.api_key_masked }}</code> · 来源 {{ aiCfg.source === 'db' ? '后台配置' : '环境变量' }}<template v-if="aiCfg.updated_at && aiCfg.source === 'db'"> · 更新于 {{ dt(aiCfg.updated_at) }}</template>
            </template>
            <template v-else>未配置大模型 —— AI 客服走<b>内置规则引擎</b>（订单查询 / FAQ 检索不受影响），配置后自动升级为大模型回复</template>
          </div>
        </div>
        <span class="tag" :class="aiCfg.api_key_set ? 'tag-paid' : 'tag-pending'">{{ aiCfg.api_key_set ? '已启用' : '规则引擎' }}</span>
      </div>

      <!-- 接入配置 -->
      <section class="ai-sec">
        <div class="ai-sec-head">
          <div class="dtitle">接入配置</div>
          <span class="ai-hint">OpenAI 兼容接口 · 保存即时生效</span>
        </div>
        <div class="ai-grid">
          <div class="field s12" style="margin:0">
            <label>API Key <span v-if="aiCfg.api_key_set" class="ai-hint">（留空 = 沿用已保存的 Key）</span></label>
            <div style="display:flex;gap:8px">
              <input v-model="aiForm.api_key" class="input" type="password" style="flex:1" :placeholder="aiCfg.api_key_set ? aiCfg.api_key_masked : 'sk-…（OpenAI 兼容网关的密钥）'" autocomplete="new-password">
              <button v-if="aiCfg.source === 'db' && aiCfg.api_key_set" class="btn btn-ghost btn-sm" style="color:var(--error);flex:none" :disabled="aiSaving" @click="clearDlg = true">清除</button>
            </div>
            <p class="ai-note">密钥仅存服务端，界面以掩码显示</p>
          </div>
          <div class="field s12" style="margin:0">
            <label>接口地址 Base URL</label>
            <input v-model="aiForm.base_url" class="input" placeholder="https://api.openai.com/v1">
            <p class="ai-note">默认官方 https://api.openai.com/v1，国内网关填对应地址</p>
          </div>
          <div class="field s6" style="margin:0">
            <label>模型名</label>
            <input v-model="aiForm.model" class="input" placeholder="gpt-4o-mini">
          </div>
          <div class="field s3" style="margin:0">
            <label>超时（秒）</label>
            <input v-model.number="aiForm.timeout" class="input" type="number" min="3" max="60">
            <p class="ai-note">3 - 60</p>
          </div>
          <div class="field s3" style="margin:0">
            <label>回复上限（tokens）</label>
            <input v-model.number="aiForm.max_tokens" class="input" type="number" min="50" max="2000">
            <p class="ai-note">50 - 2000</p>
          </div>
        </div>
      </section>

      <!-- 对话风格 -->
      <section class="ai-sec">
        <div class="ai-sec-head">
          <div class="dtitle">对话风格</div>
          <span class="ai-hint">最终提示词可点下方「提示词预览」核对</span>
        </div>
        <div class="ai-grid">
          <div class="field s8" style="margin:0">
            <label>人设 Persona</label>
            <textarea v-model="aiForm.persona" class="input" rows="3" placeholder="You are GlowBot, the friendly AI assistant of GLOWMAG…（身份 / 语气 / 称呼）"></textarea>
            <p class="ai-note">留空 = 默认 GlowBot · ≤500 字符</p>
          </div>
          <div class="field s4" style="margin:0">
            <label>创造性 Temperature</label>
            <input v-model.number="aiForm.temperature" class="input" type="number" min="0" max="2" step="0.1">
            <p class="ai-note">0 严谨 · 0.4 均衡 · 1+ 活泼</p>
          </div>
          <div class="field s12" style="margin:0">
            <label>补充指令</label>
            <textarea v-model="aiForm.prompt_extra" class="input" rows="3" placeholder="例如：本月大促期间主动提及「满 $35 免邮」；周末回复结尾加一句周末快乐 💅"></textarea>
            <p class="ai-note">追加在安全规则之后，适合活动话术 / 临时规则 · ≤2000 字符</p>
          </div>
        </div>
      </section>

      <!-- FAQ 知识库（RAG） -->
      <section class="ai-sec">
        <div class="ai-sec-head">
          <div class="dtitle">FAQ 知识库 · RAG</div>
          <span class="tag" :class="aiCfg.rag?.ready ? 'tag-paid' : 'tag-pending'">{{ aiCfg.rag?.ready ? '已就绪' : '未启用' }}</span>
        </div>
        <p class="ai-note" style="margin:0 0 12px">
          问答仅注入与客户问题最相关的 top-5 片段 · 已索引 <b style="color:var(--ink)">{{ aiCfg.rag?.embedded || 0 }} / {{ aiCfg.rag?.total || 0 }}</b> 条
          <template v-if="!aiCfg.rag?.ready"> · {{ aiCfg.api_key_set ? '覆盖率不足或未建索引' : '未配置 API Key' }}，当前为全量注入模式</template>
        </p>
        <div class="ai-rag-row">
          <div class="field" style="margin:0;flex:1;min-width:220px">
            <label>向量模型</label>
            <input v-model="aiForm.embedding_model" class="input" placeholder="text-embedding-3-small">
          </div>
          <button class="btn btn-secondary" :class="{ loading: aiReidx }" :disabled="aiReidx || aiSaving" title="为未索引的 FAQ 生成向量（保存配置后使用）" @click="reindexRag(false)">📥 补建索引</button>
          <button class="btn btn-ghost" style="color:var(--error)" :class="{ loading: aiReidx }" :disabled="aiReidx || aiSaving" title="全部重建（更换向量模型后使用）" @click="rebuildDlg = true">♻️ 全量重建</button>
        </div>
      </section>

      <!-- 保存与验证 -->
      <section class="ai-sec ai-sec-foot">
        <div class="ai-btn-row">
          <button class="btn btn-primary" :class="{ loading: aiSaving }" :disabled="aiSaving || aiTesting" @click="saveAi">保存配置</button>
          <button class="btn btn-secondary" :class="{ loading: aiPrevBusy }" :disabled="aiSaving || aiPrevBusy" title="查看实际下发的大模型系统提示词（含 FAQ 知识库注入结果）" @click="loadPreview">📄 提示词预览</button>
          <button class="btn btn-secondary" :class="{ loading: aiTesting }" :disabled="aiSaving || aiTesting" title="用当前配置发一条测试消息，验证 Key / 网关 / 模型是否可用" @click="testAi">⚡ 测试连接</button>
        </div>
        <div v-if="aiTest.done" class="ai-test" :class="aiTest.ok ? 'ok' : 'err'">
          <span>{{ aiTest.ok ? '✅' : '⚠️' }}</span>
          <span style="flex:1">{{ aiTest.msg }}</span>
        </div>
        <div v-if="aiPrevOpen && aiPrev" class="ai-prev">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <b style="font-size:12.5px">最终系统提示词（实际下发 · {{ aiPrev.prompt.length }} 字符）</b>
            <button class="btn btn-ghost btn-sm" @click="aiPrevOpen = false">收起</button>
          </div>
          <pre style="margin:0;white-space:pre-wrap;word-break:break-word;font-size:11.5px;line-height:1.7;color:var(--ink)">{{ aiPrev.prompt }}</pre>
        </div>
      </section>

      <!-- 机制说明 -->
      <section class="ai-sec ai-sec-foot ai-foot">
        <div class="ai-foot-row"><b>优先级</b><span>后台配置优先于服务器环境变量（GM_LLM_*），保存即时生效，无需重启</span></div>
        <div class="ai-foot-row"><b>提示词</b><span>人设（可配）+ 安全红线（固定不可配）+ 补充指令（可配）+ 运营政策 / FAQ 知识库（自动注入）</span></div>
        <div class="ai-foot-row"><b>知识边界</b><span>AI 问答以「内容管理 → FAQ」为知识库；订单 / 物流等数据类问题始终走规则引擎查库，大模型不接触订单数据</span></div>
        <div class="ai-foot-row"><b>兜底</b><span>配置异常时自动回退规则引擎，前台客服不中断</span></div>
      </section>
    </template>
  </div>

  <!-- 管理员账号（列表全员可读；新建/编辑/停用仅超管） -->
  <div v-else-if="st.tab === 'admins'" class="card" style="padding:0">
    <!-- 非超管只读提示 -->
    <div v-if="!isSuper" style="display:flex;align-items:center;gap:8px;margin:12px;padding:10px 14px;background:var(--pale-warn);border-radius:10px;font-size:12.5px">
      🔒 仅超管可管理（当前账号为{{ ROLE_LABEL[session.role] || '管理员' }}，以下为只读视图）
    </div>
    <div v-if="adminsErr" style="display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 14px;margin:12px;background:var(--pale-error);border-radius:10px;font-size:12.5px;color:var(--error)">
      <span>⚠️ 管理员列表加载失败</span>
      <button class="btn btn-secondary btn-sm" @click="loadAdmins">重试</button>
    </div>
    <!-- tbl-wrap：sticky 表头 + 限高内滚（与 raw 日志表格一致，账号多时页内滚动） -->
    <div class="tbl-wrap">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)">
          <th style="padding:12px 18px">账号</th><th>角色</th><th style="text-align:right">操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="a in admins" :key="a.id" style="border-top:1px solid var(--gray-light)">
            <td style="padding:12px 18px">
              <template v-if="editId === a.id && isSuper">
                <div style="display:flex;gap:8px;flex-wrap:wrap">
                  <input v-model="editDraft.name" class="input" style="width:160px" placeholder="姓名">
                  <select v-model="editDraft.role" class="input" style="width:auto" :disabled="a.id === session.user?.id" :title="a.id === session.user?.id ? '不能修改自己的角色' : ''">
                    <option value="1">1 · 客服</option><option value="2">2 · 运营</option><option value="3">3 · 仓库</option><option value="9">9 · 超管</option>
                  </select>
                </div>
                <div style="font-size:11.5px;color:var(--gray);margin-top:4px">{{ a.email }}<span v-if="a.id === session.user?.id"> · 当前登录账号</span></div>
              </template>
              <template v-else>
                <b>{{ a.name || '—' }}</b><span v-if="a.id === session.user?.id" class="tag tag-pending" style="margin-left:6px;font-size:10px">我</span>
                <div style="font-size:11.5px;color:var(--gray)">{{ a.email }}</div>
              </template>
            </td>
            <td><span class="tag" :class="roleCls(a.role)">{{ ROLE_LABEL[a.role] || a.role }}</span></td>
            <td style="text-align:right;white-space:nowrap">
              <template v-if="isSuper">
                <template v-if="editId === a.id">
                  <button class="btn btn-primary btn-sm" :class="{ loading: savingAdmin === a.id }" :disabled="savingAdmin" @click="saveAdmin(a)">保存</button>
                  <button class="btn btn-secondary btn-sm" :disabled="savingAdmin" @click="cancelEditAdmin">取消</button>
                </template>
                <template v-else>
                  <button class="btn btn-secondary btn-sm" :class="{ loading: savingAdmin === a.id }" :disabled="savingAdmin" @click="openEditAdmin(a)">编辑</button>
                  <button
                    class="btn btn-ghost btn-sm"
                    style="color:var(--error)"
                    :disabled="savingAdmin || a.id === session.user?.id"
                    :title="a.id === session.user?.id ? '不能停用自己' : '停用后该账号无法登录后台'"
                    @click="openOffAdmin(a)"
                  >停用</button>
                </template>
              </template>
              <span v-else style="color:var(--gray);font-size:12px">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <EmptyState v-if="adminsLoaded && !adminsErr && !admins.length" icon="👤" title="暂无管理账号" sub="客服/运营/仓库/超管的启用账号将显示在这里" />

    <!-- 新建表单（仅超管） -->
    <div v-if="isSuper" style="padding:16px 18px;border-top:1px solid var(--gray-light)">
      <div class="dhead" style="margin-bottom:10px"><div class="dtitle">新建管理员</div></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <input v-model="adminForm.email" class="input" style="flex:1;min-width:180px" placeholder="邮箱" @keydown.enter="createAdmin">
        <input v-model="adminForm.name" class="input" style="width:120px" placeholder="姓名" @keydown.enter="createAdmin">
        <input v-model="adminForm.password" class="input" type="password" style="width:150px" placeholder="密码（≥8 位）" @keydown.enter="createAdmin">
        <select v-model="adminForm.role" class="input" style="width:auto">
          <option value="1">1 · 客服</option><option value="2">2 · 运营</option><option value="3">3 · 仓库</option><option value="9">9 · 超管</option>
        </select>
        <button class="btn btn-primary" :class="{ loading: creating }" :disabled="creating" @click="createAdmin">创建</button>
      </div>
      <p style="font-size:11.5px;color:var(--gray);margin-top:6px">角色权限：客服={{ ROLE_SCOPE_DESC[1] }}；运营={{ ROLE_SCOPE_DESC[2] }}；仓库={{ ROLE_SCOPE_DESC[3] }}；超管={{ ROLE_SCOPE_DESC[9] }}。</p>
    </div>
  </div>

  <!-- 媒体库（q 搜索 + 分页 + 缩略图 + 上传/删除） -->
  <div v-else-if="st.tab === 'media'" class="card" style="padding:0">
    <div class="filter-bar" style="padding:12px 14px;border-bottom:1px solid var(--gray-light)">
      <input v-model="mQ" class="input" style="width:240px" placeholder="按文件名搜索（支持 202601/ 目录段）" @keydown.enter="searchMedia()">
      <button class="btn btn-secondary btn-sm" style="height:38px" @click="searchMedia()">搜索</button>
      <span style="flex:1"></span>
      <input ref="fileInput" type="file" accept="image/png,image/jpeg,image/webp,image/gif" style="display:none" @change="onPickFile">
      <button class="btn btn-primary btn-sm" style="height:38px" :class="{ loading: uploading }" :disabled="uploading" @click="pickFile">{{ uploading ? '上传中…' : '⬆ 上传新文件' }}</button>
    </div>
    <div v-if="mErr" style="display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 14px;margin:12px;background:var(--pale-error);border-radius:10px;font-size:12.5px;color:var(--error)">
      <span>⚠️ 媒体库加载失败</span>
      <button class="btn btn-secondary btn-sm" @click="loadMedia(mPage)">重试</button>
    </div>
    <!-- tbl-wrap：sticky 表头 + 限高内滚（缩略图较多时页内滚动） -->
    <div class="tbl-wrap">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)">
          <th style="padding:12px 14px">预览</th><th>文件名</th><th>大小</th><th>修改时间</th><th style="text-align:right">操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="m in media" :key="m.name" style="border-top:1px solid var(--gray-light)">
            <td style="padding:8px 14px">
              <a :href="mediaSrc(m)" target="_blank" rel="noopener" title="在新窗口查看原图">
                <img :src="mediaSrc(m)" :alt="m.name" loading="lazy" style="width:44px;height:44px;object-fit:cover;border-radius:8px;border:1px solid var(--gray-light);display:block" @error="$event.target.style.visibility='hidden'">
              </a>
            </td>
            <td style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="m.name"><code>{{ m.name }}</code></td>
            <td style="white-space:nowrap">{{ fmtBytes(m.bytes) }}</td>
            <td style="color:var(--gray);white-space:nowrap">{{ dt(m.modified_at) || '—' }}</td>
            <td style="text-align:right">
              <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="openDelMedia(m)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <EmptyState v-if="mLoaded && !mErr && !media.length" :icon="mQ.trim() ? '🔍' : '🖼'" :title="mQ.trim() ? '未找到匹配的文件' : '媒体库为空'" :sub="mQ.trim() ? '试试调整或清除搜索' : '上传的商品图片将显示在这里'" />
    <Pagination embed :page="mPage" :pages="mPages" :total="mTotal" unit="个" @go="loadMedia" />
  </div>

  <!-- 全部参数（raw k-v，支持关键字过滤） -->
  <div v-else class="card tbl-wrap">
    <div class="filter-bar" style="padding:12px 14px;border-bottom:1px solid var(--gray-light)">
      <input v-model="rawFilter" class="input" style="width:260px" placeholder="按 Key / 说明关键字过滤">
      <span style="font-size:12px;color:var(--gray)">匹配 {{ rawRows.length }} / {{ Object.keys(settings).length }} 项</span>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:10px">Key</th><th>Value</th><th>说明</th><th>最后修改</th></tr></thead>
      <tbody>
        <tr v-for="[key, v] in rawRows" :key="key" style="border-top:1px solid var(--gray-light)">
          <td style="padding:10px"><b>{{ key }}</b></td>
          <td>
            <code>{{ JSON.stringify(v.value) }}</code>
            <!-- llm_config / payment_config 的密钥字段后端已掩码（*_set 标记真实存在性）：提示不可复制原值 -->
            <span v-if="key === 'llm_config' || key === 'payment_config'" class="tag tag-pending" style="margin-left:6px;font-size:10px" title="敏感字段（API Key / 支付密钥）由服务端掩码存储，此处展示非原值">敏感项已脱敏</span>
          </td>
          <td style="color:var(--gray)">{{ v.description || '—' }}</td>
          <td style="color:var(--gray);white-space:nowrap">{{ v.updated_by != null ? '#' + v.updated_by : '—' }} · {{ dt(v.updated_at) || '—' }}</td>
        </tr>
      </tbody>
    </table>
    <EmptyState v-if="loaded && !Object.keys(settings).length" icon="⚙️" title="暂无参数" sub="服务端暂无预置参数，保存后将写入并即时生效" />
    <EmptyState v-else-if="loaded && !rawRows.length" icon="🔍" title="没有匹配的参数" :sub="'没有匹配「' + rawFilter + '」的参数'" />
  </div>

  <!-- Mock 支付开/关确认：开启走 danger（生产放行模拟收款）；关闭提示前台通道收敛 -->
  <ConfirmDialog
    :open="mockOnDlg" title="开启 Mock 支付" danger confirm-text="确认开启" :busy="payBusy"
    body="确认开启 Mock 模拟支付？开启后前台可用模拟通道直接完成下单（生产环境同样生效），接入真实支付后请及时关闭。"
    @confirm="mockOnDlg = false; setMockPay(1)" @close="mockOnDlg = false"
  />
  <ConfirmDialog
    :open="mockOffDlg" title="关闭 Mock 支付" confirm-text="确认关闭" :busy="payBusy"
    body="确认关闭 Mock 模拟支付？关闭后前台仅保留真实支付通道，无可用通道时结算按钮将置灰。"
    @confirm="mockOffDlg = false; setMockPay(0)" @close="mockOffDlg = false"
  />

  <!-- 清除支付密钥确认（danger）：清除=该字段回落环境变量配置 -->
  <ConfirmDialog
    :open="payClearDlg.open" :title="payClearDlg.title" danger confirm-text="确认清除" :busy="paySaving !== ''"
    :body="payClearDlg.body"
    @confirm="payClearConfirm" @close="payClearDlg.open = false"
  />

  <!-- 清除 API Key 确认（danger）：清除后回退规则引擎，前台客服不中断 -->
  <ConfirmDialog
    :open="clearDlg" title="清除 API Key" danger confirm-text="确认清除" :busy="aiSaving"
    body="确认清除已保存的 API Key？清除后 AI 客服回退内置规则引擎（环境变量配置不受影响）。"
    @confirm="clearAiKey" @close="clearDlg = false"
  />

  <!-- RAG 全量重建确认（danger）：覆盖所有 FAQ 向量 -->
  <ConfirmDialog
    :open="rebuildDlg" title="全量重建 FAQ 索引" danger confirm-text="确认重建" :busy="aiReidx"
    body="全量重建将覆盖所有 FAQ 向量并重新调用 embedding 接口（更换向量模型后使用），耗时与 FAQ 数量相关。"
    @confirm="rebuildDlg = false; reindexRag(true)" @close="rebuildDlg = false"
  />

  <!-- 模板预览弹窗（iframe 沙箱渲染 html，宽度自适应邮件版式） -->
  <div v-if="previewTpl" class="modal open" @click.self="previewTpl = null">
    <div class="modal-box" style="max-width:880px">
      <button class="modal-x" @click="previewTpl = null">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:10px">{{ previewTpl.name }}</h3>
      <iframe :srcdoc="previewTpl.html" sandbox style="width:100%;height:60vh;border:1px solid var(--gray-light);border-radius:10px;background:#fff"></iframe>
    </div>
  </div>

  <!-- 停用管理员确认（danger）：自己行的按钮已禁用，后端 cannot modify self 兜底 -->
  <ConfirmDialog
    :open="offDlg" title="停用管理员" danger confirm-text="确认停用" :busy="savingAdmin !== 0"
    :body="`确认停用 ${offTarget?.name}（${offTarget?.email}）？停用后该账号无法登录后台，且不再出现在列表中。`"
    @confirm="offAdminConfirm" @close="offDlg = false"
  />

  <!-- 删除媒体确认（danger）：被商品引用的文件后端 409 拒删 -->
  <ConfirmDialog
    :open="delMDlg" title="删除媒体文件" danger confirm-text="确认删除" :busy="delMBusy"
    :body="`确认删除 ${delMTarget?.name}？正在被商品引用的文件不可删除（后端将拒绝）；删除后引用该文件的页面将无法显示图片。`"
    @confirm="delMediaConfirm" @close="delMDlg = false"
  />
</template>

<style scoped>
/* 参数表单两列栅格（窄屏单列），替代单列 max-width 布局 */
.set-grid{display:grid;grid-template-columns:1fr 1fr;column-gap:28px;align-items:start}
@media(max-width:768px){.set-grid{grid-template-columns:1fr}}
/* AI 提示词预览框 */
.ai-prev{background:var(--bg-page);border:1px solid var(--gray-light);border-radius:10px;padding:10px 12px;max-height:260px;overflow-y:auto}
/* ===== AI 客服 tab：状态带 + 分区表单 ===== */
/* 状态带：图标圆片 + 主/副文案 + 状态 tag（启用时图标染品牌色） */
.ai-status{display:flex;gap:14px;align-items:center;padding:16px 20px;border-bottom:1px solid var(--gray-light)}
.ai-status-ico{width:42px;height:42px;border-radius:12px;background:var(--gray-light);display:flex;align-items:center;justify-content:center;font-size:21px;flex:none}
.ai-status-ico.on{background:var(--rose-pale)}
.ai-status-sub{font-size:12px;color:var(--gray);margin-top:3px;line-height:1.6}
.ai-status-sub code{background:var(--gray-light);border-radius:5px;padding:1px 5px;font-size:11.5px}
/* 分区：上边线分隔，标题行用全局 .dtitle（plum 指示条）；hint 右对齐灰字 */
.ai-sec{padding:18px 20px;border-top:1px solid var(--gray-light)}
.ai-sec:first-of-type{border-top:none}
.ai-sec-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:14px}
.ai-hint{font-size:11.5px;color:var(--gray);font-weight:400}
/* 12 列栅格：字段跨列由 s3/s4/s6/s8/s12 控制，窄屏全部整行 */
.ai-grid{display:grid;grid-template-columns:repeat(12,1fr);gap:14px}
.ai-grid .s3{grid-column:span 3}
.ai-grid .s4{grid-column:span 4}
.ai-grid .s6{grid-column:span 6}
.ai-grid .s8{grid-column:span 8}
.ai-grid .s12{grid-column:span 12}
@media(max-width:768px){.ai-grid .s3,.ai-grid .s4,.ai-grid .s6,.ai-grid .s8{grid-column:span 12}}
/* 字段下小注（范围/默认值/用途），替代塞进 label 的长括号说明 */
.ai-note{font-size:11.5px;color:var(--gray);margin-top:5px;line-height:1.6}
/* RAG 行：向量模型输入 + 两个操作按钮底对齐 */
.ai-rag-row{display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap}
.ai-rag-row .btn{height:38px;flex:none}
/* 底部操作/说明区：浅底与表单区分，形成页脚带 */
.ai-sec-foot{background:var(--bg-page)}
.ai-btn-row{display:flex;gap:10px;flex-wrap:wrap}
/* 测试连接结果条：成功/失败语义色底（替代挤在按钮行内的 tag） */
.ai-test{display:flex;gap:8px;align-items:flex-start;margin-top:12px;padding:10px 12px;border-radius:10px;font-size:12.5px;line-height:1.6;word-break:break-all}
.ai-test.ok{background:var(--pale-success);color:#1E7A45}
.ai-test.err{background:var(--pale-error);color:var(--error)}
.ai-sec-foot .ai-prev{margin-top:12px;background:#fff}
/* 机制说明：标签列 + 说明列，替代 br 堆叠的灰字墙 */
.ai-foot{padding-top:14px;padding-bottom:14px}
.ai-foot-row{display:grid;grid-template-columns:64px 1fr;gap:10px;font-size:11.5px;color:var(--gray);line-height:1.7;padding:2px 0}
.ai-foot-row b{color:var(--plum);font-weight:600}
/* ===== 支付通道 tab：摘要条 + 双通道卡 + Mock 条 + 说明卡 ===== */
/* 摘要条：图标 + 默认链/前台可用 + 右侧刷新与回调地址快捷复制（有真实通道时染品牌色） */
.pay-hero{display:flex;gap:16px;align-items:center;padding:18px 20px;margin-bottom:16px;flex-wrap:wrap;position:relative;overflow:hidden}
.pay-hero::before{content:"";position:absolute;inset:0 auto 0 0;width:4px;background:var(--gray-light)}
.pay-hero.ok::before{background:var(--plum)}
.pay-hero-ico{width:46px;height:46px;border-radius:14px;background:var(--gray-light);display:flex;align-items:center;justify-content:center;font-size:22px;flex:none}
.pay-hero-ico.on{background:var(--rose-pale)}
.pay-hero-main{flex:1;min-width:230px}
.pay-hero-title{font-size:14px}
.pay-hero-title b{color:var(--ink)}
.pay-hero-env{display:inline-block;margin-left:8px;font-size:10.5px;font-weight:700;letter-spacing:.5px;color:var(--warn);background:var(--pale-warn);border-radius:999px;padding:1px 8px;vertical-align:1px}
.pay-hero-sub{font-size:12px;color:var(--gray);margin-top:4px;line-height:1.7}
.pay-hero-side{display:flex;flex-direction:column;gap:8px;align-items:flex-end}
/* 回调地址胶囊按钮（hover 提示可复制） */
.pay-hook{border:1px dashed var(--gray-light);background:#fff;border-radius:8px;padding:3px 8px;cursor:pointer;max-width:340px;overflow:hidden}
.pay-hook:hover{border-color:var(--plum)}
.pay-hook code{font-size:11px;color:var(--gray);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block}
/* 前台可用通道小胶囊 */
.pay-chip{display:inline-flex;align-items:center;background:var(--pale-success);color:#1E7A45;font-size:11px;font-weight:700;border-radius:999px;padding:2px 9px;margin:0 3px}
.pay-chip.warn{background:var(--pale-warn);color:var(--warn)}
/* 双通道卡：宽屏并排（Stripe / PayPal 同屏对照），窄屏堆叠 */
.pay-cards{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start;margin-bottom:16px}
@media(max-width:1100px){.pay-cards{grid-template-columns:1fr}}
.pay-card{background:#fff;border-radius:14px;box-shadow:var(--shadow-card);overflow:hidden}
/* 卡头：品牌渐变色块 + 名称/掩码 + 状态徽章 */
.pay-card-head{display:flex;gap:12px;align-items:center;padding:15px 18px;border-bottom:1px solid var(--gray-light);background:linear-gradient(180deg,#FDFBFC,#fff)}
.pay-card-head-txt{flex:1;min-width:0}
.pay-card-name{font-size:14.5px;font-weight:700}
.pay-card-sub{font-size:11.5px;color:var(--gray);font-weight:400;margin-left:6px}
.pay-card-meta{font-size:11.5px;color:var(--gray);margin-top:3px;line-height:1.6}
.pay-card-meta code{background:var(--gray-light);border-radius:5px;padding:1px 5px;font-size:11px}
.pay-brand-tile{width:42px;height:42px;border-radius:12px;color:#fff;font-size:19px;font-weight:800;font-style:italic;display:flex;align-items:center;justify-content:center;flex:none;box-shadow:0 2px 6px rgba(0,0,0,.14)}
/* 卡体：单列表单（卡已窄），字段间距 14px */
.pay-card-body{padding:16px 18px;display:flex;flex-direction:column;gap:14px}
/* 卡脚：浅底操作带，测试结果整行展开 */
.pay-card-foot{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:12px 18px;border-top:1px solid var(--gray-light);background:var(--bg-page)}
.pay-card-foot .pay-test{flex-basis:100%;margin:0}
.pay-hint{font-size:11.5px;color:var(--gray);font-weight:400}
.pay-note{font-size:11.5px;color:var(--gray);margin-top:5px;line-height:1.6}
/* 缺包降级横幅 */
.pay-warn{display:flex;gap:8px;align-items:flex-start;background:var(--pale-warn);padding:10px 18px;font-size:12px;line-height:1.6;color:#8A6D1B;border-bottom:1px solid #F0E3C2}
.pay-warn code{background:rgba(0,0,0,.06);border-radius:5px;padding:1px 5px}
/* 测试结果条 */
.pay-test{display:flex;gap:8px;align-items:flex-start;padding:9px 12px;border-radius:10px;font-size:12.5px;line-height:1.6;word-break:break-all}
.pay-test.ok{background:var(--pale-success);color:#1E7A45}
.pay-test.err{background:var(--pale-error);color:var(--error)}
/* Klarna 开关：胶囊滑块（键盘可达 role=switch） */
.pay-switch-row{display:flex;align-items:center;gap:10px;cursor:pointer;font-size:13px;font-weight:600;padding:10px 12px;background:var(--bg-page);border-radius:10px}
.pay-switch-row:has(.pay-switch:not(.on)){background:#fff;border:1px solid var(--gray-light)}
.pay-switch{width:40px;height:22px;border-radius:999px;background:var(--gray-light);position:relative;transition:background .2s;flex:none;border:none;padding:0;flex-shrink:0}
.pay-switch i{position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.25);transition:left .2s}
.pay-switch.on{background:var(--plum)}
.pay-switch.on i{left:21px}
/* PayPal 环境分段选择 */
.pay-seg{display:inline-flex;border:1.5px solid var(--gray-light);border-radius:10px;overflow:hidden;background:#fff}
.pay-seg button{border:none;background:none;padding:8px 18px;font-size:12.5px;font-weight:600;color:var(--gray);cursor:pointer;transition:background .15s,color .15s}
.pay-seg button+button{border-left:1.5px solid var(--gray-light)}
.pay-seg button.on{background:var(--plum);color:#fff}
.pay-seg button:disabled{cursor:not-allowed;opacity:.6}
/* Mock 紧凑条：单行卡片（色块 + 文案 + 状态 + 开关） */
.pay-mock{display:flex;gap:12px;align-items:center;padding:14px 18px;margin-bottom:16px;flex-wrap:wrap}
.pay-mock .pay-brand-tile{width:38px;height:38px;font-size:17px;border-radius:11px}
.pay-mock-ops{display:flex;gap:8px;align-items:center}
/* 机制说明卡：首行回调地址整行 + 2 列小注 */
.pay-foot-card{background:#fff;border-radius:14px;box-shadow:var(--shadow-card);padding:14px 18px;display:grid;grid-template-columns:1fr 1fr;gap:4px 28px}
.pay-foot-item{display:grid;grid-template-columns:64px 1fr;gap:10px;font-size:11.5px;color:var(--gray);line-height:1.7;padding:5px 0}
.pay-foot-item b{color:var(--plum);font-weight:600}
.pay-foot-hook{grid-column:1 / -1;border-bottom:1px dashed var(--gray-light);margin-bottom:4px;padding-bottom:10px}
@media(max-width:768px){.pay-foot-card{grid-template-columns:1fr}.pay-hero-side{align-items:flex-start}}
</style>
