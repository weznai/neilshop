<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { toast } from '../composables/toast'

const route = useRoute()
const router = useRouter()
/* 返回列表：优先回退历史（保留列表筛选 query），直链进入无历史时兜底 /orders */
function backToList() {
  if (window.history.state && window.history.state.back) router.back()
  else router.push('/orders')
}
const o = ref(null)
const err = ref('')
/* OrderStatus 真值：0待付 1已付 2履约中 3已发货 4已送达 5已完成 8已取消 9已退款(全额) */
const OSTATUS = {
  0: ['待支付', 'tag-pending'], 1: ['已支付', 'tag-paid'], 2: ['备货中', 'tag-pending'],
  3: ['已发货', 'tag-ship'], 4: ['已送达', 'tag-ship'], 5: ['已完成', 'tag-done'],
  8: ['已取消', 'tag-error'], 9: ['已退款', 'tag-error'],
}
/* PaymentStatus：0待支付 1成功 2失败 3已退款 4部分退款 */
const PSTATUS = {
  0: ['待支付', 'tag-pending'], 1: ['支付成功', 'tag-paid'], 2: ['支付失败', 'tag-error'],
  3: ['已退款', 'tag-done'], 4: ['部分退款', 'tag-ship'],
}
/* ShipmentStatus：0待打单 1已打单待拣货 2待交接 3运输中 4送达 5异常 6面单作废 */
const SHSTATUS = {
  0: ['待打单', 'tag-pending'], 1: ['已打单待拣货', 'tag-pending'], 2: ['待交接', 'tag-pending'],
  3: ['运输中', 'tag-ship'], 4: ['已送达', 'tag-done'], 5: ['异常', 'tag-error'], 6: ['面单作废', 'tag-error'],
}
/* RmaReason：1尺码不合 2质量 3不喜欢 4损坏 5发错货 6其他 */
const RMA_REASON = { 1: '尺码不合', 2: '质量问题', 3: '不喜欢', 4: '损坏', 5: '发错货', 6: '其他' }
const ACTOR = { system: '系统', admin: '管理员', user: '用户' }
/* 时间线事件码 → 中文（以 OrderTimeline 注释与各 service add_timeline 调用为准） */
const EVENT_LABEL = {
  checkout_created: '订单创建', payment_succeeded: '支付成功', payment_failed: '支付失败',
  status_changed: '状态变更', refund_issued: '退款', shipment_created: '发货',
  tracking_updated: '物流更新', note_added: '备注', email_sent: '邮件发送',
  ticket_linked: '关联工单', label_voided: '面单作废',
  rma_created: '退货申请', rma_label_sent: '退货标签已发送', rma_received: '退货已收货',
  exchange_created: '换货申请', exchange_approved: '换货已批准', exchange_rejected: '换货已拒绝',
  exchange_diff_paid: '换货差价已付', exchange_shipped: '换货已重发', exchange_completed: '换货完成',
  giftcard_created: '礼品卡购卡', points_granted: '积分发放',
}

onMounted(async () => {
  const no = route.query.no
  if (!no) { err.value = '缺少订单号'; return }
  try { o.value = await req('GET', '/api/admin/trade/orders/' + encodeURIComponent(no)) }
  catch (e) { err.value = (e.status === 404 ? '订单不存在' : '加载失败 ' + (e.message || '')) }
})

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
const dt = (iso) => (iso || '').replace('T', ' ').slice(0, 16)
const reload = async () => { o.value = await req('GET', '/api/admin/trade/orders/' + encodeURIComponent(route.query.no)) }

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
      let s = `状态 ${OSTATUS[d.from]?.[0] ?? d.from} → ${OSTATUS[d.to]?.[0] ?? d.to}`
      if (d.reason === 'timeout') s += '（超时未支付自动关闭）'
      else if (d.reason === 'user') s += '（用户取消）'
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
const refundAmt = ref(0)
const refundReason = ref('')
/* 发货弹窗（替代 prompt：可选承运商，与订单列表一致） */
const shipDlg = ref(false)
const carrier = ref('USPS')
const tracking = ref('')

async function act(type) {
  const no = o.value.order_no
  try {
    if (type === 'ship') {
      tracking.value = ''
      carrier.value = 'USPS'
      shipDlg.value = true
      return
    } else if (type === 'deliver') {
      if (!confirm(`标记 ${no} 已妥投？`)) return
      await req('POST', `/api/admin/trade/orders/${no}/mark-delivered`)
    } else if (type === 'refund') {
      if (refundable.value <= 0) { toast('暂无可退余额（无成功支付或已全额退款）', 'error'); return }
      refundAmt.value = refundable.value
      refundReason.value = ''
      refundDlg.value = true
      return
    }
    toast('操作成功 ✓', 'success')
    await reload()
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}
async function shipConfirm() {
  if (!tracking.value.trim()) { toast('请填写物流单号', 'error'); return }
  try {
    await req('POST', `/api/admin/trade/orders/${o.value.order_no}/ship`, {
      carrier: carrier.value, tracking_no: tracking.value.trim(),
    })
    toast('已发货 ✓', 'success')
    shipDlg.value = false
    await reload()
  } catch (e) { toast('发货失败：' + (e.data?.detail || e.message), 'error') }
}
async function refundConfirm() {
  const amt = Math.round(Number(refundAmt.value))
  if (!amt || amt <= 0 || amt > refundable.value) {
    toast(`退款金额需在 $0.01 ~ ${money(refundable.value)}（可退余额）之间`, 'error')
    return
  }
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
      msg = `金额超出可退余额（剩余 ${money(Number(msg.split(':')[1]))}）`
    } else if (msg === 'no_refundable_payment') msg = '无成功支付记录可退款'
    else if (msg === 'already_fully_refunded') msg = '该订单已全额退款'
    toast('退款失败：' + msg, 'error')
  }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">订单详情</h1>
      <span style="font-size:12.5px;color:var(--gray)">{{ route.query.no }}</span>
    </div>
    <button class="btn btn-secondary btn-sm" @click="backToList">← 返回列表</button>
  </div>

  <div v-if="err" class="card" style="padding:32px;text-align:center;color:var(--gray)">{{ err }}</div>
  <div v-else-if="!o" class="card skeleton" style="min-height:240px" />

  <div v-else class="grid-2" style="align-items:start">
    <div style="display:grid;gap:16px">
      <div class="card" style="padding:20px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <h3 style="font-size:15px">商品明细</h3>
          <span class="tag" :class="OSTATUS[o.status]?.[1] || 'tag-error'">{{ OSTATUS[o.status]?.[0] ?? o.status }}</span>
        </div>
        <div v-for="(it, i) in o.items || []" :key="i" style="display:flex;gap:12px;padding:10px 0;border-bottom:1px solid var(--gray-light);font-size:13px">
          <div style="flex:1">
            <b>{{ it.title }}</b>
            <div style="color:var(--gray)">x{{ it.qty }} · 单价 {{ money(it.unit_price) }}
              <span v-if="it.refunded_qty">· 已退 {{ it.refunded_qty }}</span></div>
          </div>
          <b>{{ money(it.subtotal) }}</b>
        </div>
        <div v-if="!(o.items || []).length" style="color:var(--gray);font-size:13px;padding:8px 0">📭 此订单暂无商品</div>
        <div style="display:grid;gap:6px;margin-top:12px;font-size:13px">
          <div style="display:flex;justify-content:space-between"><span>小计</span><span>{{ money(o.subtotal) }}</span></div>
          <div v-if="o.discount_total" style="display:flex;justify-content:space-between;color:var(--success)"><span>折扣</span><span>−{{ money(o.discount_total) }}</span></div>
          <div v-if="o.points_discount" style="display:flex;justify-content:space-between;color:var(--success)"><span>积分抵扣</span><span>−{{ money(o.points_discount) }}</span></div>
          <div v-if="o.giftcard_discount" style="display:flex;justify-content:space-between;color:var(--success)"><span>礼品卡抵扣</span><span>−{{ money(o.giftcard_discount) }}</span></div>
          <div style="display:flex;justify-content:space-between"><span>运费</span><span>{{ money(o.shipping_fee) }}</span></div>
          <div style="display:flex;justify-content:space-between"><span>税费</span><span>{{ money(o.tax) }}</span></div>
          <div style="display:flex;justify-content:space-between;font-weight:800;font-size:14.5px;border-top:1px solid var(--gray-light);padding-top:6px">
            <span>总计</span><span style="color:var(--plum)">{{ money(o.grand_total) }}</span>
          </div>
        </div>
      </div>

      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">时间线</h3>
        <div style="display:grid;gap:10px">
          <div v-for="(t, i) in o.timeline || []" :key="i" style="display:flex;gap:12px;font-size:13px">
            <span style="width:112px;color:var(--gray);flex:none;font-size:12px;padding-top:2px">{{ dt(t.created_at) }}</span>
            <span style="flex:1">
              <b>{{ EVENT_LABEL[t.event] || t.event }}</b>
              <span class="tag tag-done" style="margin-left:6px;font-size:10.5px;padding:1px 7px">{{ ACTOR[t.actor] || t.actor }}</span>
              <div v-if="eventText(t)" style="color:var(--gray);font-size:12.5px;margin-top:2px">{{ eventText(t) }}</div>
            </span>
          </div>
          <div v-if="!(o.timeline || []).length" style="color:var(--gray);font-size:13px">📭 暂无时间线记录</div>
        </div>
      </div>
    </div>

    <div style="display:grid;gap:16px">
      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">订单信息</h3>
        <div style="display:grid;gap:8px;font-size:13px">
          <div style="display:flex;justify-content:space-between"><span>客户</span><span>{{ o.email }}</span></div>
          <div style="display:flex;justify-content:space-between"><span>下单</span><span style="color:var(--gray)">{{ dt(o.placed_at) || '—' }}</span></div>
          <div style="display:flex;justify-content:space-between"><span>支付</span><span style="color:var(--gray)">{{ dt(o.paid_at) || '—' }}</span></div>
          <div v-if="o.shipped_at" style="display:flex;justify-content:space-between"><span>发货</span><span style="color:var(--gray)">{{ dt(o.shipped_at) }}</span></div>
          <div v-if="o.delivered_at" style="display:flex;justify-content:space-between"><span>送达</span><span style="color:var(--gray)">{{ dt(o.delivered_at) }}</span></div>
          <div style="display:flex;justify-content:space-between"><span>物流单号</span><span>{{ o.tracking_no || '—' }}</span></div>
          <div style="display:flex;justify-content:space-between"><span>积分</span><span>+{{ o.points_earned ?? 0 }} 得 / −{{ o.points_used ?? 0 }} 用</span></div>
        </div>
        <!-- 客户留言（下单时提交，浅底强调） -->
        <div v-if="o.note" style="margin-top:12px;background:var(--rose-pale);border-left:3px solid var(--rose);border-radius:8px;padding:10px 12px">
          <div style="font-size:11px;color:var(--gray);letter-spacing:1px;margin-bottom:3px">💬 客户留言</div>
          <div style="font-size:13px;color:var(--plum);line-height:1.6;white-space:pre-wrap">{{ o.note }}</div>
        </div>
      </div>

      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">支付信息</h3>
        <div v-for="p in o.payments || []" :key="p.id" style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--gray-light);font-size:13px">
          <div>
            <b>{{ money(p.amount) }}</b>
            <div style="color:var(--gray);font-size:12px">
              尾号 {{ (p.payment_intent || '').slice(-8) || '—' }}<span v-if="p.refunded_amount"> · 已退 {{ money(p.refunded_amount) }}</span>
            </div>
          </div>
          <span class="tag" :class="PSTATUS[p.status]?.[1]">{{ PSTATUS[p.status]?.[0] ?? p.status }}</span>
        </div>
        <div v-if="!(o.payments || []).length" style="color:var(--gray);font-size:13px">📭 暂无支付记录</div>
        <div v-else style="display:flex;justify-content:space-between;margin-top:10px;font-size:12.5px;color:var(--gray)">
          <span>可退余额（最新可退支付）</span><b :style="{ color: refundable > 0 ? 'var(--ink)' : 'var(--gray)' }">{{ money(refundable) }}</b>
        </div>
      </div>

      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">物流包裹</h3>
        <div v-for="s in o.shipments || []" :key="s.shipment_no" style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--gray-light);font-size:13px">
          <div>
            <b>{{ s.shipment_no }}</b> · {{ s.carrier || '—' }}
            <div style="color:var(--gray);font-size:12px">
              {{ s.tracking_no || '无单号' }} · 发货 {{ dt(s.shipped_at) || '—' }}<span v-if="s.delivered_at"> · 送达 {{ dt(s.delivered_at) }}</span>
            </div>
          </div>
          <span class="tag" :class="SHSTATUS[s.status]?.[1]">{{ SHSTATUS[s.status]?.[0] ?? s.status }}</span>
        </div>
        <div v-if="!(o.shipments || []).length" style="color:var(--gray);font-size:13px">📭 暂无物流包裹</div>
      </div>

      <div v-if="o.redemptions && o.redemptions.length" class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">折扣码核销</h3>
        <div v-for="(r, i) in o.redemptions" :key="i" style="display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-bottom:1px solid var(--gray-light);font-size:13px">
          <span>折扣码 #{{ r.code_id }}<span style="color:var(--gray)"> · {{ r.email }}</span></span>
          <b style="color:var(--success)">−{{ money(r.discount_amount) }}</b>
        </div>
      </div>

      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">收件地址</h3>
        <div v-if="o.shipping_address" style="font-size:13px;line-height:1.7;color:var(--ink)">
          {{ o.shipping_address?.full_name }}<br>{{ o.shipping_address?.line1 }} {{ o.shipping_address?.line2 }}<br>
          {{ o.shipping_address?.city }}, {{ o.shipping_address?.state }} {{ o.shipping_address?.zip }} · {{ o.shipping_address?.country }}
        </div>
        <div v-else style="color:var(--gray);font-size:13px">📭 暂无收件地址</div>
      </div>

      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">履约操作</h3>
        <div style="display:grid;gap:8px">
          <button v-if="o.status === 1 || o.status === 2" class="btn btn-primary" @click="act('ship')">📦 发货</button>
          <button v-if="o.status === 3" class="btn btn-secondary" @click="act('deliver')">✅ 标记妥投</button>
          <button v-if="[1, 2, 3, 4, 5].includes(o.status)" class="btn btn-ghost" style="color:var(--error)" @click="act('refund')">💸 退款（余额 {{ money(refundable) }}）</button>
          <div v-if="![1, 2, 3, 4, 5].includes(o.status)" style="color:var(--gray);font-size:13px">📭 当前状态（{{ OSTATUS[o.status]?.[0] ?? o.status }}）无可用操作</div>
        </div>
      </div>
    </div>
  </div>

  <!-- 发货弹窗 -->
  <div v-if="shipDlg" class="modal open" @click.self="shipDlg = false">
    <div class="modal-box" style="max-width:420px">
      <button class="modal-x" @click="shipDlg = false">×</button>
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
      <button class="btn btn-primary btn-block" style="margin-top:12px" @click="shipConfirm">确认发货</button>
    </div>
  </div>

  <!-- 退款弹窗 -->
  <div v-if="refundDlg" class="modal open" @click.self="refundDlg = false">
    <div class="modal-box" style="max-width:420px">
      <button class="modal-x" @click="refundDlg = false">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">💸 退款 {{ o.order_no }}</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:14px">
        订单总额 {{ money(o.grand_total) }} · 可退余额 <b style="color:var(--plum)">{{ money(refundable) }}</b>
        （按最新可退支付计算）。全额退款将回补库存、作废本单积分并恢复礼品卡抵扣。
      </p>
      <div class="field">
        <label>退款金额（分）<span style="color:var(--gray);font-weight:400">≈ {{ money(refundAmt) }}</span></label>
        <input v-model.number="refundAmt" class="input" type="number" min="1" :max="refundable">
      </div>
      <div class="field"><label>原因</label><input v-model="refundReason" class="input" placeholder="ops-refund"></div>
      <button class="btn btn-primary btn-block" style="margin-top:12px" @click="refundConfirm">确认退款</button>
    </div>
  </div>
</template>
