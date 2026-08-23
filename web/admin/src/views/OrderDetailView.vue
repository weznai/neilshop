<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import { money, dt } from '../composables/format'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { OSTATUS, PAY, SHIP, RMA_REASON, ORDER_ERR, mapErr } from '../constants/trade'

const route = useRoute()
const router = useRouter()
/* 返回列表：优先回退历史（保留列表筛选 query），直链进入无历史时兜底 /orders */
function backToList() {
  if (window.history.state && window.history.state.back) router.back()
  else router.push('/orders')
}
const o = ref(null)
const err = ref('')
/* 状态映射统一走 constants/trade.js：OSTATUS 订单 / PAY 支付 / SHIP 物流包裹 / RMA_REASON 退货原因 */
const ACTOR = { system: '系统', admin: '管理员', user: '用户' }
/* 时间线事件码 → 中文（以 OrderTimeline 注释与各 service add_timeline 调用为准） */
const EVENT_LABEL = {
  checkout_created: '订单创建', payment_succeeded: '支付成功', payment_failed: '支付失败',
  status_changed: '状态变更', refund_issued: '退款', shipment_created: '发货',
  tracking_updated: '物流更新', note_added: '备注', email_sent: '邮件发送',
  ticket_linked: '关联工单', label_voided: '面单作废',
  rma_created: '退货申请', rma_label_sent: '退货标签已发送', rma_received: '退货已收货',
  rma_canceled: '退货申请已取消', rma_rejected: '退货申请已拒绝',
  exchange_created: '换货申请', exchange_approved: '换货已批准', exchange_rejected: '换货已拒绝',
  exchange_diff_paid: '换货差价已付', exchange_shipped: '换货已重发', exchange_completed: '换货完成',
  giftcard_created: '礼品卡购卡', points_granted: '积分发放',
  address_updated: '收件地址修改',
}
/* 时间线圆点语义色（支付绿 / 退款退货红 / 物流蓝 / 状态紫 / 其余 rose） */
const TL_DOT = {
  payment_succeeded: 'ok', refund_issued: 'err', payment_failed: 'err', label_voided: 'err',
  rma_created: 'err', exchange_rejected: 'err',
  shipment_created: 'info', tracking_updated: 'info', exchange_shipped: 'info',
  status_changed: 'plum', checkout_created: 'rose',
  address_updated: 'plum',
}
const dotCls = (ev) => TL_DOT[ev] || ''

/* 时间线折叠：>30 条默认只显示前 30，底部按钮展开/收起 */
const TL_LIMIT = 30
const tlOpen = ref(false)
const tlItems = computed(() => {
  const t = o.value?.timeline || []
  return t.length > TL_LIMIT && !tlOpen.value ? t.slice(0, TL_LIMIT) : t
})

/* 按订单号加载详情（初载/深链切换共用） */
async function fetchOrder(no) {
  if (!no) { err.value = '缺少订单号'; o.value = null; return }
  err.value = ''
  o.value = null
  tlOpen.value = false
  try { o.value = await req('GET', '/api/admin/trade/orders/' + encodeURIComponent(no)) }
  catch (e) { err.value = (e.status === 404 ? '订单不存在' : '加载失败 ' + (e.message || '')) }
}
onMounted(() => fetchOrder(route.query.no))
/* 深链响应：已停留在 /order-detail 时 no 变化（列表跳转另一单）重新加载 */
watch(() => route.query.no, (no) => fetchOrder(no))

/* money/dt 统一走 format.js（dt 补 Z 修时区） */
const reload = async () => { o.value = await req('GET', '/api/admin/trade/orders/' + encodeURIComponent(route.query.no)) }
async function doReload() {
  try { await reload() ; toast('已刷新', 'success') } catch (e) { toast('刷新失败：' + (e.message || ''), 'error') }
}

/* 英雄区主题：按订单状态给浅色底 + 左缘强调条 */
const HERO_THEME = { 0: 'is-pending', 1: 'is-paid', 2: 'is-paid', 3: 'is-ship', 4: 'is-ship', 5: 'is-done', 8: 'is-error', 9: 'is-error' }
/* 生命周期步进条：创建→支付→发货→送达→完成；终态(8/9)不展示步进条 */
const STEPS = ['创建', '支付', '发货', '送达', '完成']
const stepIdx = computed(() => ({ 0: 0, 1: 1, 2: 1, 3: 2, 4: 3, 5: 4 }[o.value?.status]))
const isClosed = computed(() => [8, 9].includes(o.value?.status))
/* 一键复制订单号（clipboard API 不可用时退回 execCommand） */
function copyNo() {
  const no = o.value.order_no
  const fallback = () => {
    const ta = document.createElement('textarea')
    ta.value = no; document.body.appendChild(ta); ta.select()
    try { document.execCommand('copy'); toast('订单号已复制', 'success') } catch { toast('复制失败', 'error') }
    ta.remove()
  }
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(no).then(() => toast('订单号已复制', 'success')).catch(fallback)
  else fallback()
}

/* 可退余额：后端取 status∈{1,4} 的最新一笔支付的 amount − refunded_amount（apply_refund 契约） */
const refundable = computed(() => {
  const ps = (o.value?.payments || []).filter((p) => p.status === 1 || p.status === 4)
  if (!ps.length) return 0
  const p = ps.reduce((a, b) => (b.id > a.id ? b : a))
  return Math.max(0, p.amount - p.refunded_amount)
})

/* 时间线事件正文：按事件码把 detail 翻译为友好中文 */
function eventText(t) {
  const d = t.detail || {}
  switch (t.event) {
    case 'status_changed': {
      let s = `状态 ${OSTATUS[d.from]?.label ?? d.from} → ${OSTATUS[d.to]?.label ?? d.to}`
      if (d.reason === 'timeout') s += '（超时未支付自动关闭）'
      else if (d.reason === 'user') s += '（用户取消）'
      else if (d.reason === 'admin') s += '（管理员操作）'
      else if (d.reason === 'user_cancel_paid') s += '（用户支付后取消）'
      return s
    }
    case 'refund_issued':
      return `${money(d.amount)} · ${d.full ? '全额退款' : '部分退款'}${d.reason ? ' · 原因：' + d.reason : ''}`
    case 'payment_succeeded': return `${money(d.amount)}${d.source ? ' · 渠道：' + d.source : ''}`
    case 'payment_failed': return d.reason ? `失败原因：${d.reason}` : ''
    case 'shipment_created': case 'exchange_shipped':
      return `${d.carrier || '—'} ${d.tracking_no || '—'}（包裹 ${d.shipment_no || '—'}）`
    case 'rma_created':
      return `退货单 ${d.rma_no || '—'} · x${d.qty ?? '?'} · ${RMA_REASON[d.reason] || '原因：' + (d.reason ?? '—')}`
    case 'rma_label_sent': return `退货单 ${d.rma_no || '—'} 退货标签已邮件发送`
    case 'rma_received': return `退货单 ${d.rma_no || '—'} 已收货 · 回补库存 x${d.restock_qty ?? 0}`
    case 'exchange_created':
      return `换货单 ${d.exchange_no || '—'} · 差价 ${money(d.price_diff)}${d.reason ? ' · ' + d.reason : ''}`
    case 'exchange_approved':
      return `换货单 ${d.exchange_no || '—'} → ${d.to === 2 ? '待买家付差价' : '待重发'}`
    case 'exchange_rejected':
      return `换货单 ${d.exchange_no || '—'}${d.reason ? ' · 拒绝原因：' + d.reason : ''}`
    case 'exchange_diff_paid': return `换货单 ${d.exchange_no || '—'} · 差价 ${money(d.price_diff)} 已收`
    case 'exchange_completed': return `换货单 ${d.exchange_no || '—'} 完成 · 原商品已回补库存`
    case 'giftcard_created':
      return `${money(d.amount)}${d.recipient ? ' · 赠送给 ' + d.recipient : ''}`
    case 'points_granted':
      return d.referrer_points ? `推荐奖励：邀请人 +${d.referrer_points} 分${d.invitee_points ? ' · 受邀人 +' + d.invitee_points + ' 分' : ''}` : ''
    case 'note_added': return d.text || ''
    case 'address_updated': {
      const ks = Object.keys(d.new || {})
      return ks.length ? `已更新字段：${ks.join('、')}` : ''
    }
    case 'checkout_created': {
      const parts = []
      if (d.code_discount) parts.push('折扣码 −' + money(d.code_discount))
      if (d.bundle_discount) parts.push('捆绑优惠 −' + money(d.bundle_discount))
      if (d.points_used) parts.push(`积分抵扣 ${d.points_used} 分`)
      if (d.giftcard_discount) parts.push('礼品卡 −' + money(d.giftcard_discount))
      return parts.join(' · ')
    }
    default: {
      const vals = Object.values(d).filter((v) => v !== null && v !== undefined && v !== '')
      return vals.length ? vals.join(' · ') : ''
    }
  }
}

const refundDlg = ref(false)
const refundAmt = ref(0) /* 美元数值，提交时 ×100 转分 */
const refundReason = ref('')
/* 发货弹窗（替代 prompt：可选承运商，与订单列表一致） */
const shipDlg = ref(false)
const deliverDlg = ref(false)
const carrier = ref('USPS')
const tracking = ref('')
/* 写操作提交防抖：请求期间弹窗按钮 busy+disabled，双击不会重复 POST */
const submitting = ref(false)

function act(type) {
  if (type === 'ship') {
    tracking.value = ''
    carrier.value = 'USPS'
    shipDlg.value = true
  } else if (type === 'deliver') {
    deliverDlg.value = true
  } else if (type === 'refund') {
    if (refundable.value <= 0) { toast('暂无可退余额（无成功支付或已全额退款）', 'error'); return }
    refundAmt.value = refundable.value / 100
    refundReason.value = ''
    refundDlg.value = true
  }
}
async function deliverConfirm() {
  if (submitting.value) return
  submitting.value = true
  try {
    await req('POST', `/api/admin/trade/orders/${o.value.order_no}/mark-delivered`)
    toast('已标记妥投 ✓', 'success')
    deliverDlg.value = false
    await reload()
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
  submitting.value = false
}
async function shipConfirm() {
  if (submitting.value) return
  if (!tracking.value.trim()) { toast('请填写物流单号', 'error'); return }
  submitting.value = true
  try {
    await req('POST', `/api/admin/trade/orders/${o.value.order_no}/ship`, {
      carrier: carrier.value, tracking_no: tracking.value.trim(),
    })
    toast('已发货 ✓', 'success')
    shipDlg.value = false
    await reload()
  } catch (e) { toast('发货失败：' + (e.data?.detail || e.message), 'error') }
  submitting.value = false
}
async function refundConfirm() {
  if (submitting.value) return
  /* 美元输入 → 四舍五入到分，校验 $0.01 ~ 可退余额 */
  const amt = Math.round(Number(refundAmt.value) * 100)
  if (!Number.isFinite(amt) || amt < 1 || amt > refundable.value) {
    toast(`退款金额需在 $0.01 ~ ${money(refundable.value)}（可退余额）之间`, 'error')
    return
  }
  submitting.value = true
  try {
    await req('POST', `/api/admin/trade/orders/${o.value.order_no}/refund`, {
      amount_cents: amt, reason: refundReason.value || 'ops-refund',
    })
    toast('退款已执行 ✓', 'success')
    refundDlg.value = false
    await reload()
  } catch (e) {
    let msg = e.data?.detail || e.message
    if (typeof msg === 'string' && msg.startsWith('invalid_refund_amount:')) {
      msg = `退款金额超出可退余额（剩余 ${money(Number(msg.split(':')[1]))}）`
    } else {
      msg = mapErr(msg, ORDER_ERR) || msg
    }
    toast('退款失败：' + msg, 'error')
  }
  submitting.value = false
}

/* 取消订单：仅 status=0 可取消，409 时转后端语义文案 */
const cancelDlg = ref(false)
async function cancelConfirm() {
  if (submitting.value) return
  submitting.value = true
  try {
    await req('POST', `/api/admin/trade/orders/${o.value.order_no}/cancel`)
    toast('已取消', 'success')
    cancelDlg.value = false
    await reload()
  } catch (e) {
    toast(mapErr(e.data?.detail, ORDER_ERR) || (e.status === 409 ? '仅待支付订单可取消' : '取消失败：' + (e.data?.detail || e.message)), 'error')
  }
  submitting.value = false
}

/* 添加备注：POST /note 落时间线 note_added，reload 后由时间线渲染正文 */
const noteDlg = ref(false)
const noteText = ref('')
function openNote() { noteText.value = ''; noteDlg.value = true }
async function noteConfirm() {
  if (submitting.value) return
  const text = noteText.value.trim()
  if (!text) { toast('请填写备注内容', 'error'); return }
  submitting.value = true
  try {
    await req('POST', `/api/admin/trade/orders/${o.value.order_no}/note`, { text })
    toast('备注已添加', 'success')
    noteDlg.value = false
    await reload()
  } catch (e) { toast('添加失败：' + (e.data?.detail || e.message), 'error') }
  submitting.value = false
}

/* ===== 开始备货（status=1→2）：CAS 防并发重复备货，409 not_prepable:{status} ===== */
const prepareDlg = ref(false)
async function prepareConfirm() {
  if (submitting.value) return
  submitting.value = true
  try {
    await req('POST', `/api/admin/trade/orders/${o.value.order_no}/prepare`)
    toast('已开始备货，订单进入「备货中」✓', 'success')
    prepareDlg.value = false
    await reload()
  } catch (e) {
    toast('操作失败：' + (mapErr(e.data?.detail, ORDER_ERR) || e.data?.detail || e.message), 'error')
  }
  submitting.value = false
}

/* ===== 代确认完成（status=4→5）：替代客户 confirm_received，完成时解冻积分 ===== */
const doneDlg = ref(false)
async function doneConfirm() {
  if (submitting.value) return
  submitting.value = true
  try {
    await req('POST', `/api/admin/trade/orders/${o.value.order_no}/mark-completed`)
    toast('订单已完成，冻结积分已解冻发放 ✓', 'success')
    doneDlg.value = false
    await reload()
  } catch (e) {
    toast('操作失败：' + (mapErr(e.data?.detail, ORDER_ERR) || e.data?.detail || e.message), 'error')
  }
  submitting.value = false
}

/* ===== 修改收件地址（status≤2 可改，全字段可选覆盖）：手写 modal 回填现值 ===== */
const addrDlg = ref(false)
const ADDR_FIELDS = ['full_name', 'line1', 'line2', 'city', 'state', 'zip', 'country', 'phone']
const addrForm = reactive({})
function openAddr() {
  const a = o.value?.shipping_address || {}
  for (const k of ADDR_FIELDS) addrForm[k] = a[k] != null ? String(a[k]) : ''
  addrDlg.value = true
}
async function addrConfirm() {
  if (submitting.value) return
  if (addrForm.country && addrForm.country.trim().length !== 2) {
    toast('国家代码需为 2 位字母（如 US / CN）', 'error'); return
  }
  submitting.value = true
  try {
    /* 仅提交非空字段（后端按字段增量覆盖；line2 可传空串清空） */
    const body = {}
    for (const k of ADDR_FIELDS) {
      const v = addrForm[k].trim()
      if (v || (k === 'line2' && o.value.shipping_address?.line2)) body[k] = v
    }
    const r = await req('PUT', `/api/admin/trade/orders/${o.value.order_no}/address`, body)
    o.value.shipping_address = r.shipping_address
    toast('收件地址已更新 ✓', 'success')
    addrDlg.value = false
    await reload()
  } catch (e) {
    toast('保存失败：' + (mapErr(e.data?.detail, ORDER_ERR) || e.data?.detail || e.message), 'error')
  }
  submitting.value = false
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="od-h1">订单详情</h1>
      <span class="od-sub">{{ route.query.no }}</span>
    </div>
    <div class="od-actions">
      <button class="btn btn-secondary btn-sm" :disabled="!o" @click="doReload">⟳ 刷新</button>
      <button class="btn btn-secondary btn-sm" @click="backToList">← 返回列表</button>
    </div>
  </div>

  <div v-if="err" class="card" style="padding:32px;text-align:center;color:var(--gray)">{{ err }}</div>
  <div v-else-if="!o" class="card skeleton" style="min-height:240px" />

  <template v-else>
    <!-- 状态英雄区：订单号 + 状态 + 总额 + 生命周期步进 + 操作 -->
    <div class="hero" :class="HERO_THEME[o.status] || ''">
      <div class="hero-top">
        <div class="hero-left">
          <button class="hero-no" title="点击复制订单号" @click="copyNo">
            <b>{{ o.order_no }}</b><i>⧉</i>
          </button>
          <span class="tag hero-tag" :class="OSTATUS[o.status]?.cls || 'tag-error'">{{ OSTATUS[o.status]?.label ?? o.status }}</span>
        </div>
        <div class="hero-amount">
          <span>订单总计</span>
          <b>{{ money(o.grand_total) }}</b>
        </div>
      </div>

      <div v-if="!isClosed" class="steps">
        <div v-for="(s, i) in STEPS" :key="s" class="step" :class="{ done: i < stepIdx, now: i === stepIdx }">
          <i class="dot">{{ i < stepIdx ? '✓' : i + 1 }}</i><span>{{ s }}</span>
        </div>
      </div>
      <div v-else class="closed-banner">
        {{ OSTATUS[o.status]?.label }} · {{ o.status === 9 ? '本单已全额退款' : '本单已取消，无可用操作' }}
      </div>

      <div class="hero-meta">
        <span>下单 <b>{{ dt(o.placed_at) || '—' }}</b></span>
        <span>支付 <b>{{ dt(o.paid_at) || '—' }}</b></span>
        <span v-if="o.shipped_at">发货 <b>{{ dt(o.shipped_at) }}</b></span>
        <span v-if="o.delivered_at">送达 <b>{{ dt(o.delivered_at) }}</b></span>
        <span v-if="o.tracking_no">物流 <b>{{ o.tracking_no }}</b></span>
      </div>

      <div class="hero-ops">
        <button v-if="o.status === 1 || o.status === 2" class="btn btn-primary btn-sm" @click="act('ship')">📦 发货</button>
        <button v-if="o.status === 1" class="btn btn-secondary btn-sm" @click="prepareDlg = true">🧰 开始备货</button>
        <button v-if="o.status === 3" class="btn btn-secondary btn-sm" @click="act('deliver')">✅ 标记妥投</button>
        <button v-if="o.status === 4" class="btn btn-secondary btn-sm" @click="doneDlg = true">✅ 代确认完成</button>
        <button v-if="o.status <= 2" class="btn btn-secondary btn-sm" @click="openAddr">✏️ 修改地址</button>
        <button v-if="[1, 2, 3, 4, 5].includes(o.status)" class="btn btn-ghost btn-sm hero-danger" @click="act('refund')">💸 退款（余额 {{ money(refundable) }}）</button>
        <button v-if="o.status === 0" class="btn btn-ghost btn-sm hero-danger" @click="cancelDlg = true">✕ 取消订单</button>
      </div>
    </div>

    <!-- 主栏 1.6fr / 侧栏 1fr：商品（交易主数据）在左，客户信息在右 -->
    <div class="od-grid">
      <div class="card od-card" style="padding:20px">
        <div class="dhead">
          <h3 class="dtitle">商品明细</h3>
          <span class="item-cnt" v-if="(o.items || []).length">{{ o.items.length }} 项</span>
        </div>
        <div class="oi-wrap">
          <div class="oi-list">
            <div v-for="(it, i) in o.items || []" :key="i" class="oitem">
              <div class="oitem-main">
                <b class="oitem-title">{{ it.title }}</b>
                <div class="oitem-meta">
                  <span class="qtypill">x{{ it.qty }}</span>
                  <span>单价 {{ money(it.unit_price) }}</span>
                  <span v-if="it.refunded_qty" class="refpill">已退 {{ it.refunded_qty }}</span>
                </div>
              </div>
              <b class="oitem-sub">{{ money(it.subtotal) }}</b>
            </div>
            <div v-if="!(o.items || []).length" class="empty-line">📭 此订单暂无商品</div>
            <!-- 折扣码核销并入商品卡（同属交易明细） -->
            <div v-if="o.redemptions && o.redemptions.length" class="redem">
              <div class="redem-title">🎟 折扣码核销</div>
              <div v-for="(r, i) in o.redemptions" :key="i" class="redem-row">
                <span>#{{ r.code_id }}<i class="kv-sub"> · {{ r.email }}</i></span>
                <b>−{{ money(r.discount_amount) }}</b>
              </div>
            </div>
          </div>
          <!-- 发票式汇总：右侧竖栏，虚线分隔 -->
          <div class="sum">
            <div class="sum-row"><span>小计</span><span>{{ money(o.subtotal) }}</span></div>
            <div v-if="o.discount_total" class="sum-row disc"><span>折扣</span><span>−{{ money(o.discount_total) }}</span></div>
            <div v-if="o.points_discount" class="sum-row disc"><span>积分抵扣</span><span>−{{ money(o.points_discount) }}</span></div>
            <div v-if="o.giftcard_discount" class="sum-row disc"><span>礼品卡抵扣</span><span>−{{ money(o.giftcard_discount) }}</span></div>
            <div class="sum-row"><span>运费</span><span>{{ money(o.shipping_fee) }}</span></div>
            <div class="sum-row"><span>税费</span><span>{{ money(o.tax) }}</span></div>
            <div class="sum-total"><span>总计</span><b>{{ money(o.grand_total) }}</b></div>
          </div>
        </div>
      </div>

      <!-- 侧栏：基本信息 + 收件地址 + 客户留言 合并为一张高卡，与左栏等高平衡 -->
      <div class="card od-card" style="padding:20px;animation-delay:.06s">
        <div class="dhead"><h3 class="dtitle">订单信息</h3></div>
        <div class="kv">
          <div class="kv-row"><span>客户</span><b class="kv-val">{{ o.email }}</b></div>
          <div class="kv-row"><span>下单</span><span class="kv-val">{{ dt(o.placed_at) || '—' }}</span></div>
          <div class="kv-row"><span>支付</span><span class="kv-val">{{ dt(o.paid_at) || '—' }}</span></div>
          <div v-if="o.shipped_at" class="kv-row"><span>发货</span><span class="kv-val">{{ dt(o.shipped_at) }}</span></div>
          <div v-if="o.delivered_at" class="kv-row"><span>送达</span><span class="kv-val">{{ dt(o.delivered_at) }}</span></div>
          <div class="kv-row"><span>物流单号</span><span class="kv-val">{{ o.tracking_no || '—' }}</span></div>
          <div class="kv-row"><span>积分</span><span class="kv-val">+{{ o.points_earned ?? 0 }} 得 / −{{ o.points_used ?? 0 }} 用</span></div>
        </div>
        <div class="addr-sec">
          <div class="sec-lb">📍 收件地址</div>
          <div v-if="o.shipping_address" class="addr">
            <b>{{ o.shipping_address?.full_name }}</b>
            <p>{{ o.shipping_address?.line1 }} {{ o.shipping_address?.line2 }}</p>
            <p>{{ o.shipping_address?.city }}, {{ o.shipping_address?.state }} {{ o.shipping_address?.zip }} · {{ o.shipping_address?.country }}</p>
          </div>
          <div v-else class="empty-line">📭 暂无收件地址</div>
        </div>
        <!-- 客户留言（下单时提交，浅底强调） -->
        <div v-if="o.note" class="note-box">
          <div class="note-lb">💬 客户留言</div>
          <div class="note-txt">{{ o.note }}</div>
        </div>
      </div>
    </div>

    <!-- 支付 / 物流：两张矮卡并排一行，消除竖向碎片空白 -->
    <div class="duo">
      <div class="card od-card" style="padding:20px;animation-delay:.1s">
        <div class="dhead"><h3 class="dtitle">支付信息</h3></div>
        <div v-for="p in o.payments || []" :key="p.id" class="pay-row">
          <div class="pay-main">
            <b>{{ money(p.amount) }}</b>
            <div class="pay-meta">
              尾号 {{ (p.payment_intent || '').slice(-8) || '—' }}<span v-if="p.refunded_amount"> · 已退 {{ money(p.refunded_amount) }}</span>
            </div>
          </div>
          <span class="tag" :class="PAY[p.status]?.cls">{{ PAY[p.status]?.label ?? p.status }}</span>
        </div>
        <div v-if="!(o.payments || []).length" class="empty-line">📭 暂无支付记录</div>
        <div v-else class="ref-box" :class="{ on: refundable > 0 }">
          <span>可退余额（最新可退支付）</span>
          <b>{{ money(refundable) }}</b>
        </div>
      </div>

      <div class="card od-card" style="padding:20px;animation-delay:.14s">
        <div class="dhead"><h3 class="dtitle">物流包裹</h3></div>
        <div v-for="s in o.shipments || []" :key="s.shipment_no" class="pay-row">
          <div class="pay-main">
            <b>{{ s.shipment_no }}</b> · {{ s.carrier || '—' }}
            <div class="pay-meta">
              {{ s.tracking_no || '无单号' }} · 发货 {{ dt(s.shipped_at) || '—' }}<span v-if="s.delivered_at"> · 送达 {{ dt(s.delivered_at) }}</span>
            </div>
          </div>
          <span class="tag" :class="SHIP[s.status]?.cls">{{ SHIP[s.status]?.label ?? s.status }}</span>
        </div>
        <div v-if="!(o.shipments || []).length" class="empty-line">📭 暂无物流包裹</div>
      </div>
    </div>

    <!-- 时间线：底部通栏（日志式行填充整行宽度，不再撑高左栏） -->
    <div class="card od-card" style="padding:20px;animation-delay:.18s">
      <div class="dhead">
        <h3 class="dtitle">时间线</h3>
        <div style="display:flex;align-items:center;gap:10px">
          <span v-if="(o.timeline || []).length" class="item-cnt">{{ o.timeline.length }} 条</span>
          <button class="btn btn-secondary btn-sm" @click="openNote">＋ 添加备注</button>
        </div>
      </div>
      <div class="tl">
        <div v-for="(t, i) in tlItems" :key="i" class="tl-item">
          <i class="tl-dot" :class="dotCls(t.event)"></i>
          <div class="tl-head">
            <b>{{ EVENT_LABEL[t.event] || t.event }}</b>
            <span class="tl-actor">{{ ACTOR[t.actor] || t.actor }}</span>
            <span class="tl-time">{{ dt(t.created_at) }}</span>
          </div>
          <div v-if="eventText(t)" class="tl-text">{{ eventText(t) }}</div>
        </div>
      </div>
      <button v-if="(o.timeline || []).length > TL_LIMIT" class="tl-more" @click="tlOpen = !tlOpen">{{ tlOpen ? '收起' : `展开全部 (${o.timeline.length})` }}</button>
      <div v-if="!(o.timeline || []).length" class="empty-line">📭 暂无时间线记录</div>
    </div>
  </template>

  <!-- 发货弹窗：提交中遮罩与 ✕ 不可关闭 -->
  <div v-if="shipDlg" class="modal open" @click.self="!submitting && (shipDlg = false)">
    <div class="modal-box" style="max-width:420px">
      <button class="modal-x" @click="!submitting && (shipDlg = false)">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">📦 发货 {{ o.order_no }}</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:14px">发货后扣库存并向客户发送物流邮件。</p>
      <div class="field">
        <label>承运商</label>
        <select v-model="carrier" class="input">
          <option>USPS</option><option>UPS</option><option>FedEx</option><option>DHL</option>
        </select>
      </div>
      <div class="field">
        <label>物流单号</label>
        <input v-model="tracking" class="input" placeholder="9400…">
      </div>
      <button class="btn btn-primary btn-block" style="margin-top:12px" :disabled="submitting" @click="shipConfirm">{{ submitting ? '发货中…' : '确认发货' }}</button>
    </div>
  </div>

  <!-- 妥投确认弹窗 -->
  <ConfirmDialog
    :open="deliverDlg"
    title="标记妥投"
    :body="`确认标记 ${o?.order_no} 已妥投？`"
    confirm-text="确认妥投"
    :busy="submitting"
    @confirm="deliverConfirm"
    @close="deliverDlg = false"
  />

  <!-- 取消订单确认弹窗 -->
  <ConfirmDialog
    :open="cancelDlg"
    title="取消订单"
    body="仅待支付订单可取消，取消后不可恢复，库存/积分/礼品卡抵扣将回补。"
    confirm-text="确认取消"
    danger
    :busy="submitting"
    @confirm="cancelConfirm"
    @close="cancelDlg = false"
  />

  <!-- 退款弹窗：提交中遮罩与 ✕ 不可关闭 -->
  <div v-if="refundDlg" class="modal open" @click.self="!submitting && (refundDlg = false)">
    <div class="modal-box" style="max-width:420px">
      <button class="modal-x" @click="!submitting && (refundDlg = false)">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">💸 退款 {{ o.order_no }}</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:14px">
        订单总额 {{ money(o.grand_total) }} · 可退余额 <b style="color:var(--plum)">{{ money(refundable) }}</b>
        （按最新可退支付计算）。全额退款将回补库存、作废本单积分并恢复礼品卡抵扣。
      </p>
      <div class="field">
        <label>退款金额（美元）</label>
        <input v-model.number="refundAmt" class="input" type="number" step="0.01" min="0.01" :max="refundable / 100">
      </div>
      <div class="field"><label>原因</label><input v-model="refundReason" class="input" placeholder="ops-refund"></div>
      <button class="btn btn-primary btn-block" style="margin-top:12px" :disabled="submitting" @click="refundConfirm">{{ submitting ? '退款中…' : '确认退款' }}</button>
    </div>
  </div>

  <!-- 添加备注弹窗 -->
  <div v-if="noteDlg" class="modal open" @click.self="!submitting && (noteDlg = false)">
    <div class="modal-box" style="max-width:420px">
      <button class="modal-x" @click="!submitting && (noteDlg = false)">×</button>
      <div class="dhead" style="margin-bottom:10px"><h3 class="dtitle">添加订单备注</h3></div>
      <div class="field">
        <label>备注内容 <span style="float:right;color:var(--gray);font-weight:400">{{ noteText.length }}/500</span></label>
        <textarea v-model="noteText" class="input" rows="3" maxlength="500" style="height:auto;min-height:78px;padding:10px 14px;resize:vertical;font-family:inherit" placeholder="记录客服沟通、异常原因等（仅内部可见）"></textarea>
      </div>
      <div style="display:flex;justify-content:space-between;gap:10px;margin-top:12px">
        <button class="btn btn-secondary" :disabled="submitting" @click="noteDlg = false">取消</button>
        <button class="btn btn-primary" :disabled="submitting" @click="noteConfirm">{{ submitting ? '提交中…' : '确认添加' }}</button>
      </div>
    </div>
  </div>

  <!-- 开始备货确认（1→2，CAS 防并发） -->
  <ConfirmDialog
    :open="prepareDlg"
    title="开始备货"
    :body="`确认将 ${o?.order_no} 转入备货？订单状态将变为「备货中」，期间仍可正常发货。`"
    confirm-text="确认备货"
    :busy="submitting"
    @confirm="prepareConfirm"
    @close="prepareDlg = false"
  />

  <!-- 代确认完成（4→5，解冻积分） -->
  <ConfirmDialog
    :open="doneDlg"
    title="代确认完成"
    :body="`确认代替客户完成 ${o?.order_no}？本单冻结积分将解冻发放，订单进入终态「已完成」，此后不可再发货/退款。`"
    confirm-text="确认完成"
    :busy="submitting"
    @confirm="doneConfirm"
    @close="doneDlg = false"
  />

  <!-- 修改收件地址弹窗：回填现值，全字段可编辑（status≤2 可改；发货后 409） -->
  <div v-if="addrDlg" class="modal open" @click.self="!submitting && (addrDlg = false)">
    <div class="modal-box" style="max-width:520px">
      <button class="modal-x" @click="!submitting && (addrDlg = false)">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">✏️ 修改收件地址 · {{ o.order_no }}</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:14px">仅未发货订单可修改；留空的字段保持原值不变。</p>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px 12px">
        <div class="field" style="grid-column:1 / -1"><label>收件人</label><input v-model="addrForm.full_name" class="input" placeholder="Full name"></div>
        <div class="field" style="grid-column:1 / -1"><label>地址行 1</label><input v-model="addrForm.line1" class="input" placeholder="Street address"></div>
        <div class="field" style="grid-column:1 / -1"><label>地址行 2（选填）</label><input v-model="addrForm.line2" class="input" placeholder="Apt / Suite"></div>
        <div class="field"><label>城市</label><input v-model="addrForm.city" class="input" placeholder="City"></div>
        <div class="field"><label>州 / 省</label><input v-model="addrForm.state" class="input" placeholder="State"></div>
        <div class="field"><label>邮编</label><input v-model="addrForm.zip" class="input" placeholder="ZIP"></div>
        <div class="field"><label>国家（2 位码）</label><input v-model="addrForm.country" class="input" placeholder="US" maxlength="2" style="text-transform:uppercase"></div>
        <div class="field" style="grid-column:1 / -1"><label>电话（选填）</label><input v-model="addrForm.phone" class="input" placeholder="Phone"></div>
      </div>
      <div style="display:flex;justify-content:space-between;gap:10px;margin-top:12px">
        <button class="btn btn-secondary" :disabled="submitting" @click="addrDlg = false">取消</button>
        <button class="btn btn-primary" :class="{ loading: submitting }" :disabled="submitting" @click="addrConfirm">{{ submitting ? '保存中…' : '保存地址' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ===== 顶栏 ===== */
.od-h1{font-family:var(--font-title);font-size:22px;font-weight:700;letter-spacing:-.3px}
.od-sub{font-size:12.5px;color:var(--gray)}
.od-actions{display:flex;gap:8px;align-items:center}

/* ===== 状态英雄区 ===== */
.hero{--tint:#fff;position:relative;overflow:hidden;border-radius:14px;padding:20px 22px;border:1px solid var(--gray-light);
  background:linear-gradient(135deg,var(--tint),#fff 62%);box-shadow:var(--shadow-card);animation:odRise .45s ease-out backwards}
.hero::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:linear-gradient(180deg,var(--rose),var(--plum))}
.hero::after{content:"";position:absolute;top:-36px;right:-30px;width:170px;height:140px;border-radius:50%;
  background:radial-gradient(closest-side,rgba(232,180,184,.2),transparent);pointer-events:none}
.hero.is-pending{--tint:var(--pale-warn)}
.hero.is-paid{--tint:var(--pale-success)}
.hero.is-ship{--tint:var(--pale-info)}
.hero.is-done{--tint:var(--gray-light)}
.hero.is-error{--tint:var(--pale-error)}
.hero-top{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap}
.hero-left{display:flex;align-items:center;gap:12px;flex-wrap:wrap;min-width:0}
.hero-no{display:inline-flex;align-items:center;gap:8px;background:none;border:none;cursor:pointer;padding:0;
  font-family:var(--font-title);font-size:20px;font-weight:700;color:var(--ink);letter-spacing:-.2px;transition:color .15s}
.hero-no:hover{color:var(--plum)}
.hero-no i{font-style:normal;font-size:13px;color:var(--gray);opacity:0;transform:translateX(-3px);transition:opacity .15s,transform .15s}
.hero-no:hover i{opacity:1;transform:none}
.hero-tag{font-size:13px;padding:5px 14px}
.hero-amount{text-align:right;flex:none}
.hero-amount span{display:block;font-size:11px;color:var(--gray);letter-spacing:1px}
.hero-amount b{font-size:24px;font-weight:800;color:var(--plum);font-variant-numeric:tabular-nums;letter-spacing:-.3px}
/* 生命周期步进条 */
.steps{display:flex;gap:0;margin:18px 2px 4px;flex-wrap:wrap}
.step{flex:1;display:flex;align-items:center;gap:8px;min-width:110px;position:relative}
.step .dot{width:26px;height:26px;border-radius:50%;background:#fff;border:2px solid var(--gray-light);color:var(--gray);
  font-style:normal;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center;flex:none;transition:all .3s}
.step span{font-size:12px;color:var(--gray);font-weight:600;white-space:nowrap}
.step:not(:last-child)::after{content:"";flex:1;height:2px;background:var(--gray-light);margin:0 10px;border-radius:1px;transition:background .3s}
.step.done .dot{background:var(--success);border-color:var(--success);color:#fff}
.step.done:not(:last-child)::after{background:var(--success)}
.step.now .dot{background:var(--plum);border-color:var(--plum);color:#fff;box-shadow:0 0 0 4px rgba(138,74,99,.14)}
.step.now span{color:var(--plum)}
/* 终态（取消/退款）横幅 */
.closed-banner{margin-top:16px;padding:10px 14px;border-radius:10px;background:rgba(229,72,77,.08);
  border:1px dashed rgba(229,72,77,.35);color:var(--error);font-size:13px;font-weight:600}
/* 关键节点 chips */
.hero-meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.hero-meta span{font-size:12px;color:var(--gray);background:rgba(255,255,255,.75);border:1px solid var(--gray-light);border-radius:999px;padding:3px 11px;white-space:nowrap}
.hero-meta b{color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums}
/* 操作按钮区 */
.hero-ops{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
.hero-danger{color:var(--error)}
.hero-danger:hover{background:var(--pale-error)}

/* ===== 页面骨架：主栏 1.6fr / 侧栏 1fr，支付物流并排，时间线通栏 ===== */
.od-grid{display:grid;grid-template-columns:1.6fr 1fr;gap:16px;align-items:start;margin-top:16px}
.duo{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px;align-items:start}

/* ===== 商品明细：条目列表 + 发票式汇总并排 ===== */
.oi-wrap{display:grid;grid-template-columns:1fr 232px;gap:0 22px;align-items:start}
.oi-list{min-width:0}
.oitem{display:flex;gap:12px;align-items:center;padding:11px 0;border-bottom:1px dashed var(--gray-light);font-size:13px}
.oitem:last-of-type{border-bottom:none}
.oitem-main{flex:1;min-width:0}
.oitem-title{display:block;font-size:13.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.oitem-meta{display:flex;align-items:center;gap:8px;color:var(--gray);font-size:12px;margin-top:4px;flex-wrap:wrap}
.qtypill{background:var(--rose-pale);color:var(--plum);border-radius:6px;padding:0 7px;font-weight:700}
.refpill{background:var(--pale-error);color:var(--error);border-radius:6px;padding:0 7px;font-weight:700}
.oitem-sub{flex:none;font-variant-numeric:tabular-nums}
/* 折扣码核销（并入商品卡） */
.redem{margin-top:12px;padding-top:10px;border-top:1px dashed var(--gray-light)}
.redem-title{font-size:11px;font-weight:700;letter-spacing:1px;color:var(--gray);margin-bottom:4px}
.redem-row{display:flex;justify-content:space-between;gap:10px;font-size:12.5px;padding:4px 0}
.redem-row b{color:var(--success);font-variant-numeric:tabular-nums}
/* 汇总竖栏：虚线分隔的发票式小票 */
.sum{display:grid;gap:7px;font-size:13px;border-left:1px dashed var(--gray-light);padding-left:20px;align-content:start}
.sum-row{display:flex;justify-content:space-between;color:var(--ink)}
.sum-row span+span{font-variant-numeric:tabular-nums}
.sum-row.disc{color:var(--success)}
.sum-total{display:flex;justify-content:space-between;align-items:center;background:var(--rose-pale);border-radius:10px;
  padding:10px 14px;margin-top:6px;font-weight:700;font-size:13px}
.sum-total b{color:var(--plum);font-size:17px;font-weight:800;font-variant-numeric:tabular-nums}

/* ===== 时间线（竖向圆点连线，底部通栏） ===== */
.tl{position:relative;padding-left:20px}
.tl::before{content:"";position:absolute;left:5px;top:6px;bottom:10px;width:2px;background:var(--gray-light);border-radius:1px}
.tl-item{position:relative;padding-bottom:16px}
.tl-item:last-child{padding-bottom:4px}
.tl-dot{position:absolute;left:-20px;top:4px;width:12px;height:12px;border-radius:50%;background:var(--rose);
  border:2.5px solid #fff;box-shadow:0 0 0 1.5px var(--rose-light)}
.tl-dot.ok{background:var(--success);box-shadow:0 0 0 1.5px var(--pale-success)}
.tl-dot.err{background:var(--error);box-shadow:0 0 0 1.5px var(--pale-error)}
.tl-dot.info{background:var(--info);box-shadow:0 0 0 1.5px var(--pale-info)}
.tl-dot.plum{background:var(--plum);box-shadow:0 0 0 1.5px var(--rose-light)}
.tl-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:13px}
.tl-head b{font-size:13.5px}
.tl-actor{font-size:10.5px;font-weight:700;color:var(--gray);background:var(--gray-light);border-radius:999px;padding:1px 8px}
.tl-time{font-size:11.5px;color:var(--gray);margin-left:auto;font-variant-numeric:tabular-nums;white-space:nowrap}
.tl-text{color:var(--gray);font-size:12.5px;margin-top:3px;line-height:1.6}
/* 展开/收起全部（>30 条折叠） */
.tl-more{background:none;border:none;cursor:pointer;padding:2px 0;font-size:12.5px;font-weight:600;color:var(--plum)}
.tl-more:hover{text-decoration:underline}

/* ===== 键值行（.kv/.kv-row/.kv-val 已全局化） ===== */
.kv-sub{font-style:normal;color:var(--gray);font-size:12px}

/* ===== 客户留言 ===== */
.note-box{margin-top:12px;background:var(--rose-pale);border-left:3px solid var(--rose);border-radius:10px;padding:10px 13px}
.note-lb{font-size:11px;color:var(--gray);letter-spacing:1px;margin-bottom:3px}
.note-txt{font-size:13px;color:var(--plum);line-height:1.6;white-space:pre-wrap}

/* ===== 支付 / 物流行 ===== */
.pay-row{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 0;border-bottom:1px dashed var(--gray-light);font-size:13px}
.pay-row:last-of-type{border-bottom:none}
.pay-main{min-width:0}
.pay-meta{color:var(--gray);font-size:12px;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* 可退余额提示条 */
.ref-box{display:flex;justify-content:space-between;align-items:center;margin-top:10px;padding:9px 13px;border-radius:10px;
  background:var(--gray-light);font-size:12.5px;color:var(--gray)}
.ref-box b{font-variant-numeric:tabular-nums}
.ref-box.on{background:var(--rose-pale);color:var(--plum)}

/* ===== 收件地址（侧栏内小节） ===== */
.addr-sec{margin-top:12px;padding-top:12px;border-top:1px dashed var(--gray-light)}
.sec-lb{font-size:11px;font-weight:700;letter-spacing:1px;color:var(--gray);margin-bottom:6px}
.addr{font-size:13px;line-height:1.8}
.addr b{font-size:13.5px}
.addr p{color:var(--gray)}

/* ===== 入场动画 ===== */
.od-card{animation:odRise .45s ease-out backwards}
@keyframes odRise{from{opacity:0;transform:translateY(10px)}}

/* ===== 响应式：窄屏逐级塌缩 ===== */
@media (max-width:1080px){
  .od-grid{grid-template-columns:1fr}
}
@media (max-width:768px){
  .hero{padding:16px}
  .hero-amount{text-align:left}
  .hero-ops .btn{flex:1}
  .duo{grid-template-columns:1fr}
  .oi-wrap{grid-template-columns:1fr}
  .sum{border-left:none;padding-left:0;border-top:1px dashed var(--gray-light);padding-top:14px}
  .tl-time{margin-left:0;width:100%;flex-basis:100%}
}
</style>
