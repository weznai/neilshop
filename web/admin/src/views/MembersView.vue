<script setup>
import { computed, onMounted, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'

const members = ref([])
const total = ref(0)
const q = ref('')
const tier = ref('')          /* '' = 全部等级（后端 tier 为精确匹配，null 不过滤） */
const page = ref(1)
const SIZE = 50
const active = ref(null)
const loaded = ref(false)
const loadErr = ref(false)

const TIER = ['Glow', 'Shimmer', 'Diva', 'Queen']
const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
const pages = computed(() => Math.max(1, Math.ceil(total.value / SIZE)))

async function load(p = 1) {
  loaded.value = false
  loadErr.value = false
  try {
    const params = new URLSearchParams({ page: p, size: SIZE })
    const s = q.value.trim()
    if (s) params.set('q', s)
    if (tier.value !== '') params.set('tier', tier.value)
    const d = await req('GET', '/api/admin/ops/members?' + params)
    members.value = d.items || []
    total.value = d.total ?? 0
    page.value = d.page || p
  } catch (e) {
    loadErr.value = true
    toast('会员列表加载失败：' + (e.message || ''), 'error')
  }
  loaded.value = true
}
onMounted(() => load(1))

function search() { load(1) }
function setTier(v) { tier.value = v; load(1) }
function go(d) { const n = page.value + d; if (n >= 1 && n <= pages.value) load(n) }

async function openDetail(m) {
  try {
    active.value = await req('GET', '/api/admin/ops/members/' + m.id)
    riskDraft.value = String(active.value.risk_flag || 0)
  }
  catch (e) { toast('加载失败：' + (e.message || ''), 'error') }
}

/* 风控下拉：受控 v-model（riskDraft），确认/取消/失败都回写草稿值驱动视图复位 */
const riskDraft = ref('0')
async function setRisk(flag) {
  const cur = active.value.risk_flag || 0
  if (flag === cur) return
  if (flag === 2) {
    const name = active.value.name || active.value.email
    if (!confirm(`确认将「${name}」加入黑名单？\n黑名单会员下单时将被风控拦截，无法完成支付。`)) {
      riskDraft.value = String(cur)   /* 取消：受控回滚 */
      return
    }
  }
  try {
    await req('POST', `/api/admin/ops/members/${active.value.id}/risk`, { flag })
    active.value.risk_flag = flag
    riskDraft.value = String(flag)
    members.value = members.value.map((x) => (x.id === active.value.id ? { ...x, risk_flag: flag } : x))
    toast(flag === 2 ? '已加入黑名单（下单将被风控拦截）' : '风控状态已更新 ✓', 'success')
  } catch (e) {
    riskDraft.value = String(cur)   /* 失败：受控回滚 */
    toast('操作失败：' + (e.data?.detail || e.message), 'error')
  }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">会员管理</h1>
      <span style="font-size:12.5px;color:var(--gray)">共 {{ total }} 位会员</span>
    </div>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <select class="input" :value="tier" style="width:auto;height:38px;font-size:13px" @change="setTier($event.target.value)">
        <option value="">全部等级</option>
        <option v-for="(t, i) in TIER" :key="i" :value="String(i)">{{ t }}</option>
      </select>
      <input v-model="q" class="input" style="width:220px" placeholder="搜邮箱 / 姓名" @keydown.enter="search()">
      <button class="btn btn-secondary btn-sm" style="height:38px" @click="search()">搜索</button>
    </div>
  </div>

  <div class="card tbl-wrap">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)">
        <th style="padding:10px">会员</th><th>等级</th><th>积分</th><th>累计消费</th><th>最近下单</th><th>风控</th><th style="text-align:right">操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="m in members" :key="m.id" style="border-top:1px solid var(--gray-light)">
          <td style="padding:10px">
            <div style="display:flex;gap:10px;align-items:center">
              <span style="width:34px;height:34px;border-radius:50%;background:var(--rose);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:700">
                {{ (m.name || m.email || '?').charAt(0).toUpperCase() }}
              </span>
              <div><b>{{ m.name || '—' }}</b><div style="font-size:11.5px;color:var(--gray)">{{ m.email }}</div></div>
            </div>
          </td>
          <td><span class="tag tag-paid">{{ TIER[m.tier || 0] }}</span></td>
          <td><b style="color:var(--plum)">{{ (m.points || 0).toLocaleString() }}</b></td>
          <td>{{ money(m.total_spent) }}</td>
          <td style="color:var(--gray)">{{ m.last_order_at ? m.last_order_at.slice(0, 10) : '—' }}</td>
          <td><span class="tag" :class="m.risk_flag === 2 ? 'tag-error' : m.risk_flag === 1 ? 'tag-pending' : 'tag-done'">
            {{ ['正常', '关注', '黑名单'][m.risk_flag || 0] }}</span></td>
          <td style="text-align:right"><button class="btn btn-secondary btn-sm" @click="openDetail(m)">画像</button></td>
        </tr>
      </tbody>
    </table>
    <div v-if="loadErr" style="text-align:center;padding:28px 0">
      <div style="font-size:24px;margin-bottom:6px">⚠️</div>
      <div style="color:var(--error);font-size:13px;margin-bottom:10px">会员列表加载失败</div>
      <button class="btn btn-secondary btn-sm" @click="load(1)">重试</button>
    </div>
    <div v-else-if="loaded && !members.length" style="text-align:center;color:var(--gray);padding:28px 0">没有匹配会员</div>
    <div v-if="pages > 1" style="display:flex;justify-content:space-between;align-items:center;padding:12px 10px;font-size:12.5px;color:var(--gray);border-top:1px solid var(--gray-light)">
      <span>第 {{ page }} / {{ pages }} 页 · 共 {{ total }} 位</span>
      <div style="display:flex;gap:8px">
        <button class="btn btn-secondary btn-sm" :disabled="page <= 1" :style="{ opacity: page <= 1 ? 0.45 : 1 }" @click="go(-1)">上一页</button>
        <button class="btn btn-secondary btn-sm" :disabled="page >= pages" :style="{ opacity: page >= pages ? 0.45 : 1 }" @click="go(1)">下一页</button>
      </div>
    </div>
  </div>

  <!-- 会员画像弹窗 -->
  <div v-if="active" class="modal open" @click.self="active = null">
    <div class="modal-box" style="max-width:540px">
      <button class="modal-x" @click="active = null">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:4px">{{ active.name || active.email }}</h3>
      <div style="font-size:12.5px;color:var(--gray);margin-bottom:14px">
        {{ active.email }} · 加入于 {{ (active.created_at || '').slice(0, 10) }}
      </div>
      <div class="grid-2" style="gap:10px;margin-bottom:14px">
        <div class="stat"><div class="lb">等级</div><div class="vl" style="font-size:18px">{{ TIER[active.tier || 0] }}</div></div>
        <div class="stat"><div class="lb">积分</div><div class="vl" style="font-size:18px;color:var(--plum)">{{ (active.points || 0).toLocaleString() }}</div></div>
        <div class="stat"><div class="lb">累计消费</div><div class="vl" style="font-size:18px">{{ money(active.total_spent) }}</div></div>
        <div class="stat"><div class="lb">最近下单</div><div class="vl" style="font-size:15px">{{ active.last_order_at ? active.last_order_at.slice(0, 10) : '—' }}</div></div>
      </div>

      <div class="field">
        <label>风控状态</label>
        <select v-model="riskDraft" class="input" @change="setRisk(parseInt(riskDraft, 10))">
          <option value="0">正常</option><option value="1">关注</option><option value="2">黑名单</option>
        </select>
        <p style="font-size:11.5px;color:var(--gray);margin-top:6px">黑名单会员下单时将被风控拦截（无法完成支付）；「关注」仅标记观察，不影响下单。</p>
      </div>

      <div style="margin-top:6px">
        <router-link to="/orders" style="font-size:12.5px;color:var(--plum)">查看订单 →</router-link>
      </div>

      <div v-if="active.ledger && active.ledger.length" style="margin-top:14px">
        <h4 style="font-size:13.5px;margin-bottom:8px">积分流水（近 {{ Math.min(10, active.ledger.length) }} 条）</h4>
        <div v-for="(l, i) in active.ledger.slice(0, 10)" :key="l.id || i" style="display:flex;justify-content:space-between;gap:10px;font-size:12.5px;padding:6px 0;border-bottom:1px solid var(--gray-light)">
          <span style="color:var(--gray);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
            {{ (l.created_at || '').slice(0, 10) }} · {{ l.reason || '—' }}<span v-if="l.frozen" class="tag tag-pending" style="font-size:10px;margin-left:4px">冻结中</span>
          </span>
          <span style="flex:none;text-align:right">
            <b :style="{ color: (l.change ?? 0) >= 0 ? 'var(--success)' : 'var(--error)' }">{{ (l.change ?? 0) >= 0 ? '+' : '' }}{{ l.change ?? 0 }}</b>
            <span style="color:var(--gray);font-size:11px;margin-left:6px">余 {{ (l.balance_after ?? 0).toLocaleString() }}</span>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
