<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import { dt } from '../composables/format'
import { useQuerySync } from '../composables/useQuerySync'
import EmptyState from '../components/EmptyState.vue'

const TABS = [['shipping', '运费与运营'], ['email', '邮件模板'], ['raw', '全部参数']]
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
  loaded.value = true
}
onMounted(load)

/* 模板区重试：单独重拉邮件模板（失败横幅保留） */
async function retryTemplates() {
  tplErr.value = false
  try { templates.value = (await req('GET', '/api/admin/ops/email-templates')).items || [] }
  catch (_) { tplErr.value = true }
}

const saving = ref('')
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
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
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
    toast(`保存中断（${done}/${keys.length} 已保存）：` + (e.data?.detail || e.message), 'error')
    load()
  } finally { savingAll.value = false }
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
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">系统设置</h1>
      <span class="page-sub">运费 / 税率 / 运营参数 / 邮件模板</span>
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
      捆绑折扣参数已移至 <router-link :to="{ path: '/marketing', query: { tab: 'bundles' } }" style="color:var(--plum)">营销工具 · 捆绑折扣</router-link> 统一管理
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
          <td><code>{{ JSON.stringify(v.value) }}</code></td>
          <td style="color:var(--gray)">{{ v.description || '—' }}</td>
          <td style="color:var(--gray);white-space:nowrap">{{ v.updated_by != null ? '#' + v.updated_by : '—' }} · {{ dt(v.updated_at) || '—' }}</td>
        </tr>
      </tbody>
    </table>
    <EmptyState v-if="loaded && !Object.keys(settings).length" icon="⚙️" title="暂无参数" sub="服务端暂无预置参数，保存后将写入并即时生效" />
    <EmptyState v-else-if="loaded && !rawRows.length" icon="🔍" title="没有匹配的参数" :sub="'没有匹配「' + rawFilter + '」的参数'" />
  </div>

  <!-- 模板预览弹窗（iframe 沙箱渲染 html，宽度自适应邮件版式） -->
  <div v-if="previewTpl" class="modal open" @click.self="previewTpl = null">
    <div class="modal-box" style="max-width:880px">
      <button class="modal-x" @click="previewTpl = null">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:10px">{{ previewTpl.name }}</h3>
      <iframe :srcdoc="previewTpl.html" sandbox style="width:100%;height:60vh;border:1px solid var(--gray-light);border-radius:10px;background:#fff"></iframe>
    </div>
  </div>
</template>

<style scoped>
/* 参数表单两列栅格（窄屏单列），替代单列 max-width 布局 */
.set-grid{display:grid;grid-template-columns:1fr 1fr;column-gap:28px;align-items:start}
@media(max-width:768px){.set-grid{grid-template-columns:1fr}}
</style>
