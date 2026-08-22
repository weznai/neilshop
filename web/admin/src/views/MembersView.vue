<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import { useQuerySync } from '../composables/useQuerySync'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'

const members = ref([])
const total = ref(0)
const tier = ref('')          /* '' = 全部等级（后端 tier 为精确匹配，null 不过滤） */
const SIZE = 50
const active = ref(null)
const loaded = ref(false)
const loadErr = ref(false)
const errMsg = ref('')       /* 最近一次加载失败信息（空态 sub / 横幅文案） */
const detailBusy = ref(false)

/* 筛选/分页 URL 同步（risk：'' 全部 / 0 正常 / 1 关注 / 2 黑名单，见 models/user.py） */
const st = reactive({ q: '', page: 1, risk: '' })
useQuerySync(st, { nums: ['page'], defaults: { page: 1, risk: '' } })

const TIER = ['Glow', 'Shimmer', 'Diva', 'Queen']
/* 等级视觉分档：Glow/Shimmer 淡玫瑰、Diva 蓝调（tag-ship）、Queen 金 */
const tierCls = (t) => (t === 2 ? 'tag-ship' : '')
const tierStyle = (t) => (t === 3 ? 'background:#C9A227;color:#fff' : 'background:var(--rose-pale);color:var(--plum)')
const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
const pages = computed(() => Math.max(1, Math.ceil(total.value / SIZE)))

async function load(p = 1) {
  /* 刷新保留旧数据，骨架只在首载出现 */
  loadErr.value = false
  errMsg.value = ''
  try {
    const params = new URLSearchParams({ page: p, size: SIZE })
    const s = st.q.trim()
    if (s) params.set('q', s)
    if (tier.value !== '') params.set('tier', tier.value)
    if (st.risk !== '') params.set('risk', st.risk)
    if (sort.key) params.set('sort', (sort.dir === -1 ? '-' : '') + sort.key)   /* 服务端白名单排序 */
    const d = await req('GET', '/api/admin/ops/members?' + params)
    members.value = d.items || []
    total.value = d.total ?? 0
    st.page = d.page || p
  } catch (e) {
    loadErr.value = true
    errMsg.value = e.message || ''
    toast('会员列表加载失败：' + (e.message || ''), 'error')
  }
  loaded.value = true
}
onMounted(() => load(st.page))

function search() { load(1) }
function setTier(v) { tier.value = v; load(1) }
function setRiskFilter(v) { st.risk = v; load(1) }
/* 表格空态文案：搜索/等级/风控任一筛选生效→未匹配，否则暂无 */
const filtered = computed(() => st.q.trim() !== '' || tier.value !== '' || st.risk !== '')

/* 服务端排序（积分/累计消费）：点击列头 asc/desc 循环，sort 传后端白名单（points/-points/total_spent/-total_spent） */
const sort = reactive({ key: '', dir: 1 })
function sortBy(k) {
  if (sort.key !== k) { sort.key = k; sort.dir = 1 }
  else { sort.dir = -sort.dir }
  load(1)   /* 全量排序后回第一页；翻页时 load 继续携带排序参数 */
}
const sortInd = (k) => (sort.key === k ? (sort.dir === 1 ? '▲' : '▼') : '')

async function openDetail(m) {
  detailBusy.value = true
  try {
    active.value = await req('GET', '/api/admin/ops/members/' + m.id)
    riskDraft.value = String(active.value.risk_flag || 0)
  }
  catch (e) { toast('加载失败：' + (e.message || ''), 'error') }
  finally { detailBusy.value = false }
}

/* 风控下拉：受控 v-model（riskDraft），确认/取消/失败都回写草稿值驱动视图复位 */
const riskDraft = ref('0')
/* 拉黑走危险确认弹窗（替代原生 confirm），确认后才提交 */
const banDlg = ref(false)
const banBusy = ref(false)
function setRisk(flag) {
  const cur = active.value.risk_flag || 0
  if (flag === cur) return
  if (flag === 2) { banDlg.value = true; return }
  applyRisk(flag)
}
function cancelBan() {
  banDlg.value = false
  riskDraft.value = String(active.value?.risk_flag || 0)   /* 受控回滚 */
}
async function applyRisk(flag = 2) {
  banBusy.value = true
  try {
    await req('POST', `/api/admin/ops/members/${active.value.id}/risk`, { flag })
    active.value.risk_flag = flag
    riskDraft.value = String(flag)
    members.value = members.value.map((x) => (x.id === active.value.id ? { ...x, risk_flag: flag } : x))
    toast(flag === 2 ? '已加入黑名单（下单将被风控拦截）' : '风控状态已更新 ✓', 'success')
    banDlg.value = false
  } catch (e) {
    riskDraft.value = String(active.value.risk_flag || 0)   /* 失败：受控回滚 */
    toast('操作失败：' + (e.data?.detail || e.message), 'error')
  } finally { banBusy.value = false }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">会员管理</h1>
      <span class="page-sub">共 {{ total }} 位会员</span>
    </div>
    <div class="filter-bar">
      <select class="input" :value="tier" style="width:auto;height:38px;font-size:13px" @change="setTier($event.target.value)">
        <option value="">全部等级</option>
        <option v-for="(t, i) in TIER" :key="i" :value="String(i)">{{ t }}</option>
      </select>
      <select class="input" :value="st.risk" style="width:auto;height:38px;font-size:13px" @change="setRiskFilter($event.target.value)">
        <option value="">全部会员</option>
        <option value="0">正常</option>
        <option value="1">关注</option>
        <option value="2">黑名单</option>
      </select>
      <input v-model="st.q" class="input" style="width:220px" placeholder="搜邮箱 / 姓名" @keydown.enter="search()">
      <button class="btn btn-secondary btn-sm" style="height:38px" @click="search()">搜索</button>
    </div>
  </div>

  <div v-if="!loaded" class="card skeleton" style="min-height:280px" />

  <!-- 首屏失败（无旧数据）：错误空态置顶，隐藏表格 -->
  <EmptyState v-else-if="loadErr && !members.length" icon="⚠️" title="会员列表加载失败" :sub="errMsg || '服务端可能未启动或会话已过期'">
    <template #action><button class="btn btn-secondary btn-sm" @click="load(st.page)">重试</button></template>
  </EmptyState>

  <div v-else class="card tbl-wrap">
    <!-- 刷新失败（有旧数据）：卡内顶部横幅，旧数据保留 -->
    <div v-if="loadErr" class="err-banner">
      <span>⚠️ 刷新失败：{{ errMsg || '网络异常，下方为旧数据' }}</span>
      <button class="btn btn-secondary btn-sm" @click="load(st.page)">重试</button>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)">
        <th style="padding:10px">会员</th><th>等级</th>
        <th class="sortable" title="点击排序" @click="sortBy('points')">积分<span v-if="sortInd('points')" class="sort-ind">{{ sortInd('points') }}</span></th>
        <th class="sortable" title="点击排序" @click="sortBy('total_spent')">累计消费<span v-if="sortInd('total_spent')" class="sort-ind">{{ sortInd('total_spent') }}</span></th>
        <th>最近下单</th><th>风控</th><th style="text-align:right">操作</th>
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
          <td><span class="tag" :class="tierCls(m.tier || 0)" :style="tierStyle(m.tier || 0)">{{ TIER[m.tier || 0] }}</span></td>
          <td><b style="color:var(--plum)">{{ (m.points || 0).toLocaleString() }}</b></td>
          <td>{{ money(m.total_spent) }}</td>
          <td style="color:var(--gray)">{{ m.last_order_at ? m.last_order_at.slice(0, 10) : '—' }}</td>
          <td><span class="tag" :class="m.risk_flag === 2 ? 'tag-error' : m.risk_flag === 1 ? 'tag-pending' : 'tag-done'">
            {{ ['正常', '关注', '黑名单'][m.risk_flag || 0] }}</span></td>
          <td style="text-align:right">
            <button class="btn btn-secondary btn-sm" :class="{ loading: detailBusy }" :disabled="detailBusy" @click="openDetail(m)">{{ detailBusy ? '加载中…' : '画像' }}</button>
          </td>
        </tr>
      </tbody>
    </table>
    <EmptyState v-if="!members.length" :icon="filtered ? '🔍' : '🧍'" :title="filtered ? '未找到匹配的会员' : '暂无会员'" :sub="filtered ? '试试调整或清除筛选' : '注册用户将显示在这里'" />
    <Pagination embed :page="st.page" :pages="pages" :total="total" unit="位" @go="load" />
  </div>

  <!-- 会员画像弹窗 -->
  <div v-if="active" class="modal open" @click.self="active = null">
    <div class="modal-box" style="max-width:540px">
      <button class="modal-x" @click="active = null">×</button>
      <div class="dhead">
        <div class="dtitle">{{ active.name || active.email }}</div>
        <span class="tag" :class="tierCls(active.tier || 0)" :style="tierStyle(active.tier || 0)">{{ TIER[active.tier || 0] }}</span>
      </div>
      <div class="kv" style="margin-bottom:14px">
        <div class="kv-row"><span>邮箱</span><span class="kv-val">{{ active.email }}</span></div>
        <div class="kv-row"><span>加入时间</span><span class="kv-val">{{ (active.created_at || '').slice(0, 10) || '—' }}</span></div>
        <div class="kv-row"><span>积分</span><span class="kv-val" style="color:var(--plum);font-weight:700">{{ (active.points || 0).toLocaleString() }}</span></div>
        <div class="kv-row"><span>累计消费</span><span class="kv-val">{{ money(active.total_spent) }}</span></div>
        <div class="kv-row"><span>最近下单</span><span class="kv-val">{{ active.last_order_at ? active.last_order_at.slice(0, 10) : '—' }}</span></div>
      </div>

      <div class="field">
        <label>风控状态</label>
        <select v-model="riskDraft" class="input" @change="setRisk(parseInt(riskDraft, 10))">
          <option value="0">正常</option><option value="1">关注</option><option value="2">黑名单</option>
        </select>
        <p style="font-size:11.5px;color:var(--gray);margin-top:6px">黑名单会员下单时将被风控拦截（无法完成支付）；「关注」仅标记观察，不影响下单。</p>
      </div>

      <div style="display:flex;gap:16px;margin-top:6px;font-size:12.5px">
        <router-link :to="{ path: '/orders', query: { q: active.email } }" style="color:var(--plum)">查看订单 →</router-link>
        <router-link :to="{ path: '/tickets', query: { q: active.email } }" style="color:var(--plum)">查看工单 →</router-link>
      </div>

      <div v-if="active.ledger && active.ledger.length" style="margin-top:14px">
        <div class="dtitle" style="margin-bottom:8px">积分流水（近 {{ Math.min(10, active.ledger.length) }} 条）</div>
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

  <!-- 拉黑危险确认 -->
  <ConfirmDialog
    :open="banDlg" title="加入黑名单" danger confirm-text="确认拉黑" :busy="banBusy"
    :body="'黑名单会员「' + (active?.name || active?.email || '') + '」下单时将被风控拦截，无法完成支付；「关注」仅标记观察不影响下单。'"
    @confirm="applyRisk(2)" @close="cancelBan"
  />
</template>

<style scoped>
/* 刷新失败横幅：pale-error 底 + error 字，圆角，卡内顶部 */
.err-banner{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 14px;margin:12px 12px 0;background:var(--pale-error);color:var(--error);border-radius:10px;font-size:12.5px}
</style>
