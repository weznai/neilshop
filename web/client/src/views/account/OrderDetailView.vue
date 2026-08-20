<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../../api/client'
import { useUiStore } from '../../stores/ui'
import { statusLabel, statusTag } from '../../composables/orderStatus'
import { i18n } from '../../i18n'

const route = useRoute()
const ui = useUiStore()
const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)
const o = ref(null)
const err = ref('')
const loading = ref(true)
const busy = ref(false)

/* OrderStatus 共享映射（composables/orderStatus.js）：0待付 1已付 2备货 3已发货 4已送达 5已完成 8已取消 9已退款 */
/* RmaReason 1-6 */
const RMA_REASON = { 1: '尺码不合', 2: '质量问题', 3: '不喜欢', 4: '收到损坏', 5: '发错货', 6: '其他' }
/* ShipmentStatus */
const SHIP_ST = { 0: '待打单', 1: '已打单', 2: '待交接', 3: '运输中', 4: '已送达', 5: '异常', 6: '面单作废' }
/* PaymentStatus */
const PAY_ST = { 0: ['待支付', 'tag-pending'], 1: ['成功', 'tag-paid'], 2: ['失败', 'tag-error'], 3: ['已退款', 'tag-error'], 4: ['部分退款', 'tag-pending'] }
/* 时间线事件 → 中文 */
const EVENT_LABEL = {
  status_changed: '状态变更', payment_succeeded: '支付成功', payment_failed: '支付失败',
  rma_created: '退货申请', exchange_created: '换货申请', exchange_approved: '换货已批准',
  exchange_rejected: '换货被拒绝', exchange_diff_paid: '换货差价已支付', exchange_shipped: '换货已发货',
  exchange_completed: '换货完成', points_granted: '积分发放', tracking_updated: '物流更新',
  note_added: '备注', email_sent: '邮件通知', ticket_linked: '关联工单', label_voided: '面单作废',
}

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
function fmt(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d)) return '—'
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function detailText(ev) {
  const d = ev.detail
  if (!d) return ''
  if (ev.event === 'status_changed' && d.to !== undefined) {
    return `${statusLabel(d.from)} → ${statusLabel(d.to)}`
  }
  if (typeof d === 'object') {
    return Object.entries(d).filter(([k]) => k !== 'code').slice(0, 3)
      .map(([k, v]) => `${k}: ${v}`).join(' · ')
  }
  return String(d)
}

async function load() {
  const no = route.query.no
  if (!no) { err.value = '缺少订单号'; loading.value = false; return }
  try {
    o.value = await req('GET', '/api/orders/' + encodeURIComponent(no))
  } catch (e) {
    err.value = e && e.status === 404 ? '订单不存在' : '订单加载失败，请稍后再试'
  } finally { loading.value = false }
}
onMounted(load)

/* 进度条仅用于正常履约流（0-5）；取消/退款单独展示 */
const steps = computed(() => {
  if (!o.value) return []
  const labels = ['下单', '支付', '备货', '发货', '送达']
  const s = o.value.status
  if (![0, 1, 2, 3, 4, 5].includes(s)) return []
  const upto = Math.min(s, 4)
  return labels.map((l, i) => ({ l, done: i <= upto, now: i === upto }))
})
const addr = computed(() => o.value?.shipping_address || {})
/* 可退换：已付且未取消/退款（后端 RETURNABLE_STATUSES {1,2,3,4,5}） */
const statusReturnable = computed(() => !!o.value && [1, 2, 3, 4, 5].includes(o.value.status))
/* 30 天退货窗口预判（按 paid_at，缺失回落 placed_at；与后端 return_days=30 口径一致） */
const inReturnWindow = computed(() => {
  const ov = o.value
  if (!ov) return false
  const base = ov.paid_at || ov.placed_at
  if (!base) return true
  const t = new Date(base).getTime()
  return isNaN(t) ? true : Date.now() - t <= 30 * 86400000
})
const returnable = computed(() => statusReturnable.value && inReturnWindow.value)
function avail(it) { return (it.qty || 0) - (it.refunded_qty || 0) - (it.exchanged_qty || 0) }

/* 待付订单：支付（create-intent → mock-pay）/ 取消 */
async function payNow() {
  busy.value = true
  try {
    await req('POST', '/api/payments/create-intent', { order_no: o.value.order_no })
    const d = await req('POST', '/api/payments/mock-pay', { order_no: o.value.order_no, succeed: true })
    ui.toast(d.order_status === 1 ? '支付成功 🎉' : '支付处理中', 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    if (String(d).startsWith('order_not_pending') || d === 'already_paid') { ui.toast('订单状态已变化，已刷新', 'error'); await load() }
    else ui.toast('支付失败，请稍后再试', 'error')
  } finally { busy.value = false }
}
async function cancelOrder() {
  if (!window.confirm(`确认取消订单 ${o.value.order_no}？`)) return
  busy.value = true
  try {
    await req('POST', '/api/orders/' + encodeURIComponent(o.value.order_no) + '/cancel', { reason: 'user' })
    ui.toast('订单已取消', 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    ui.toast(String(d).startsWith('not_cancellable') ? '该订单当前状态不可取消' : '取消失败，请稍后再试', 'error')
  } finally { busy.value = false }
}

/* ---------- 退货 RMA ---------- */
const rma = reactive({ open: false, item: null, qty: 1, reason: 1, detail: '', busy: false })
function openRma(it) {
  Object.assign(rma, { open: true, item: it, qty: 1, reason: 1, detail: '', busy: false })
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
    ui.toast(`退货申请已提交（${d.rma_no}），请耐心等待审核`, 'success')
    rma.open = false
    await load()
  } catch (e) {
    const d = (e && e.data && e.data.detail) || ''
    if (String(d).startsWith('not_returnable')) ui.toast('该订单当前状态不可退货', 'error')
    else if (d === 'return_window_closed') ui.toast('退货窗口已关闭（下单后 30 天内可退）', 'error')
    else if (String(d).startsWith('qty_exceeds_available')) ui.toast('退货数量超出可退数量', 'error')
    else ui.toast('退货申请失败，请稍后再试', 'error')
  } finally { rma.busy = false }
}

/* ---------- 换货（new_variant_id）---------- */
const ex = reactive({ open: false, item: null, loading: false, variants: [], picked: null, busy: false, error: '' })
async function openExchange(it) {
  Object.assign(ex, { open: true, item: it, loading: true, variants: [], picked: null, busy: false, error: '' })
  /* 通过商品标题前缀搜商品 → 定位含旧变体的商品 → 列出其它在售变体 */
  const base = (it.title || '').split(' · ')[0].trim()
  try {
    const q = await req('GET', '/api/catalog/products?q=' + encodeURIComponent(base) + '&size=20')
    for (const p of q.items || []) {
      const d = await req('GET', '/api/catalog/products-by-id/' + p.id)
      const vs = d.variants || []
      if (vs.some((v) => v.id === it.variant_id)) {
        ex.variants = vs.filter((v) => v.id !== it.variant_id && v.stock > 0)
        break
      }
    }
  } catch (_) { /* 商品可能已下架 */ }
  if (!ex.variants.length) ex.error = '未找到同款其它在售规格（商品可能已下架或无库存）'
  ex.loading = false
}
function exDiff(v) {
  const diff = (v.price || 0) - (ex.item?.unit_price || 0)
  if (diff > 0) return `需补差价 ${money(diff)}`
  if (diff < 0) return `退差价 ${money(-diff)}`
  return '同价换货'
}
async function submitExchange() {
  if (!ex.picked) return
  ex.busy = true
  try {
    const d = await req('POST', '/api/exchanges', {
      order_no: o.value.order_no,
      order_item_id: ex.item.id,
      new_variant_id: ex.picked,
    })
    ui.toast(`换货申请已提交（${d.exchange_no}）`, 'success')
    ex.open = false
    await load()
  } catch (e) {
    const d = (e && e.data && e.data.detail) || ''
    if (String(d).startsWith('not_exchangeable')) ui.toast('该订单当前状态不可换货', 'error')
    else if (d === 'return_window_closed') ui.toast('换货窗口已关闭', 'error')
    else if (String(d).startsWith('qty_exceeds_available')) ui.toast(tt('Insufficient quantity available for exchange', '可换数量不足'), 'error')
    else if (d === 'variant_out_of_stock') ui.toast('新规格库存不足，请重选', 'error')
    else if (d === 'variant_not_found') ui.toast('所选规格不存在，请重选', 'error')
    else ui.toast('换货申请失败，请稍后再试', 'error')
  } finally { ex.busy = false }
}
</script>

<template>
  <div>
    <div v-if="err" class="card" style="padding:30px;text-align:center;color:var(--gray)">
      {{ err }}
      <div style="margin-top:10px"><router-link class="btn btn-secondary btn-sm" to="/account/orders">← 返回订单列表</router-link></div>
    </div>
    <div v-else-if="loading" style="display:grid;gap:16px">
      <div class="skeleton" style="height:110px;border-radius:14px" />
      <div class="skeleton" style="height:260px;border-radius:14px" />
    </div>

    <div v-else style="display:grid;gap:16px">
      <!-- 头部 + 进度 -->
      <div class="card" style="padding:20px">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
          <div>
            <h2 style="font-family:var(--font-title);font-size:22px">{{ o.order_no }}</h2>
            <div style="font-size:12.5px;color:var(--gray)">下单 {{ fmt(o.placed_at) }}<span v-if="o.paid_at"> · 支付 {{ fmt(o.paid_at) }}</span></div>
          </div>
          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
            <span class="tag" :class="statusTag(o.status)">{{ statusLabel(o.status) }}</span>
            <template v-if="o.status === 0">
              <button class="btn btn-primary btn-sm" :class="{ loading: busy }" :disabled="busy" @click="payNow">去支付 {{ money(o.grand_total) }}</button>
              <button class="btn btn-ghost btn-sm" style="color:var(--error)" :disabled="busy" @click="cancelOrder">取消订单</button>
            </template>
          </div>
        </div>
        <div v-if="steps.length" style="display:flex;gap:0;margin:18px 0 6px">
          <div v-for="(s, i) in steps" :key="i" style="flex:1;text-align:center;position:relative">
            <div :style="{ background: s.done ? 'var(--success)' : 'var(--gray-light)' }" style="width:26px;height:26px;border-radius:50%;margin:0 auto 6px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:12px">
              {{ s.done ? '✓' : i + 1 }}
            </div>
            <div style="font-size:11.5px" :style="{ color: s.done ? 'var(--ink)' : 'var(--gray)', fontWeight: s.now ? '700' : '' }">{{ s.l }}</div>
          </div>
        </div>
        <div v-else style="margin-top:14px;padding:10px 14px;border-radius:10px;background:#FDE9EA;color:var(--error);font-size:13.5px;font-weight:600">
          {{ o.status === 8 ? '订单已取消' : '订单已退款' }}
        </div>
      </div>

      <div class="grid-m-1" style="display:grid;grid-template-columns:1.4fr 1fr;gap:16px">
        <div style="display:grid;gap:16px">
          <!-- 商品 -->
          <div class="card" style="padding:20px">
            <h3 style="font-size:15px;margin-bottom:12px">商品</h3>
            <div v-for="it in o.items || []" :key="it.id" style="padding:12px 0;border-bottom:1px solid var(--gray-light)">
              <div style="display:flex;gap:12px;align-items:center">
                <img :src="it.image" :alt="it.title" style="width:56px;height:56px;border-radius:9px;object-fit:cover">
                <div style="flex:1;font-size:13.5px;min-width:0">
                  <b style="display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ it.title }}</b>
                  <div style="color:var(--gray);font-size:12px">
                    {{ money(it.unit_price) }} × {{ it.qty }}
                    <span v-if="it.refunded_qty" class="tag tag-error" style="margin-left:6px">已退 {{ it.refunded_qty }}</span>
                    <span v-if="it.exchanged_qty" class="tag tag-ship" style="margin-left:6px">已换 {{ it.exchanged_qty }}</span>
                  </div>
                </div>
                <b style="font-size:13.5px">{{ money(it.subtotal) }}</b>
              </div>
              <div v-if="statusReturnable && avail(it) > 0" class="item-actions">
                <template v-if="inReturnWindow">
                  <button class="btn btn-ghost btn-sm" @click="openRma(it)">↩️ 申请退货（可退 {{ avail(it) }}）</button>
                  <button class="btn btn-ghost btn-sm" @click="openExchange(it)">🔁 申请换货</button>
                </template>
                <span v-else class="tag tag-error">{{ tt('Return window closed (30 days after payment)', '已超退货窗口（支付后 30 天）') }}</span>
              </div>
            </div>

            <!-- 金额汇总 -->
            <div style="display:grid;gap:6px;margin-top:12px;font-size:13.5px">
              <div style="display:flex;justify-content:space-between"><span>小计</span><span>{{ money(o.subtotal) }}</span></div>
              <div v-if="o.discount_total" style="display:flex;justify-content:space-between;color:var(--success)"><span>折扣优惠</span><span>-{{ money(o.discount_total) }}</span></div>
              <div v-if="o.points_discount" style="display:flex;justify-content:space-between;color:var(--success)"><span>积分抵扣（{{ o.points_used }} 分）</span><span>-{{ money(o.points_discount) }}</span></div>
              <div v-if="o.giftcard_discount" style="display:flex;justify-content:space-between;color:var(--success)"><span>礼品卡抵扣</span><span>-{{ money(o.giftcard_discount) }}</span></div>
              <div style="display:flex;justify-content:space-between"><span>运费{{ o.shipping_method === 'express' ? '（快递）' : '' }}</span><span>{{ o.shipping_fee ? money(o.shipping_fee) : '包邮' }}</span></div>
              <div style="display:flex;justify-content:space-between"><span>税费</span><span>{{ money(o.tax) }}</span></div>
              <div style="display:flex;justify-content:space-between;font-weight:800;font-size:15px;border-top:1px solid var(--gray-light);padding-top:6px">
                <span>实付总额</span><span style="color:var(--plum)">{{ money(o.grand_total) }}</span>
              </div>
              <div v-if="o.points_earned" style="font-size:12.5px;color:var(--gray)">本单获得 {{ o.points_earned }} 积分（确认收货后解冻）</div>
            </div>
          </div>

          <!-- 时间线 -->
          <div class="card" style="padding:20px">
            <h3 style="font-size:15px;margin-bottom:12px">订单动态</h3>
            <div style="display:grid;gap:0;max-height:280px;overflow-y:auto">
              <div v-for="(t, i) in o.timeline || []" :key="i" style="display:flex;gap:10px;font-size:13px;padding:7px 0">
                <span style="color:var(--gray);flex:none;width:88px">{{ fmt(t.created_at) }}</span>
                <span style="flex:none;width:4px;height:4px;border-radius:50%;background:var(--rose);margin-top:7px"></span>
                <span><b>{{ EVENT_LABEL[t.event] || t.event }}</b><span v-if="detailText(t)" style="color:var(--gray)"> · {{ detailText(t) }}</span></span>
              </div>
              <div v-if="!(o.timeline || []).length" style="color:var(--gray);font-size:13px">暂无动态</div>
            </div>
          </div>
        </div>

        <div style="display:grid;gap:16px;align-content:start">
          <!-- 收货地址 -->
          <div class="card" style="padding:20px">
            <h3 style="font-size:15px;margin-bottom:10px">收货信息</h3>
            <div style="font-size:13.5px;line-height:1.7">
              {{ addr.full_name }}<br>
              {{ addr.line1 }} {{ addr.line2 || '' }}<br>
              {{ addr.city }}{{ addr.state ? ', ' + addr.state : '' }} {{ addr.zip }}<br>
              {{ addr.country }}<span v-if="addr.phone"><br>{{ addr.phone }}</span>
            </div>
          </div>

          <!-- 物流 -->
          <div v-if="(o.shipments || []).length || o.tracking_no" class="card" style="padding:20px">
            <h3 style="font-size:15px;margin-bottom:10px">物流</h3>
            <template v-if="(o.shipments || []).length">
              <div v-for="s in o.shipments" :key="s.shipment_no" style="font-size:13.5px;line-height:1.9;padding-bottom:8px;border-bottom:1px dashed var(--gray-light);margin-bottom:8px">
                <b>{{ (s.carrier || '').toUpperCase() }}</b> · {{ s.shipment_no }}<br>
                追踪号 <code style="font-size:12.5px">{{ s.tracking_no }}</code><br>
                <span class="tag" :class="s.status >= 4 ? 'tag-done' : 'tag-ship'">{{ SHIP_ST[s.status] || s.status }}</span>
              </div>
            </template>
            <div v-else style="font-size:13.5px;color:var(--gray)">追踪号 {{ o.tracking_no || '—' }}</div>
          </div>

          <!-- 支付记录 -->
          <div v-if="(o.payments || []).length" class="card" style="padding:20px">
            <h3 style="font-size:15px;margin-bottom:10px">支付记录</h3>
            <div v-for="p in o.payments" :key="p.id" style="display:flex;justify-content:space-between;align-items:center;font-size:13.5px;padding:6px 0">
              <span>{{ money(p.amount) }}<span v-if="p.refunded_amount" style="color:var(--gray)">（已退 {{ money(p.refunded_amount) }}）</span></span>
              <span class="tag" :class="PAY_ST[p.status]?.[1]">{{ PAY_ST[p.status]?.[0] || p.status }}</span>
            </div>
          </div>

          <div class="card" style="padding:20px;font-size:12.5px;color:var(--gray);line-height:1.8">
            💡 退货/换货需在支付后 30 天内发起；换货永久免费，退货标签由客服审核后发送。
          </div>
        </div>
      </div>
    </div>

    <!-- 退货弹层 -->
    <div v-if="rma.open" class="gm-modal-mask" @click.self="rma.open = false">
      <div class="card gm-modal" style="padding:22px;max-width:420px">
        <h3 style="font-size:16px;margin-bottom:6px">申请退货</h3>
        <div style="font-size:12.5px;color:var(--gray);margin-bottom:14px">{{ rma.item?.title }}</div>
        <div class="field"><label>退货数量（最多 {{ avail(rma.item) }}）</label>
          <input v-model.number="rma.qty" class="input" type="number" min="1" :max="avail(rma.item)">
        </div>
        <div class="field"><label>退货原因</label>
          <select v-model.number="rma.reason" class="input">
            <option v-for="(label, v) in RMA_REASON" :key="v" :value="Number(v)">{{ label }}</option>
          </select>
        </div>
        <div class="field"><label>补充说明（可选）</label>
          <textarea v-model="rma.detail" class="input" rows="3" maxlength="500" style="height:auto;padding:10px 14px" placeholder="告诉我们更多细节…"></textarea>
        </div>
        <div style="display:flex;gap:10px;justify-content:flex-end">
          <button class="btn btn-ghost" @click="rma.open = false">取消</button>
          <button class="btn btn-primary" :class="{ loading: rma.busy }" :disabled="rma.busy || rma.qty < 1 || rma.qty > avail(rma.item)" @click="submitRma">提交申请</button>
        </div>
      </div>
    </div>

    <!-- 换货弹层 -->
    <div v-if="ex.open" class="gm-modal-mask" @click.self="ex.open = false">
      <div class="card gm-modal" style="padding:22px;max-width:460px">
        <h3 style="font-size:16px;margin-bottom:6px">申请换货</h3>
        <div style="font-size:12.5px;color:var(--gray);margin-bottom:14px">
          {{ ex.item?.title }} → 选择想要更换的新规格（同款其它尺码/颜色）
        </div>
        <div v-if="ex.loading" class="skeleton" style="height:120px;border-radius:10px" />
        <template v-else>
          <div v-if="ex.error" style="font-size:13.5px;color:var(--error);padding:10px 0">{{ ex.error }}</div>
          <div v-else style="display:grid;gap:8px;max-height:260px;overflow-y:auto">
            <label v-for="v in ex.variants" :key="v.id" style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 12px;border:1.5px solid var(--gray-light);border-radius:10px;cursor:pointer;font-size:13.5px"
              :style="{ borderColor: ex.picked === v.id ? 'var(--plum)' : '', background: ex.picked === v.id ? 'var(--rose-pale)' : '' }">
              <span style="display:flex;align-items:center;gap:8px">
                <input v-model="ex.picked" :value="v.id" type="radio" style="accent-color:var(--plum)">
                {{ v.option1_value }}{{ v.option2_value ? ' / ' + v.option2_value : '' }}
              </span>
              <span style="color:var(--plum);font-weight:600">{{ money(v.price) }} · {{ exDiff(v) }}</span>
            </label>
          </div>
        </template>
        <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:14px">
          <button class="btn btn-ghost" @click="ex.open = false">取消</button>
          <button class="btn btn-primary" :class="{ loading: ex.busy }" :disabled="ex.busy || !ex.picked" @click="submitExchange">提交换货申请</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gm-modal-mask { position: fixed; inset: 0; background: rgba(31,27,30,.45); display: flex; align-items: center; justify-content: center; z-index: 60; padding: 16px; }
.gm-modal { width: 100%; }
.item-actions { display: flex; gap: 8px; margin-top: 8px; padding-left: 68px; flex-wrap: wrap; align-items: center; }
@media (max-width: 640px) {
  .item-actions { padding-left: 0; }
}
</style>
