<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req, intentNoChannel } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import { useCartStore } from '../../stores/cart'
import { useUiStore } from '../../stores/ui'
import { COUNTRIES, PHONE_RE } from '../../data/countries'
import { statusLabel, statusTag } from '../../composables/orderStatus'
import { useArmConfirm } from '../../composables/useArmConfirm'
import { createOrderIntent } from '../../composables/useOrderPay'
import { fmtDateTime, zulu } from '../../composables/datetime'
import { money } from '../../composables/format'
import { i18n, tt } from '../../i18n'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const cart = useCartStore()
const auth = useAuthStore()
const o = ref(null)
const err = ref('')
const loading = ref(true)
const busy = ref(false)

/* 游客查单双因子：?email= 透传（复用 SuccessView/GiftCardsView 的 ?email= 模式；登录态走 Cookie 忽略） */
const guestEmail = computed(() => String(route.query.email || '').trim())
function guestQ() {
  return (!auth.isLoggedIn && guestEmail.value) ? '?email=' + encodeURIComponent(guestEmail.value) : ''
}

/* 订单商品图兜底：回落 placehold + dataset 守卫防循环（对齐 ProductCard imgFallback） */
const IMG_FALLBACK = 'https://placehold.co/200x200/E8B4B8/552338?text=%E2%9C%A8'
function imgFallback(e) {
  const img = e.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = IMG_FALLBACK
}

/* OrderStatus 共享映射（composables/orderStatus.js）：0待付 1已付 2备货 3已发货 4已送达 5已完成 8已取消 9已退款 */
/* 标签统一 [en, zh]（tt 局部双语），对齐 TrackView EVENT_TEXT 模式 */
/* RmaReason 1-6 */
const RMA_REASON = {
  1: ['Wrong size', '尺码不合'], 2: ['Quality issue', '质量问题'], 3: ['Not a fit', '不喜欢'],
  4: ['Arrived damaged', '收到损坏'], 5: ['Wrong item shipped', '发错货'], 6: ['Other', '其他'],
}
/* ShipmentStatus */
const SHIP_ST = {
  0: ['Awaiting label', '待打单'], 1: ['Label printed', '已打单'], 2: ['Awaiting handoff', '待交接'],
  3: ['In transit', '运输中'], 4: ['Delivered', '已送达'], 5: ['Exception', '异常'], 6: ['Label voided', '面单作废'],
}
/* PaymentStatus：[en, zh, tag] */
const PAY_ST = {
  0: ['Pending', '待支付', 'tag-pending'], 1: ['Paid', '成功', 'tag-paid'], 2: ['Failed', '失败', 'tag-error'],
  3: ['Refunded', '已退款', 'tag-error'], 4: ['Partially refunded', '部分退款', 'tag-pending'],
}
/* 时间线事件 → [en, zh]（status_changed 特判带状态名；对齐后端全部事件名，含 RMA/换货/礼品卡链路） */
const EVENT_LABEL = {
  status_changed: ['Status updated', '状态变更'], payment_succeeded: ['Payment confirmed', '支付成功'],
  payment_failed: ['Payment failed', '支付失败'], rma_created: ['Return requested', '退货申请'],
  exchange_created: ['Exchange requested', '换货申请'], exchange_approved: ['Exchange approved', '换货已批准'],
  exchange_rejected: ['Exchange declined', '换货被拒绝'], exchange_diff_paid: ['Exchange difference paid', '换货差价已支付'],
  exchange_shipped: ['Exchange shipped', '换货已发货'], exchange_completed: ['Exchange completed', '换货完成'],
  points_granted: ['Points granted', '积分发放'], tracking_updated: ['Tracking updated', '物流更新'],
  note_added: ['Note added', '备注'], email_sent: ['Email sent', '邮件通知'],
  ticket_linked: ['Ticket linked', '关联工单'], label_voided: ['Label voided', '面单作废'],
  checkout_created: ['Order placed', '订单已创建'], shipment_created: ['Package shipped', '包裹已发出'],
  refund_issued: ['Refund issued', '退款已发放'], rma_label_sent: ['Return label sent', '退货标签已发送'],
  rma_received: ['Return received', '退货已签收'], rma_canceled: ['Return canceled', '退货已取消'],
  giftcard_created: ['Gift card issued', '礼品卡已开出'],
  exchange_withdrawn: ['Exchange withdrawn', '换货已撤回'],
  exchange_diff_intent: ['Exchange difference payment created', '换货差价待支付'],
  exchange_diff_refunded: ['Exchange difference refunded', '换货差价已退回'],
}
function eventLabel(t) {
  if (t.event === 'status_changed' && t.detail && t.detail.to !== undefined) {
    return tt(`Status → ${statusLabel(t.detail.to)}`, `状态 → ${statusLabel(t.detail.to)}`)
  }
  const row = EVENT_LABEL[t.event]
  return row ? tt(row[0], row[1]) : (t.event || '').replace(/_/g, ' ')
}

const fmt = fmtDateTime
/* 时间线 detail 已知键 → 双语标签（白名单）：未知键不渲染，最多 3 条（防原始键名/内部 id 泄漏） */
const DETAIL_LABELS = {
  from: ['From', '从'], to: ['To', '至'], qty: ['Qty', '数量'],
  reason: ['Reason', '原因'], amount: ['Amount', '金额'], source: ['Source', '来源'],
  carrier: ['Carrier', '承运商'], tracking_no: ['Tracking no.', '追踪号'], operator: ['Operator', '操作者'],
}
function detailText(ev) {
  const d = ev.detail
  if (!d) return ''
  if (ev.event === 'status_changed' && d.to !== undefined) {
    return `${statusLabel(d.from)} → ${statusLabel(d.to)}`
  }
  if (typeof d === 'object') {
    return Object.entries(d)
      .filter(([k]) => DETAIL_LABELS[k])
      .slice(0, 3)
      .map(([k, v]) => `${tt(DETAIL_LABELS[k][0], DETAIL_LABELS[k][1])}: ${v}`).join(' · ')
  }
  return String(d)
}

async function load() {
  const no = route.query.no
  /* 每次进入先清残留错误态：切换订单/支付后刷新可正常渲染（修复失败一次后永久错误卡） */
  err.value = ''
  o.value = null
  loading.value = true
  if (!no) { err.value = tt('Missing order number', '缺少订单号'); loading.value = false; return }
  try {
    o.value = await req('GET', '/api/orders/' + encodeURIComponent(no) + guestQ())
    /* reviewed 持久化：order detail items 新增 reviewed 字段（无字段时回落会话内行为） */
    for (const it of (o.value.items || [])) if (it.reviewed) reviewed.value[it.id] = true
  } catch (e) {
    err.value = e && e.status === 404 ? tt('Order not found', '订单不存在') : tt('Could not load this order — please retry later', '订单加载失败，请稍后再试')
  } finally { loading.value = false }
}
onMounted(load)
/* 同路由 ?no= 切换（订单间跳转）时重新加载 */
watch(() => route.query.no, () => load())

/* 进度条仅用于正常履约流（0-5）；取消/退款单独展示 */
const steps = computed(() => {
  if (!o.value) return []
  const labels = [tt('Placed', '下单'), tt('Paid', '支付'), tt('Packing', '备货'), tt('Shipped', '发货'), tt('Delivered', '送达')]
  const s = o.value.status
  if (![0, 1, 2, 3, 4, 5].includes(s)) return []
  const upto = Math.min(s, 4)
  return labels.map((l, i) => ({ l, done: i <= upto, now: i === upto }))
})
const addr = computed(() => o.value?.shipping_address || {})
/* 可退换：已付且未取消/退款（后端 RETURNABLE_STATUSES {1,2,3,4,5}） */
const statusReturnable = computed(() => !!o.value && [1, 2, 3, 4, 5].includes(o.value.status))
/* 30 天退货窗口预判（仅按 paid_at 判断，与服务端同口径；paid_at 缺失视为可退） */
const inReturnWindow = computed(() => {
  const ov = o.value
  if (!ov) return false
  if (!ov.paid_at) return true
  const t = new Date(zulu(ov.paid_at)).getTime()
  return isNaN(t) ? true : Date.now() - t <= 30 * 86400000
})
const returnable = computed(() => statusReturnable.value && inReturnWindow.value)
function avail(it) { return (it.qty || 0) - (it.refunded_qty || 0) - (it.exchanged_qty || 0) }
/* 已支付且未发货：可自助取消（后端自动全额原路退款） */
const canSelfCancel = computed(() => !!o.value && o.value.status === 1 && (o.value.shipping_status || 0) === 0)
/* 再次购买：非待付/非取消/非退款（0/8/9 之外） */
const canBuyAgain = computed(() => !!o.value && ![0, 8, 9].includes(o.value.status))
/* 已送达待确认：可自助确认收货（4→5 已完成） */
const canConfirmRecv = computed(() => !!o.value && o.value.status === 4)

/* 待付订单：支付（createOrderIntent 统一封装：methods 对账 + provider_unavailable 回退）/ 取消 */
async function payNow() {
  busy.value = true
  try {
    const intent = await createOrderIntent(o.value.order_no)
    if (intentNoChannel(intent)) {
      ui.toast(i18n.t('pay.unsupported_channel'), 'error')
      return
    }
    /* hosted 通道（Stripe Checkout / PayPal 等）：跳转收银台，回来后由 webhook 推进状态；
       3s 未离页 → 恢复按钮并提示重试（对齐 CheckoutView 跳转看门狗） */
    if (intent && intent.redirect_url) {
      window.location.href = intent.redirect_url
      setTimeout(() => {
        if (document.visibilityState !== 'hidden') {
          busy.value = false
          ui.toast(tt('Redirecting to payment… if nothing happened, please retry', '正在跳转支付…若未打开请重试'), 'error')
        }
      }, 3000)
      return
    }
    const d = await req('POST', '/api/payments/mock-pay', { order_no: o.value.order_no, succeed: true })
    ui.toast(d.order_status === 1 ? tt('Payment successful 🎉', '支付成功 🎉') : tt('Payment processing', '支付处理中'), 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    if (String(d).startsWith('order_not_pending') || d === 'already_paid') { ui.toast(tt('Order status changed — refreshed', '订单状态已变化，已刷新'), 'error'); await load() }
    else ui.toast(tt('Payment failed — please retry later', '支付失败，请稍后再试'), 'error')
  } finally { busy.value = false }
}
/* 两段式确认（useArmConfirm：5s 复位；按钮 arm 态红字 + 二段文案） */
const cancelArm = useArmConfirm()
const recvArm = useArmConfirm()

/* 确认收货（仅 status=4 已送达）：CAS 4→5 已完成 */
async function confirmReceived() {
  busy.value = true
  try {
    await req('POST', '/api/orders/' + encodeURIComponent(o.value.order_no) + '/confirm-received')
    ui.toast(tt('Thanks! Order completed 🎉', '感谢确认收货，订单已完成 🎉'), 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    if (String(d).startsWith('not_confirmable')) { ui.toast(tt('Order status changed — refreshed', '订单状态已变化，已刷新'), 'error'); await load() }
    else ui.toast(tt('Could not confirm — please retry later', '确认失败，请稍后再试'), 'error')
  } finally { busy.value = false }
}

/* 待付取消（仅释放库存，无退款） */
async function cancelOrder() {
  busy.value = true
  try {
    await req('POST', '/api/orders/' + encodeURIComponent(o.value.order_no) + '/cancel', { reason: 'user' })
    ui.toast(tt('Order cancelled', '订单已取消'), 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    ui.toast(String(d).startsWith('not_cancellable') ? tt('This order cannot be cancelled in its current status', '该订单当前状态不可取消') : tt('Cancel failed — please retry later', '取消失败，请稍后再试'), 'error')
  } finally { busy.value = false }
}
/* 已支付未发货：自助取消并全额原路退款（POST cancel 扩展；409 no_refundable_payment 需转人工） */
async function cancelPaidOrder() {
  busy.value = true
  try {
    const d = await req('POST', '/api/orders/' + encodeURIComponent(o.value.order_no) + '/cancel', { reason: 'user' })
    const ref = d && d.refund
    ui.toast(ref && ref.amount
      ? tt(`Order cancelled — ${money(ref.amount)} refund on its way back to your payment method`, `订单已取消，退款 ${money(ref.amount)} 将原路退回`)
      : tt('Order cancelled — refund on its way back to your payment method', '订单已取消，退款将原路退回'), 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    if (String(d).startsWith('no_refundable_payment')) ui.toast(tt('Auto refund unavailable — please contact support', '无法自动退款，请联系客服'), 'error')
    else if (String(d).startsWith('not_cancellable')) { ui.toast(tt('Order status changed — refreshed', '订单状态已变化，已刷新'), 'error'); await load() }
    else ui.toast(tt('Cancel failed — please retry later', '取消失败，请稍后再试'), 'error')
  } finally { busy.value = false }
}

/* ---------- 再次购买：POST /api/cart/items-batch（按 qty-refunded-exchanged 计算，≤20 项） ---------- */
const rebuying = ref(false)
function batchFailText(r) {
  const s = String(r == null ? '' : r)
  if (s === '409' || /stock/i.test(s)) return tt('out of stock', '缺货')
  if (s === '404' || /not.?found|inactive|unavailable|off/i.test(s)) return tt('no longer available', '已下架')
  return s
}
async function buyAgain() {
  /* 全部可复购行（qty-refunded-exchanged）；批量上限 20 行，超出部分提示手动加购 */
  const all = (o.value.items || [])
    .map((it) => ({ variant_id: it.variant_id, qty: Math.max(0, avail(it)) }))
    .filter((x) => x.qty > 0)
  const items = all.slice(0, 20)
  if (!items.length) { ui.toast(tt('No re-orderable items in this order', '该订单没有可重新购买的商品'), 'error'); return }
  rebuying.value = true
  try {
    const d = await req('POST', '/api/cart/items-batch', { items })
    /* add_batch 返回 view 顶层展开（token/items/subtotal_cents + added/failed），直接应用 */
    if (d && d.items) cart._apply(d)
    else await cart.refresh().catch(() => {})
    /* 后端 added 为成功加入的 variant_id 数组 */
    const added = ((d && d.added) || []).length
    const failed = (d && d.failed) || []
    if (failed.length) {
      ui.toast(tt(
        `Added ${added} item(s); ${failed.length} failed (${failed.map((f) => batchFailText(f.reason)).join(', ')})`,
        `已加 ${added} 件，${failed.length} 件失败（${failed.map((f) => batchFailText(f.reason)).join('、')}）`,
      ), 'error')
    } else if (all.length > items.length) {
      ui.toast(tt(
        `Added ${added}/${all.length} items — please add the rest manually (20-line batch limit)`,
        `已加 ${added}/${all.length} 件，其余请手动加购`,
      ), 'success')
    } else {
      ui.toast(tt(`Added ${added} item(s) to cart`, `已加入 ${added} 件商品`), 'success')
    }
    ui.openCart()
  } catch (e) {
    ui.toast(tt('Could not add items — please retry later', '加入购物车失败，请稍后再试'), 'error')
  } finally { rebuying.value = false }
}

/* ---------- 弹层 a11y 工具：ESC 关闭 + 焦点圈禁（开闭状态走 ui.openModalId 通道 →
      anyOverlay 统一锁滚动（gm-locked）+ App 根 ESC 委托自动关闭，替代第三套内联 overflow 写法） ---------- */
const rmaBox = ref(null)
const exBox = ref(null)
let rmaFrom = null
let exFrom = null
function dialogFocusables(root) {
  if (!root) return []
  return [...root.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
}
function trapKeydown(e, boxEl) {
  if (e.key === 'Tab') {
    const f = dialogFocusables(boxEl)
    if (!f.length) return
    const first = f[0]
    const last = f[f.length - 1]
    const inBox = boxEl.contains(document.activeElement)
    if (e.shiftKey && (document.activeElement === first || !inBox)) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && (document.activeElement === last || !inBox)) { e.preventDefault(); first.focus() }
  }
}
const rmaOpen = computed(() => ui.openModalId === 'rma')
const exOpen = computed(() => ui.openModalId === 'ex')
function closeModal() { ui.closeModal() }
function onEscKey(e) {
  /* App 根 ESC 委托已处理 ui.openModalId；此处仅兜底（如焦点在 iframe 内时根监听收不到） */
  if (e.key !== 'Escape') return
  if (rmaOpen.value || exOpen.value || addrOpen.value) ui.closeModal()
}
function restoreFocus(el) {
  if (el && el !== document.body && document.contains(el)) {
    try { el.focus({ preventScroll: true }) } catch (_) { /* 触发元素已卸载 */ }
  }
}

/* ---------- 退货 RMA ---------- */
const rma = reactive({ item: null, qty: 1, reason: 1, detail: '', busy: false })
const rmaSubmitted = ref(false)
const exSubmitted = ref(false)
function openRma(it) {
  Object.assign(rma, { item: it, qty: 1, reason: 1, detail: '', busy: false })
  ui.openModal('rma')
}
async function submitRma() {
  rma.busy = true
  try {
    const d = await req('POST', '/api/returns', {
      order_no: o.value.order_no,
      order_item_id: rma.item.id,
      qty: rma.qty,
      reason: rma.reason,
      reason_detail: rma.detail || null,
    })
    ui.toast(tt(`Return request submitted (${d.rma_no}) — pending review`, `退货申请已提交（${d.rma_no}），请耐心等待审核`), 'success')
    rmaSubmitted.value = true
    ui.closeModal()
    await load()
  } catch (e) {
    const d = (e && e.data && e.data.detail) || ''
    if (String(d).startsWith('not_returnable')) ui.toast(tt('This order is not returnable in its current status', '该订单当前状态不可退货'), 'error')
    else if (d === 'return_window_closed') ui.toast(tt('Return window closed (only within the valid return period)', '退货窗口已关闭（仅退货有效期内可退）'), 'error')
    else if (String(d).startsWith('qty_exceeds_available')) ui.toast(tt('Return quantity exceeds available quantity', '退货数量超出可退数量'), 'error')
    else ui.toast(tt('Return request failed — please retry later', '退货申请失败，请稍后再试'), 'error')
  } finally { rma.busy = false }
}

/* ---------- 换货（siblings 一次拉取同款变体，替换旧的 N+1 搜索） ---------- */
const ex = reactive({ item: null, loading: false, variants: [], picked: null, qty: 1, reason: '', busy: false, error: '', netFail: false })
async function loadSiblings() {
  ex.loading = true
  ex.error = ''
  ex.netFail = false
  /* GET /api/catalog/variants/{old_variant_id}/siblings → 同款全部在售变体（含库存态） */
  try {
    const d = await req('GET', '/api/catalog/variants/' + ex.item.variant_id + '/siblings')
    ex.variants = (d.variants || []).filter((v) => v.id !== ex.item.variant_id)
  } catch (e) {
    if (e && e.status === 404) ex.error = tt('No other variants of this style — the product may have been delisted', '未找到同款其它规格——商品可能已下架')
    else {
      ex.netFail = true
      ex.error = tt('Network error — could not load variants', '网络异常，规格加载失败')
    }
    ex.loading = false
    return
  }
  if (!ex.variants.length) ex.error = tt('No other variants of this style', '未找到同款其它规格')
  else {
    /* 预选首个有货变体 */
    const firstOk = ex.variants.find((v) => (v.stock || 0) > 0 && v.stock_status !== 'out')
    ex.picked = firstOk ? firstOk.id : null
  }
  ex.loading = false
}
async function openExchange(it) {
  Object.assign(ex, { item: it, loading: true, variants: [], picked: null, qty: 1, reason: '', busy: false, error: '', netFail: false })
  ui.openModal('ex')
  await loadSiblings()
}
function exStockText(v) {
  if ((v.stock || 0) <= 0 || v.stock_status === 'out') return tt('Out of stock', '缺货')
  if (v.stock_status === 'low' || (v.stock || 0) <= 5) return tt(`Only ${v.stock} left`, `仅剩 ${v.stock} 件`)
  return tt('In stock', '有货')
}
function exSelectable(v) { return (v.stock || 0) > 0 && v.stock_status !== 'out' }
function exDiff(v) {
  /* 差价 = 单件差 × 换货数量，单件按实付折算（对齐后端 paid_unit = unit_price × grand_total / subtotal） */
  const ov = o.value
  const ratio = ov && ov.subtotal > 0 ? ov.grand_total / ov.subtotal : 1
  const paidUnit = Math.round((ex.item?.unit_price || 0) * ratio)
  const diff = ((v.price || 0) - paidUnit) * (ex.qty || 1)
  if (diff > 0) return tt(`Pay difference ${money(diff)}`, `需补差价 ${money(diff)}`) + i18n.t('ord.diffEst')
  if (diff < 0) return tt(`Refund difference ${money(-diff)}`, `退差价 ${money(-diff)}`) + i18n.t('ord.diffEst')
  return tt('Even swap', '同价换货')
}
async function submitExchange() {
  if (!ex.picked) return
  ex.busy = true
  try {
    const d = await req('POST', '/api/exchanges', {
      order_no: o.value.order_no,
      order_item_id: ex.item.id,
      new_variant_id: ex.picked,
      qty: ex.qty,
      reason: ex.reason.trim() || null,
    })
    ui.toast(tt(`Exchange request submitted (${d.exchange_no})`, `换货申请已提交（${d.exchange_no}）`), 'success')
    exSubmitted.value = true
    ui.closeModal()
    await load()
  } catch (e) {
    const d = (e && e.data && e.data.detail) || ''
    if (String(d).startsWith('not_exchangeable')) ui.toast(tt('This order is not exchangeable in its current status', '该订单当前状态不可换货'), 'error')
    else if (d === 'return_window_closed') ui.toast(tt('Exchange window closed', '换货窗口已关闭'), 'error')
    else if (String(d).startsWith('qty_exceeds_available')) ui.toast(tt('Insufficient quantity available for exchange', '可换数量不足'), 'error')
    else if (d === 'variant_out_of_stock') ui.toast(tt('That variant is out of stock — pick another', '新规格库存不足，请重选'), 'error')
    else if (d === 'variant_not_found') ui.toast(tt('That variant no longer exists — pick another', '所选规格不存在，请重选'), 'error')
    else ui.toast(tt('Exchange request failed — please retry later', '换货申请失败，请稍后再试'), 'error')
  } finally { ex.busy = false }
}

/* 弹层打开：初始聚焦 + 关闭还原焦点（滚动锁由 ui.anyOverlay → StoreLayout gm-locked 统一驱动） */
watch(rmaOpen, async (v) => {
  if (v) {
    rmaFrom = document.activeElement
    await nextTick()
    const f = dialogFocusables(rmaBox.value)
    if (f.length) f[0].focus({ preventScroll: true })
  } else {
    restoreFocus(rmaFrom)
    rmaFrom = null
  }
})
watch(exOpen, async (v) => {
  if (v) {
    exFrom = document.activeElement
    await nextTick()
    const f = dialogFocusables(exBox.value)
    if (f.length) f[0].focus({ preventScroll: true })
  } else {
    restoreFocus(exFrom)
    exFrom = null
  }
})

/* ---------- 修改收货地址（PUT /api/orders/{no}/address；status∈{0,1,2} 且 shipping_status===0 可改；游客 ?email=） ---------- */
const addrEditable = computed(() => !!o.value && [0, 1, 2].includes(o.value.status) && (o.value.shipping_status || 0) === 0)
const addrOpen = computed(() => ui.openModalId === 'addr')
const addrBox = ref(null)
let addrFrom = null
const ad = reactive({ full_name: '', line1: '', line2: '', city: '', state: '', zip: '', country: 'US', phone: '', busy: false, err: '' })
function openAddr() {
  /* 预填当前地址；country 不在 COUNTRIES 列表时回落 US（select 匹配不到会显示空） */
  const a = o.value?.shipping_address || {}
  Object.assign(ad, {
    full_name: a.full_name || '', line1: a.line1 || '', line2: a.line2 || '',
    city: a.city || '', state: a.state || '', zip: a.zip || '',
    country: COUNTRIES.some((c) => c[0] === a.country) ? a.country : 'US',
    phone: a.phone || '', busy: false, err: '',
  })
  ui.openModal('addr')
}
function adCheck() {
  if (!ad.full_name.trim()) return tt('Recipient name is required', '请填写收件人姓名')
  if (!ad.line1.trim()) return tt('Street address is required', '请填写街道地址')
  if (!ad.city.trim()) return tt('City is required', '请填写城市')
  if (!ad.zip.trim()) return tt('ZIP / postal code is required', '请填写邮编')
  if (!ad.country) return tt('Select a country', '请选择国家')
  if (!PHONE_RE.test(ad.phone.trim())) return tt('Enter a valid phone number', '请输入有效的电话号码')
  return ''
}
async function saveAddr() {
  ad.err = adCheck()
  if (ad.err) return
  ad.busy = true
  try {
    await req('PUT', '/api/orders/' + encodeURIComponent(o.value.order_no) + '/address' + guestQ(), {
      full_name: ad.full_name.trim(),
      line1: ad.line1.trim(),
      line2: ad.line2.trim(),
      city: ad.city.trim(),
      state: ad.state.trim(),
      zip: ad.zip.trim(),
      country: ad.country,
      phone: ad.phone.trim(),
    })
    ui.closeModal()
    ui.toast(tt('Shipping address updated', '收货地址已更新'), 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    if (String(d) === 'not_editable') {
      ui.closeModal()
      ui.toast(tt('This order can no longer edit its address — refreshed', '该订单当前状态不可修改地址，已刷新'), 'error')
      await load()
    } else ui.toast(tt('Could not save — please retry later', '保存失败，请稍后再试'), 'error')
  } finally { ad.busy = false }
}
watch(addrOpen, async (v) => {
  if (v) {
    addrFrom = document.activeElement
    await nextTick()
    const f = dialogFocusables(addrBox.value)
    if (f.length) f[0].focus({ preventScroll: true })
  } else {
    restoreFocus(addrFrom)
    addrFrom = null
  }
})
onMounted(() => document.addEventListener('keydown', onEscKey))
onUnmounted(() => {
  document.removeEventListener('keydown', onEscKey)
  clearTimeout(rvPvTimer)
  /* 组件卸载时弹层仍开着 → 释放全局模态位，避免 anyOverlay 卡死锁滚动 */
  if (rmaOpen.value || exOpen.value || addrOpen.value) ui.closeModal()
})

/* ---------- 商品评价（status≥3 已发货/送达/完成可评；成功后按钮置灰） ---------- */
const reviewableStatus = computed(() => !!o.value && [3, 4, 5].includes(o.value.status))
const rv = reactive({ openId: null, rating: 5, content: '', images: [''], busy: false, err: '' })
const reviewed = ref({}) /* order_item_id → true（本会话已提交） */
function reviewDone(it) { return !!reviewed.value[it.id] }
function toggleReview(it) {
  if (rv.openId === it.id) { rv.openId = null; return }
  Object.assign(rv, { openId: it.id, rating: 5, content: '', images: [''], busy: false, err: '' })
}
function rvImages() {
  return rv.images.map((s) => s.trim()).filter(Boolean)
}
/* 图片预览：复用 Gallery 防抖模式 —— 首条 URL 输入停顿 500ms 后挂 <img>，@load ok / @error bad（红框） */
const rvPv = reactive({ url: '', state: '' }) /* '' 未校验 | loading | ok | bad */
let rvPvTimer = null
watch(() => (rv.images[0] || '').trim(), (u) => {
  clearTimeout(rvPvTimer)
  if (!u || !/^https:\/\//i.test(u)) { rvPv.url = ''; rvPv.state = ''; return }
  rvPv.state = 'loading'
  rvPv.url = ''
  rvPvTimer = setTimeout(() => { rvPv.url = u }, 500)
})
function rvPvLoad() { if (rvPv.state === 'loading') rvPv.state = 'ok' }
function rvPvError() { if (rvPv.state === 'loading') rvPv.state = 'bad' }

/* ---------- 评价传图（POST /api/content/reviews/upload multipart）：req 恒设 json 头 + JSON.stringify body，
   FormData 必须原生 fetch（不设 Content-Type 让浏览器自动带 multipart boundary），不改 client.js ---------- */
const rvFile = ref(null)
const rvUploading = ref(false)
const RV_IMG_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']
async function rvUpload(e) {
  const f = e.target.files && e.target.files[0]
  e.target.value = '' /* 复位以便同名文件可重复触发 */
  if (!f || rvUploading.value) return
  if (!RV_IMG_TYPES.includes(f.type)) { ui.toast(tt('Only PNG / JPG / WebP / GIF images are allowed', '仅支持 PNG / JPG / WebP / GIF 图片'), 'error'); return }
  if (f.size > 5 * 1024 * 1024) { ui.toast(tt('Image must be 5 MB or smaller', '图片不能超过 5MB'), 'error'); return }
  if (rv.images.filter((s) => s.trim()).length >= 6) { ui.toast(tt('Up to 6 images per review', '每条评价最多 6 张图片'), 'error'); return }
  rvUploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', f)
    const r = await fetch((window.GM_API_BASE || '') + '/api/content/reviews/upload', {
      method: 'POST',
      body: fd,
      credentials: 'include',
    })
    let d = null
    try { d = await r.json() } catch (_) { /* 非 JSON 响应 */ }
    if (!r.ok) {
      const det = d && d.detail
      if (r.status === 401) {
        /* 原生 fetch 不走 req 的 401 广播：对齐 submitReview 的未登录处理 */
        ui.toast(tt('Please sign in to review', '请登录后再评价'), 'error')
        router.push({ path: '/login', query: { next: route.fullPath } })
      } else if (det === 'invalid_type') ui.toast(tt('Only PNG / JPG / WebP / GIF images are allowed', '仅支持 PNG / JPG / WebP / GIF 图片'), 'error')
      else if (det === 'too_large') ui.toast(tt('Image must be 5 MB or smaller', '图片不能超过 5MB'), 'error')
      else ui.toast(tt('Upload failed — please retry later', '上传失败，请稍后再试'), 'error')
      return
    }
    const url = d && d.url
    if (!url) { ui.toast(tt('Upload failed — please retry later', '上传失败，请稍后再试'), 'error'); return }
    /* 追加进现有图片链接列表：优先填首个空位，否则新起一行（复用现有增删/预览逻辑） */
    const i = rv.images.findIndex((s) => !s.trim())
    if (i !== -1) rv.images[i] = url
    else rv.images.push(url)
    ui.toast(tt('Image uploaded', '图片已上传'), 'success')
  } catch (_) {
    ui.toast(tt('Upload failed — please retry later', '上传失败，请稍后再试'), 'error')
  } finally { rvUploading.value = false }
}
function rvCheck() {
  const imgs = rvImages()
  if (imgs.length > 6) return tt('Up to 6 image links', '图片链接最多 6 条')
  if (imgs.some((u) => !/^https:\/\//i.test(u))) return tt('Image links must start with https://', '图片链接需为 https:// 开头')
  if (rvPv.state === 'bad') return tt('The first image link cannot be loaded — check it before submitting', '首条图片链接无法加载，请检查后再提交')
  return ''
}
async function submitReview(it) {
  rv.err = rvCheck()
  if (rv.err) return
  rv.busy = true
  try {
    const body = {
      order_no: o.value.order_no,
      order_item_id: it.id,
      rating: rv.rating,
    }
    const imgs = rvImages()
    if (rv.content.trim()) body.content = rv.content.trim()
    if (imgs.length) body.images = imgs
    await req('POST', '/api/content/reviews', body)
    reviewed.value[it.id] = true
    rv.openId = null
    ui.toast(tt('Review submitted — it will appear after moderation (+10 points)', '评价已提交，审核后展示（+10 积分）'), 'success')
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    if (e && e.status === 401) {
      ui.toast(tt('Please sign in to review', '请登录后再评价'), 'error')
      router.push({ path: '/login', query: { next: route.fullPath } })
    } else if (e && e.status === 409 && String(d) === 'order not reviewable') {
      rv.err = tt('Reviews open after your order ships', '订单发货后才能评价')
    } else if (e && e.status === 409 && String(d) === 'already reviewed') {
      rv.err = tt('You have already reviewed this item', '已评价过')
      reviewed.value[it.id] = true
    } else if (e && e.status === 404) {
      rv.err = tt('Order or item not found — please refresh', '订单或商品不存在，请刷新')
    } else {
      rv.err = tt('Submit failed — please retry later', '提交失败，请稍后再试')
    }
  } finally { rv.busy = false }
}
</script>

<template>
  <div>
    <div v-if="err" class="card" style="padding:30px;text-align:center;color:var(--gray)">
      {{ err }}
      <div style="margin-top:10px;display:flex;gap:10px;justify-content:center;flex-wrap:wrap">
        <button class="btn btn-secondary btn-sm" @click="load">⟳ {{ tt('Retry', '重试') }}</button>
        <router-link class="btn btn-secondary btn-sm" to="/account/orders">{{ tt('← Back to orders', '← 返回订单列表') }}</router-link>
      </div>
    </div>
    <div v-else-if="loading" style="display:grid;gap:16px">
      <div class="skeleton" style="height:110px;border-radius:14px" />
      <div class="skeleton" style="height:260px;border-radius:14px" />
    </div>

    <div v-else style="display:grid;gap:16px">
      <!-- 返回订单列表入口（移动端同样可见） -->
      <div>
        <router-link to="/account/orders" style="font-size:13px;font-weight:600;color:var(--plum)">← {{ tt('Back to orders', '返回订单列表') }}</router-link>
      </div>
      <!-- 头部 + 进度 -->
      <div class="card" style="padding:20px">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
          <div>
            <h2 style="font-family:var(--font-title);font-size:22px">{{ o.order_no }}</h2>
            <div style="font-size:12.5px;color:var(--gray)">{{ tt('Placed', '下单') }} {{ fmt(o.placed_at) }}<span v-if="o.paid_at"> · {{ tt('Paid', '支付') }} {{ fmt(o.paid_at) }}</span></div>
          </div>
          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
            <span class="tag" :class="statusTag(o.status)">{{ statusLabel(o.status) }}</span>
            <template v-if="o.status === 0">
              <button class="btn btn-primary btn-sm" :class="{ loading: busy }" :disabled="busy" @click="payNow">{{ tt('Pay', '去支付') }} {{ money(o.grand_total) }}</button>
              <button
                class="btn btn-ghost btn-sm" :class="{ arm: cancelArm.is('pending'), loading: busy }"
                :disabled="busy" @click="cancelArm.hit('pending', cancelOrder)"
              >{{ cancelArm.is('pending') ? tt('Tap again to confirm', '再点一次确认') : tt('Cancel order', '取消订单') }}</button>
            </template>
            <template v-else>
              <button
                v-if="canConfirmRecv" class="btn btn-primary btn-sm" :class="{ arm: recvArm.is('recv'), loading: busy }"
                :disabled="busy || rebuying" @click="recvArm.hit('recv', confirmReceived)"
              >{{ recvArm.is('recv') ? tt('Tap again to confirm', '再点一次确认') : tt('✓ Confirm delivery', '确认收货') }}</button>
              <button
                v-if="canSelfCancel" class="btn btn-ghost btn-sm" :class="{ arm: cancelArm.is('paid'), loading: busy }"
                :disabled="busy || rebuying" @click="cancelArm.hit('paid', cancelPaidOrder)"
              >{{ cancelArm.is('paid') ? tt('Tap again to confirm', '再点一次确认') : tt('Cancel & refund', '取消并退款') }}</button>
              <button v-if="canBuyAgain" class="btn btn-secondary btn-sm" :class="{ loading: rebuying }" :disabled="rebuying || busy" @click="buyAgain">🛒 {{ tt('Buy again', '再次购买') }}</button>
            </template>
          </div>
        </div>
        <div v-if="steps.length" class="od-steps">
          <div v-for="(s, i) in steps" :key="i" class="od-step" :class="{ 'is-done': s.done }">
            <div class="od-dot" :style="{ background: s.done ? 'var(--success)' : 'var(--gray-light)' }">
              {{ s.done ? '✓' : i + 1 }}
            </div>
            <div class="od-step-label" :style="{ color: s.done ? 'var(--ink)' : 'var(--gray)', fontWeight: s.now ? '700' : '' }">{{ s.l }}</div>
          </div>
        </div>
        <div v-else style="margin-top:14px;padding:10px 14px;border-radius:10px;background:var(--pale-error);color:var(--error);font-size:13.5px;font-weight:600">
          {{ o.status === 8 ? tt('Order cancelled', '订单已取消') : tt('Order refunded', '订单已退款') }}
        </div>
      </div>

      <div class="grid-m-1" style="display:grid;grid-template-columns:1.4fr 1fr;gap:16px">
        <div style="display:grid;gap:16px">
          <!-- 商品 -->
          <div class="card" style="padding:20px">
            <h3 style="font-size:15px;margin-bottom:12px">{{ tt('Items', '商品') }}</h3>
            <div v-for="it in o.items || []" :key="it.id" style="padding:12px 0;border-bottom:1px solid var(--gray-light)">
              <div style="display:flex;gap:12px;align-items:center">
                <img :src="it.image" :alt="it.title" style="width:56px;height:56px;border-radius:9px;object-fit:cover" @error="imgFallback">
                <div style="flex:1;font-size:13.5px;min-width:0">
                  <b style="display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ it.title }}</b>
                  <div style="color:var(--gray);font-size:12px">
                    {{ money(it.unit_price) }} × {{ it.qty }}
                    <span v-if="it.refunded_qty" class="tag tag-error" style="margin-left:6px">{{ tt('Refunded', '已退') }} {{ it.refunded_qty }}</span>
                    <span v-if="it.exchanged_qty" class="tag tag-ship" style="margin-left:6px">{{ tt('Exchanged', '已换') }} {{ it.exchanged_qty }}</span>
                  </div>
                </div>
                <b style="font-size:13.5px">{{ money(it.subtotal) }}</b>
              </div>
              <div v-if="(statusReturnable && avail(it) > 0) || reviewableStatus" class="item-actions">
                <template v-if="statusReturnable && avail(it) > 0 && inReturnWindow">
                  <button class="btn btn-ghost btn-sm" @click="openRma(it)">↩️ {{ tt('Request return', '申请退货') }}（{{ tt('max', '可退') }} {{ avail(it) }}）</button>
                  <button class="btn btn-ghost btn-sm" @click="openExchange(it)">🔁 {{ tt('Request exchange', '申请换货') }}</button>
                </template>
                <span v-else-if="statusReturnable && avail(it) > 0 && !inReturnWindow" class="tag tag-error">{{ tt('Return window closed (valid return period only)', '已超退货窗口（退货有效期内可退）') }}</span>
                <!-- 评价入口：已发货（3/4/5）展示；提交后置灰 -->
                <button v-if="reviewableStatus" class="btn btn-ghost btn-sm" :class="{ 'rv-done': reviewDone(it) }" :disabled="reviewDone(it)" @click="!reviewDone(it) && toggleReview(it)">
                  {{ reviewDone(it) ? tt('Submitted · pending review', '已提交·审核后展示') : '✍️ ' + tt('Write a review', '写评价') }}
                </button>
              </div>

              <!-- 行内评价表单 -->
              <div v-if="rv.openId === it.id" class="rv-form">
                <div class="rv-stars" role="radiogroup" :aria-label="tt('Rating', '评分')">
                  <button
                    v-for="n in 5" :key="n" type="button" class="rv-star"
                    :class="{ on: n <= rv.rating }" :style="{ '--i': n - 1 }"
                    role="radio" :aria-checked="rv.rating === n" :aria-label="tt(`${n} / 5`, `${n} / 5`)"
                    @click="rv.rating = n"
                  >★</button>
                  <span style="font-size:12px;color:var(--gray);margin-left:6px">{{ rv.rating }} / 5</span>
                </div>
                <textarea v-model="rv.content" class="input" rows="3" maxlength="500" style="height:auto;padding:10px 14px" :placeholder="tt('Share how you like the set — fit, wear, glam…', '说说上手感受：贴合度、耐久度、颜值…')"></textarea>
                <div style="display:flex;justify-content:space-between;font-size:11.5px;color:var(--gray)">
                  <span>{{ tt('Optional · 500 chars max', '选填 · 最多 500 字') }}</span>
                  <span>{{ rv.content.length }}/500</span>
                </div>
                <div class="rv-imgs">
                  <label style="font-size:12.5px;font-weight:600">{{ tt('Photo links (https, up to 6)', '图片链接（https，最多 6 条）') }}</label>
                  <input
                    v-for="(im, idx) in rv.images" :key="idx" v-model="rv.images[idx]" class="input"
                    style="font-size:12.5px" placeholder="https://…"
                  >
                  <div v-if="rvPv.state" class="rv-pv" :class="{ bad: rvPv.state === 'bad' }">
                    <img v-if="rvPv.url" :src="rvPv.url" :alt="tt('Image preview', '图片预览')" @load="rvPvLoad" @error="rvPvError">
                    <span v-if="rvPv.state === 'loading'" class="rv-pv-msg">{{ tt('Checking preview…', '正在检查图片…') }}</span>
                    <span v-else-if="rvPv.state === 'bad'" class="rv-pv-msg" style="color:var(--error)">{{ tt("Couldn't load this image — check the link", '该图片链接无法加载，请检查') }}</span>
                  </div>
                  <button v-if="rv.images.length < 6" type="button" class="btn btn-ghost btn-sm" @click="rv.images.push('')">＋ {{ tt('Add image link', '添加图片链接') }}</button>
                  <button v-if="rv.images.length > 1" type="button" class="btn btn-ghost btn-sm" @click="rv.images.pop()">－ {{ tt('Remove last', '删除最后一条') }}</button>
                  <!-- 上传图片：multipart 上传（原生 fetch），成功把 url 填进上方链接列表 -->
                  <button type="button" class="btn btn-secondary btn-sm" :class="{ loading: rvUploading }" :disabled="rvUploading" @click="rvFile && rvFile.click()">
                    ⬆ {{ rvUploading ? tt('Uploading…', '上传中…') : tt('Upload image (≤5MB)', '上传图片（≤5MB）') }}
                  </button>
                  <input ref="rvFile" type="file" accept="image/png,image/jpeg,image/webp,image/gif" style="display:none" @change="rvUpload">
                </div>
                <div v-if="rv.err" class="field-msg" style="display:block;color:var(--error)" role="alert">{{ rv.err }}</div>
                <div style="display:flex;gap:10px;justify-content:flex-end">
                  <button class="btn btn-ghost btn-sm" @click="rv.openId = null">{{ tt('Cancel', '收起') }}</button>
                  <button class="btn btn-primary btn-sm" :class="{ loading: rv.busy }" :disabled="rv.busy" @click="submitReview(it)">{{ tt('Submit review', '提交评价') }}</button>
                </div>
              </div>
            </div>

            <!-- 金额汇总 -->
            <div style="display:grid;gap:6px;margin-top:12px;font-size:13.5px">
              <div style="display:flex;justify-content:space-between"><span>{{ tt('Subtotal', '小计') }}</span><span>{{ money(o.subtotal) }}</span></div>
              <div v-if="o.discount_total" style="display:flex;justify-content:space-between;color:var(--success)"><span>{{ tt('Discount', '折扣优惠') }}</span><span>-{{ money(o.discount_total) }}</span></div>
              <div v-if="o.points_discount" style="display:flex;justify-content:space-between;color:var(--success)"><span>{{ tt('Points off', '积分抵扣') }}（{{ o.points_used }}）</span><span>-{{ money(o.points_discount) }}</span></div>
              <div v-if="o.giftcard_discount" style="display:flex;justify-content:space-between;color:var(--success)"><span>{{ tt('Gift card', '礼品卡抵扣') }}</span><span>-{{ money(o.giftcard_discount) }}</span></div>
              <div style="display:flex;justify-content:space-between"><span>{{ tt('Shipping', '运费') }}{{ o.shipping_method === 'express' ? tt(' (express)', '（快递）') : '' }}</span><span>{{ o.shipping_fee ? money(o.shipping_fee) : tt('Free', '包邮') }}</span></div>
              <div style="display:flex;justify-content:space-between"><span>{{ tt('Tax', '税费') }}</span><span>{{ money(o.tax) }}</span></div>
              <div class="od-total">
                <span>{{ tt('Total paid', '实付总额') }}</span><span>{{ money(o.grand_total) }}</span>
              </div>
              <div v-if="o.points_earned" style="font-size:12.5px;color:var(--gray)">{{ tt('You earned', '本单获得') }} {{ o.points_earned }} {{ tt('points (unfrozen after delivery)', '积分（确认收货后解冻）') }}</div>
            </div>
          </div>

          <!-- 时间线 -->
          <div class="card" style="padding:20px">
            <h3 style="font-size:15px;margin-bottom:12px">{{ tt('Order activity', '订单动态') }}</h3>
            <div v-if="rmaSubmitted || exSubmitted" style="margin:-4px 0 12px;font-size:13px">
              <router-link to="/account/returns" style="color:var(--plum);font-weight:600">{{ tt('View return / exchange progress →', '查看退换货进度 →') }}</router-link>
            </div>
            <div class="tl-list">
              <div v-for="(t, i) in o.timeline || []" :key="i" style="display:flex;gap:10px;font-size:13px;padding:7px 0">
                <span style="color:var(--gray);flex:none;width:88px">{{ fmt(t.created_at) }}</span>
                <span class="tl-dot" :class="{ now: i === 0 }" :style="{ background: i === 0 ? 'var(--rose)' : 'var(--gray-light)' }"></span>
                <span><b>{{ eventLabel(t) }}</b><span v-if="detailText(t)" style="color:var(--gray)"> · {{ detailText(t) }}</span></span>
              </div>
              <div v-if="!(o.timeline || []).length" style="color:var(--gray);font-size:13px">{{ tt('No activity yet', '暂无动态') }}</div>
            </div>
          </div>
        </div>

        <div style="display:grid;gap:16px;align-content:start">
          <!-- 收货地址（待付/已付/备货 且 未发货 shipping_status===0 可改址） -->
          <div class="card" style="padding:20px">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:10px">
              <h3 style="font-size:15px">{{ tt('Shipping info', '收货信息') }}</h3>
              <button v-if="addrEditable" class="btn btn-secondary btn-sm" @click="openAddr">✏️ {{ tt('Edit address', '修改地址') }}</button>
            </div>
            <div style="font-size:13.5px;line-height:1.7">
              {{ addr.full_name }}<br>
              {{ addr.line1 }} {{ addr.line2 || '' }}<br>
              {{ addr.city }}{{ addr.state ? ', ' + addr.state : '' }} {{ addr.zip }}<br>
              {{ addr.country }}<span v-if="addr.phone"><br>{{ addr.phone }}</span>
            </div>
          </div>

          <!-- 物流 -->
          <div v-if="(o.shipments || []).length || o.tracking_no" class="card" style="padding:20px">
            <h3 style="font-size:15px;margin-bottom:10px">{{ tt('Shipment', '物流') }}</h3>
            <template v-if="(o.shipments || []).length">
              <div v-for="s in o.shipments" :key="s.shipment_no" style="font-size:13.5px;line-height:1.9;padding-bottom:8px;border-bottom:1px dashed var(--gray-light);margin-bottom:8px">
                <b>{{ s.carrier ? s.carrier.toUpperCase() : '—' }}</b> · {{ s.shipment_no }}<br>
                {{ tt('Tracking no.', '追踪号') }} <code v-if="s.tracking_no" style="font-size:12.5px">{{ s.tracking_no }}</code><span v-else>—</span><br>
                <span class="tag" :class="s.status >= 4 ? 'tag-done' : 'tag-ship'">{{ SHIP_ST[s.status] ? tt(SHIP_ST[s.status][0], SHIP_ST[s.status][1]) : s.status }}</span>
              </div>
            </template>
            <div v-else style="font-size:13.5px;color:var(--gray)">{{ tt('Tracking no.', '追踪号') }} {{ o.tracking_no || '—' }}</div>
          </div>

          <!-- 支付记录 -->
          <div v-if="(o.payments || []).length" class="card" style="padding:20px">
            <h3 style="font-size:15px;margin-bottom:10px">{{ tt('Payments', '支付记录') }}</h3>
            <div v-for="p in o.payments" :key="p.id" style="display:flex;justify-content:space-between;align-items:center;font-size:13.5px;padding:6px 0">
              <span>{{ money(p.amount) }}<span v-if="p.refunded_amount" style="color:var(--gray)">（{{ tt('refunded', '已退') }} {{ money(p.refunded_amount) }}）</span></span>
              <span class="tag" :class="PAY_ST[p.status]?.[2]">{{ PAY_ST[p.status] ? tt(PAY_ST[p.status][0], PAY_ST[p.status][1]) : p.status }}</span>
            </div>
          </div>

          <div class="card" style="padding:20px;font-size:12.5px;color:var(--gray);line-height:1.8">
            💡 {{ tt('Returns & exchanges must be requested within the valid return period after payment. Exchanges are always free; return labels are sent after support review.', '退货/换货需在退货有效期内发起；换货永久免费，退货标签由客服审核后发送。') }}
          </div>
        </div>
      </div>
    </div>

    <!-- 退货弹层（开闭走 ui.openModalId：anyOverlay 统一锁滚动，App 根 ESC 委托关闭） -->
    <div v-if="rmaOpen" class="gm-modal-mask" @click.self="closeModal">
      <div
        ref="rmaBox" class="card gm-modal" style="padding:22px;max-width:420px"
        role="dialog" aria-modal="true" :aria-label="tt('Request a return', '申请退货')"
        @keydown="trapKeydown($event, rmaBox)"
      >
        <h3 style="font-size:16px;margin-bottom:6px">{{ tt('Request a return', '申请退货') }}</h3>
        <div style="font-size:12.5px;color:var(--gray);margin-bottom:14px">{{ rma.item?.title }}</div>
        <div class="field"><label>{{ tt(`Return quantity (max ${avail(rma.item)})`, `退货数量（最多 ${avail(rma.item)}）`) }}</label>
          <input v-model.number="rma.qty" class="input" type="number" min="1" step="1" :max="avail(rma.item)">
        </div>
        <div class="field"><label>{{ tt('Reason', '退货原因') }}</label>
          <select v-model.number="rma.reason" class="input">
            <option v-for="(label, v) in RMA_REASON" :key="v" :value="Number(v)">{{ tt(label[0], label[1]) }}</option>
          </select>
        </div>
        <div class="field"><label>{{ tt('Details (optional)', '补充说明（可选）') }}</label>
          <textarea v-model="rma.detail" class="input" rows="3" maxlength="500" style="height:auto;padding:10px 14px" :placeholder="tt('Tell us more…', '告诉我们更多细节…')"></textarea>
        </div>
        <div style="display:flex;gap:10px;justify-content:flex-end">
          <button class="btn btn-ghost" @click="closeModal">{{ tt('Cancel', '取消') }}</button>
          <button class="btn btn-primary" :class="{ loading: rma.busy }" :disabled="rma.busy || !Number.isInteger(rma.qty) || rma.qty < 1 || rma.qty > avail(rma.item)" @click="submitRma">{{ tt('Submit request', '提交申请') }}</button>
        </div>
      </div>
    </div>

    <!-- 换货弹层（siblings 一次拉取 + 数量选择） -->
    <div v-if="exOpen" class="gm-modal-mask" @click.self="closeModal">
      <div
        ref="exBox" class="card gm-modal" style="padding:22px;max-width:460px"
        role="dialog" aria-modal="true" :aria-label="tt('Request an exchange', '申请换货')"
        @keydown="trapKeydown($event, exBox)"
      >
        <h3 style="font-size:16px;margin-bottom:6px">{{ tt('Request an exchange', '申请换货') }}</h3>
        <div style="font-size:12.5px;color:var(--gray);margin-bottom:14px">
          {{ ex.item?.title }} → {{ tt('pick a new variant of the same style', '选择想要更换的新规格（同款其它尺码/颜色）') }}
        </div>
        <div class="field"><label>{{ tt('Exchange quantity', '换货数量') }}（{{ tt('max', '最多') }} {{ avail(ex.item) }}）</label>
          <select v-model.number="ex.qty" class="input" :disabled="avail(ex.item) <= 1">
            <option v-for="n in Math.max(1, avail(ex.item))" :key="n" :value="n">{{ n }}</option>
          </select>
        </div>
        <div v-if="ex.loading" class="skeleton" style="height:120px;border-radius:10px" />
        <template v-else>
          <div v-if="ex.error" style="font-size:13.5px;color:var(--error);padding:10px 0">
            {{ ex.error }}
            <button v-if="ex.netFail" class="btn btn-secondary btn-sm" style="margin-left:10px" @click="loadSiblings">{{ tt('Retry', '重试') }}</button>
          </div>
          <div v-else style="display:grid;gap:8px;max-height:260px;overflow-y:auto">
            <label
              v-for="v in ex.variants" :key="v.id"
              class="ex-opt" :class="{ picked: ex.picked === v.id, disabled: !exSelectable(v) }"
              :style="{
                opacity: exSelectable(v) ? '' : '.55',
                cursor: exSelectable(v) ? 'pointer' : 'not-allowed',
              }"
              @click.prevent="exSelectable(v) && (ex.picked = v.id)"
            >
              <span style="display:flex;align-items:center;gap:8px;min-width:0">
                <input v-model="ex.picked" :value="v.id" type="radio" style="accent-color:var(--plum)" :disabled="!exSelectable(v)" @click.prevent.stop="exSelectable(v) && (ex.picked = v.id)">
                <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ v.option1_value }}{{ v.option2_value ? ' / ' + v.option2_value : '' }}</span>
                <span class="ex-stock" :class="{ out: !exSelectable(v) }">{{ exStockText(v) }}</span>
              </span>
              <span style="color:var(--plum);font-weight:600;flex:none">{{ money(v.price) }} · {{ exDiff(v) }}</span>
            </label>
          </div>
        </template>
        <div class="field" style="margin-top:12px"><label>{{ tt('Reason (optional)', '换货原因（可选）') }}</label>
          <textarea v-model="ex.reason" class="input" rows="2" maxlength="500" style="height:auto;padding:10px 14px" :placeholder="tt('Tell us more…', '告诉我们更多细节…')"></textarea>
        </div>
        <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:14px">
          <button class="btn btn-ghost" @click="closeModal">{{ tt('Cancel', '取消') }}</button>
          <button class="btn btn-primary" :class="{ loading: ex.busy }" :disabled="ex.busy || !ex.picked" @click="submitExchange">{{ tt('Submit exchange request', '提交换货申请') }}</button>
        </div>
      </div>
    </div>

    <!-- 修改地址弹层（开闭走 ui.openModalId：anyOverlay 统一锁滚动，App 根 ESC 委托关闭） -->
    <div v-if="addrOpen" class="gm-modal-mask" @click.self="closeModal">
      <div
        ref="addrBox" class="card gm-modal" style="padding:22px;max-width:460px"
        role="dialog" aria-modal="true" :aria-label="tt('Edit shipping address', '修改收货地址')"
        @keydown="trapKeydown($event, addrBox)"
      >
        <h3 style="font-size:16px;margin-bottom:14px">{{ tt('Edit shipping address', '修改收货地址') }}</h3>
        <div class="field"><label>{{ tt('Recipient name', '收件人姓名') }}</label>
          <input v-model="ad.full_name" class="input" maxlength="100" autocomplete="name">
        </div>
        <div class="field"><label>{{ tt('Street address', '街道地址') }}</label>
          <input v-model="ad.line1" class="input" maxlength="200" autocomplete="address-line1">
        </div>
        <div class="field"><label>{{ tt('Apartment, suite, etc. (optional)', '公寓 / 门牌等（可选）') }}</label>
          <input v-model="ad.line2" class="input" maxlength="200" autocomplete="address-line2">
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
          <div class="field"><label>{{ tt('City', '城市') }}</label>
            <input v-model="ad.city" class="input" maxlength="100" autocomplete="address-level2">
          </div>
          <div class="field"><label>{{ tt('State / region (optional)', '州 / 省份（可选）') }}</label>
            <input v-model="ad.state" class="input" maxlength="100" autocomplete="address-level1">
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
          <div class="field"><label>{{ tt('ZIP code', '邮编') }}</label>
            <input v-model="ad.zip" class="input" maxlength="20" autocomplete="postal-code">
          </div>
          <div class="field"><label>{{ tt('Country', '国家') }}</label>
            <select v-model="ad.country" class="input" autocomplete="country">
              <option v-for="c in COUNTRIES" :key="c[0]" :value="c[0]">{{ c[1] }}</option>
            </select>
          </div>
        </div>
        <div class="field"><label>{{ tt('Phone', '电话') }}</label>
          <input v-model="ad.phone" class="input" maxlength="20" autocomplete="tel" placeholder="+1 555 000 1234">
        </div>
        <div v-if="ad.err" class="field-msg" style="display:block;margin-bottom:10px" role="alert">{{ ad.err }}</div>
        <div style="display:flex;gap:10px;justify-content:flex-end">
          <button class="btn btn-ghost" @click="closeModal">{{ tt('Cancel', '取消') }}</button>
          <button class="btn btn-primary" :class="{ loading: ad.busy }" :disabled="ad.busy" @click="saveAddr">{{ tt('Save address', '保存地址') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gm-modal-mask { position: fixed; inset: 0; background: rgba(31,27,30,.45); display: flex; align-items: center; justify-content: center; z-index: 300; padding: 16px; }
.gm-modal { width: 100%; }
.item-actions { display: flex; gap: 8px; margin-top: 8px; padding-left: 68px; flex-wrap: wrap; align-items: center; }
@media (max-width: 640px) {
  .item-actions { padding-left: 0; }
}

/* 状态圆点向导：圆点间连接线，已过段 --success */
.od-steps { display: flex; gap: 0; margin: 18px 0 6px; }
.od-step { flex: 1; text-align: center; position: relative; }
.od-dot { width: 26px; height: 26px; border-radius: 50%; margin: 0 auto 6px; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 12px; position: relative; z-index: 1; }
.od-step.is-done .od-dot { animation: odDotIn .3s ease-out both; }
@keyframes odDotIn {
  0% { transform: scale(.4); opacity: 0; }
  60% { transform: scale(1.12); }
  100% { transform: scale(1); opacity: 1; }
}
.od-step:not(:last-child)::after { content: ""; position: absolute; top: 13px; left: calc(50% + 16px); width: calc(100% - 32px); height: 2px; background: var(--gray-light); }
.od-step.is-done:not(:last-child)::after { background: var(--success); }
.od-step-label { font-size: 11.5px; }

/* 时间线：列表顶部渐隐 mask + 当前节点光环 */
.tl-list { display: grid; gap: 0; max-height: 280px; overflow-y: auto; -webkit-mask-image: linear-gradient(180deg, transparent 0, #000 16px); mask-image: linear-gradient(180deg, transparent 0, #000 16px); }
.tl-dot { flex: none; width: 4px; height: 4px; border-radius: 50%; margin-top: 7px; }
.tl-dot.now { box-shadow: 0 0 0 4px var(--rose-pale); }

/* 金额汇总：实付总额强调行（17px 等宽数字 plum + 上边 hairline） */
.od-total { display: flex; justify-content: space-between; font-weight: 800; font-size: 17px; border-top: 1px solid var(--gray-light); padding-top: 8px; margin-top: 2px; }
.od-total span { font-variant-numeric: tabular-nums; }
.od-total span:last-child { color: var(--plum); }

/* 评价：已提交置灰 */
.rv-done { color: var(--gray); opacity: .75; cursor: default; }
.rv-form { display: grid; gap: 8px; margin-top: 10px; margin-left: 68px; padding: 14px; border: 1.5px dashed var(--rose); border-radius: 12px; background: var(--rose-pale); }
@media (max-width: 640px) {
  .rv-form { margin-left: 0; }
}
.rv-stars { display: flex; align-items: center; gap: 2px; }
.rv-star { font-size: 26px; line-height: 1; color: var(--gray-light); background: none; border: none; cursor: pointer; padding: 2px; transition: transform .12s ease-out, color .12s; }
.rv-star.on { color: var(--gold); animation: rvStarOn .18s ease-out both; animation-delay: calc(var(--i, 0) * 18ms); }
@keyframes rvStarOn {
  from { transform: scale(.6); opacity: .4; }
  to { transform: scale(1); opacity: 1; }
}
.rv-star:hover { transform: scale(1.15); }
.rv-star:focus-visible { outline: 2px solid var(--plum); outline-offset: 2px; border-radius: 4px; }
.rv-imgs { display: grid; gap: 6px; }

/* 评价图片预览（bad 态红框，拦截提交见 rvCheck） */
.rv-pv { border: 1.5px dashed var(--gray-light); border-radius: 10px; background: var(--cream); min-height: 90px; max-height: 200px; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.rv-pv img { max-width: 100%; max-height: 180px; object-fit: contain; }
.rv-pv.bad { border-color: var(--error); border-style: solid; }
.rv-pv-msg { font-size: 12px; color: var(--gray); padding: 10px; text-align: center; }

/* 换货变体行：picked 态 2px plum 边框 + 柔光 */
.ex-opt { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 10px 12px; border: 1.5px solid var(--gray-light); border-radius: 10px; font-size: 13.5px; }
.ex-opt.picked { border: 2px solid var(--plum); background: var(--rose-pale); box-shadow: 0 2px 10px rgba(138,74,99, .12); padding: 9.5px 11.5px; }
.ex-stock { font-size: 11px; color: var(--gray); background: var(--gray-light); border-radius: 999px; padding: 1px 8px; flex: none; }
.ex-stock.out { color: var(--error); background: var(--pale-error); }
</style>
