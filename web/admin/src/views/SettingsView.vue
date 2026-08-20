<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'

const tab = ref('shipping')
const settings = reactive({})   /* key → {value, description} */
const templates = ref([])
const loaded = ref(false)
const settingsErr = ref(false)  /* 配置加载失败：禁用保存，防止默认值覆盖线上配置 */

/* 可编辑运营 key —— 必须与后端消费方一致：
 * pricing.py: free_shipping_threshold / shipping_standard / shipping_express / tax_rate / bundle_2_off / bundle_3_off
 * seed: return_days / points_per_dollar_earn（PUT 为 upsert，缺失 key 也能保存生效） */
const EDITABLE = {
  free_shipping_threshold: { label: '满额免邮（分）', type: 'number', def: 3500 },
  shipping_standard: { label: '标准运费（分）', type: 'number', def: 499 },
  shipping_express: { label: '快递运费（分）', type: 'number', def: 1499 },
  tax_rate: { label: '综合税率', type: 'number', step: '0.0001', def: 0.0735 },
  return_days: { label: '退货窗口（天）', type: 'number', def: 30 },
  points_per_dollar_earn: { label: '消费 $1 赚积分', type: 'number', def: 10 },
  bundle_2_off: { label: '买 2 件折扣 %', type: 'number', def: 15 },
  bundle_3_off: { label: '买 3+ 件折扣 %', type: 'number', def: 20 },
}
const drafts = reactive({})   /* key → 编辑值（数字） */

async function load() {
  loaded.value = false
  settingsErr.value = false
  try {
    const rows = (await req('GET', '/api/admin/ops/settings')).items || []
    for (const r of rows) {
      settings[r.key] = { value: r.value, description: r.description }
    }
  } catch (e) {
    settingsErr.value = true
    toast('配置加载失败：' + (e.message || ''), 'error')
  }
  for (const [key, meta] of Object.entries(EDITABLE)) {
    drafts[key] = key in settings ? settings[key].value : meta.def
  }
  try { templates.value = (await req('GET', '/api/admin/ops/email-templates')).items || [] } catch (_) { /* */ }
  loaded.value = true
}
onMounted(load)

const saving = ref('')
async function saveKey(key) {
  if (settingsErr.value) { toast('配置加载失败，已禁用保存（防止默认值覆盖线上配置），请先重试加载', 'error'); return }
  const n = Number(drafts[key])
  if (!Number.isFinite(n) || n < 0) { toast('请输入有效的非负数字', 'error'); return }
  saving.value = key
  try {
    await req('PUT', '/api/admin/ops/settings', { key, value: n })
    settings[key] = { value: n, description: settings[key]?.description }
    toast(`「${EDITABLE[key].label}」已保存 ✓`, 'success')
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
  finally { saving.value = '' }
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
      <h1 style="font-size:22px">系统设置</h1>
      <span style="font-size:12.5px;color:var(--gray)">运费 / 税率 / 捆绑 / 运营参数 / 邮件模板</span>
    </div>
  </div>

  <div class="otab" style="display:flex;gap:4px;border-bottom:1.5px solid var(--gray-light);margin-bottom:14px">
    <button
      v-for="[k, label] in [['shipping', '运费与运营'], ['email', '邮件模板'], ['raw', '全部参数']]"
      :key="k"
      style="padding:9px 16px;font-size:13.5px;font-weight:600;border:none;background:none;cursor:pointer"
      :style="{ color: tab === k ? 'var(--plum)' : 'var(--gray)', borderBottom: tab === k ? '2.5px solid var(--plum)' : '2.5px solid transparent' }"
      @click="tab = k"
    >{{ label }}</button>
  </div>

  <!-- 运费与运营（常用 key 表单化；保存即 upsert，未初始化的 key 用默认值占位） -->
  <div v-if="tab === 'shipping'" class="card" style="padding:20px;max-width:620px">
    <div v-if="settingsErr" style="display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 14px;margin-bottom:16px;background:#FDECEC;border:1px solid var(--error);border-radius:10px;font-size:12.5px;color:var(--error)">
      <span>⚠️ 配置加载失败，保存已禁用——防止默认值覆盖线上配置</span>
      <button class="btn btn-secondary btn-sm" @click="load">重试加载</button>
    </div>
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
    <div v-if="loaded && !settingsErr && !Object.keys(settings).length" style="color:var(--gray);font-size:13px;margin-top:6px">
      服务端暂无预置参数，上方表单保存后将写入并即时生效。
    </div>
  </div>

  <!-- 邮件模板 -->
  <div v-else-if="tab === 'email'" class="card" style="padding:0">
    <div v-for="t in tplList()" :key="t.name" class="setrow" style="padding:14px 18px;border-bottom:1px solid var(--gray-light)">
      <div><b>{{ t.name }}</b><div style="font-size:12px;color:var(--gray)">主题：{{ t.subject }}</div></div>
      <button class="btn btn-secondary btn-sm" @click="showTpl(t)">👁 预览</button>
    </div>
    <div v-if="loaded && !tplList().length" style="text-align:center;color:var(--gray);padding:24px 0">暂无模板</div>
  </div>

  <!-- 全部参数（raw k-v，支持关键字过滤） -->
  <div v-else class="card tbl-wrap">
    <div style="display:flex;align-items:center;gap:10px;padding:12px 14px;border-bottom:1px solid var(--gray-light);flex-wrap:wrap">
      <input v-model="rawFilter" class="input" style="width:260px" placeholder="按 Key / 说明关键字过滤">
      <span style="font-size:12px;color:var(--gray)">匹配 {{ rawRows.length }} / {{ Object.keys(settings).length }} 项</span>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:10px">Key</th><th>Value</th><th>说明</th></tr></thead>
      <tbody>
        <tr v-for="[key, v] in rawRows" :key="key" style="border-top:1px solid var(--gray-light)">
          <td style="padding:10px"><b>{{ key }}</b></td>
          <td><code>{{ JSON.stringify(v.value) }}</code></td>
          <td style="color:var(--gray)">{{ v.description || '—' }}</td>
        </tr>
      </tbody>
    </table>
    <div v-if="loaded && !Object.keys(settings).length" style="text-align:center;color:var(--gray);padding:24px 0">暂无参数</div>
    <div v-else-if="loaded && !rawRows.length" style="text-align:center;color:var(--gray);padding:24px 0">没有匹配「{{ rawFilter }}」的参数</div>
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
