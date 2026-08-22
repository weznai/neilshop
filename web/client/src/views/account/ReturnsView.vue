<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../../api/client'
import { useUiStore } from '../../stores/ui'
import { useArmConfirm } from '../../composables/useArmConfirm'
import { zulu } from '../../composables/datetime'
import { i18n } from '../../i18n'

const ui = useUiStore()
const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)
const returns = ref([])
const exchanges = ref([])
const loaded = ref(false)
const failed = ref(false)
const cancelingNo = ref('')

/* 两段式确认（useArmConfirm：5s 复位；arm 态红字 + 二段文案） */
const arm = useArmConfirm()

/* RmaStatus：0申请 1批准 2标签已发 3在途 4已收货 5已退款 6拒绝 7部分退款（[en, zh, tag]） */
const RSTATUS = {
  0: ['Requested', '申请中', 'tag-pending'], 1: ['Approved', '已批准', 'tag-paid'], 2: ['Label sent', '标签已发送', 'tag-ship'],
  3: ['In transit', '退货在途', 'tag-ship'], 4: ['Received', '仓库已收货', 'tag-paid'], 5: ['Refunded', '已退款', 'tag-done'],
  6: ['Declined', '已拒绝', 'tag-error'], 7: ['Partially refunded', '部分退款', 'tag-pending'],
}
function rLabel(r) {
  const row = RSTATUS[r.status]
  return row ? tt(row[0], row[1]) : tt('Unknown', '未知')
}
function rClass(r) { return (RSTATUS[r.status] || [])[2] || 'tag-pending' }

/* 换货状态 0-5（后端 status_label 为中文，前端按 status 本地双语；[en, zh, tag]） */
const XSTATUS = {
  0: ['Requested', '申请', 'tag-pending'], 1: ['Approved', '批准', 'tag-paid'], 2: ['Awaiting diff payment', '待差价支付', 'tag-pending'],
  3: ['Shipped', '已发货', 'tag-ship'], 4: ['Completed', '完成', 'tag-done'], 5: ['Declined', '拒绝', 'tag-error'],
}
function xLabel(x) {
  const row = XSTATUS[x.status]
  return row ? tt(row[0], row[1]) : (x.status_label || String(x.status))
}
function xClass(x) { return (XSTATUS[x.status] || [])[2] || 'tag-pending' }
/* RmaReason（[en, zh]） */
const RREASON = {
  1: ['Wrong size', '尺码不合'], 2: ['Quality issue', '质量问题'], 3: ['Not a fit', '不喜欢'],
  4: ['Arrived damaged', '收到损坏'], 5: ['Wrong item shipped', '发错货'], 6: ['Other', '其他'],
}
function rReason(r) {
  const row = RREASON[r.reason]
  return row ? tt(row[0], row[1]) : String(r.reason)
}
/* RMA 正向流程节点（6/7 为终态例外；[en, zh]） */
const RSTEPS = [
  ['Requested', '申请'], ['Approved', '批准'], ['Label', '标签'],
  ['In transit', '在途'], ['Received', '收货'], ['Refund', '退款'],
]
const RSTEP_IDX = { 0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5 }

const money = (c) => (c === null || c === undefined) ? tt('TBD', '待定') : '$' + (c / 100).toFixed(2)
function fmt(iso) {
  if (!iso) return '—'
  const d = new Date(zulu(iso))
  if (isNaN(d)) return '—'
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function load() {
  loaded.value = false
  const [r, x] = await Promise.allSettled([
    req('GET', '/api/returns'),
    req('GET', '/api/exchanges'),
  ])
  if (r.status === 'fulfilled') returns.value = r.value.items || []
  if (x.status === 'fulfilled') exchanges.value = x.value.items || []
  failed.value = r.status === 'rejected' && x.status === 'rejected'
  loaded.value = true
}
onMounted(load)

/* 撤销退货申请（仅 status=0 申请中）：后端删除行 → 刷新列表后自然消失；RSTATUS 映射不动；两段式确认 */
async function cancelRma(r) {
  cancelingNo.value = r.rma_no
  try {
    await req('POST', '/api/returns/' + encodeURIComponent(r.rma_no) + '/cancel')
    ui.toast(tt('Return request withdrawn', '退货申请已撤销'), 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    if (String(d).startsWith('rma_not_cancellable')) ui.toast(tt('This request is already being processed and can no longer be withdrawn', '该申请已在处理中，无法撤销'), 'error')
    else ui.toast(tt('Could not withdraw — please retry later', '撤销失败，请稍后再试'), 'error')
  } finally { cancelingNo.value = '' }
}

/* 撤销换货申请（仅 status=0 申请中）：与 RMA 撤销同构；两段式确认 */
async function cancelExchange(x) {
  cancelingNo.value = x.exchange_no
  try {
    await req('POST', '/api/exchanges/' + encodeURIComponent(x.exchange_no) + '/cancel')
    ui.toast(tt('Exchange request withdrawn', '换货申请已撤销'), 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    if (String(d).startsWith('exchange_not_cancellable')) ui.toast(tt('This request is already being processed and can no longer be withdrawn', '该申请已在处理中，无法撤销'), 'error')
    else ui.toast(tt('Could not withdraw — please retry later', '撤销失败，请稍后再试'), 'error')
  } finally { cancelingNo.value = '' }
}

/* 换货差价支付（仅 status=2）：pay-intent 建单 → 真实 provider 带 redirect 跳转，
   mock（dev）直接确认核销；与订单支付链路同构 */
const payingXNo = ref('')
async function payDiff(x) {
  payingXNo.value = x.exchange_no
  try {
    const d = await req('POST', '/api/exchanges/' + encodeURIComponent(x.exchange_no) + '/pay-intent')
    if (d && d.redirect_url) {
      ui.toast(tt('Redirecting to payment…', '正在跳转支付…'), 'success')
      window.location.href = d.redirect_url
      return
    }
    const r = await req('POST', '/api/exchanges/' + encodeURIComponent(x.exchange_no) + '/mock-pay', { succeed: true })
    ui.toast(r && r.exchange_status === 1
      ? tt('Difference paid — your exchange will ship soon', '差价已支付，换货即将发出')
      : tt('Payment processing', '支付处理中'), 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    if (String(d).startsWith('exchange_not_awaiting_diff') || d === 'diff_already_paid') {
      ui.toast(tt('Status changed — refreshed', '状态已变化，已刷新'), 'error')
      await load()
    } else if (d === 'mock_provider_disabled') {
      ui.toast(tt('Online payment is not available yet — please contact support to pay the difference', '在线支付暂未开通，请联系客服支付差价'), 'error')
    } else {
      ui.toast(tt('Payment failed — please retry later', '支付失败，请稍后再试'), 'error')
    }
  } finally { payingXNo.value = '' }
}
</script>

<template>
  <div>
    <div class="card" style="padding:18px;margin-bottom:16px;font-size:13.5px;color:var(--gray);line-height:1.7">
      ↩️ <b>{{ tt('30-day free returns', '30 天免费退货') }}</b> · <b>{{ tt('Exchanges always free', '换货永久免费') }}</b>{{ tt(' (we reship instantly, you keep the original).', '（新款立即补发，旧款无需寄回）。') }}
      {{ tt('Start from:', '入口：') }}<router-link to="/account/orders" style="color:var(--plum)">{{ tt('Orders', '订单') }}</router-link> → {{ tt('Details → “Return / Exchange”', '详情 → 商品行「申请退货 / 换货」') }}。
    </div>

    <div v-if="!loaded" style="display:grid;gap:12px">
      <div v-for="i in 2" :key="i" class="skeleton" style="height:120px;border-radius:14px" />
    </div>
    <div v-else-if="failed" class="card" style="padding:30px;text-align:center;color:var(--gray)">{{ tt('Load failed — please refresh and retry', '加载失败，请刷新重试') }}</div>

    <template v-else>
      <!-- 退货 RMA -->
      <h3 v-if="returns.length" style="font-size:16px;margin-bottom:12px">{{ tt('Returns', '退货记录') }}</h3>
      <div v-if="returns.length" style="display:grid;gap:12px">
        <div v-for="r in returns" :key="r.rma_no" class="card" style="padding:18px">
          <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:flex-start">
            <div>
              <b>{{ r.rma_no }}</b>
              <div style="font-size:12px;color:var(--gray)">{{ tt('Order', '订单') }} {{ r.order_no }} · {{ fmt(r.created_at) }}</div>
            </div>
            <span class="tag" :class="rClass(r)">{{ rLabel(r) }}</span>
            <div style="text-align:right">
              <b style="color:var(--plum)">{{ money(r.refund_amount) }}</b>
              <div style="font-size:12px;color:var(--gray)">{{ tt('Est. refund', '预计退款') }}</div>
            </div>
          </div>

          <div v-if="r.item" style="display:flex;gap:10px;align-items:center;margin:10px 0;padding:8px 0;border-top:1px dashed var(--gray-light)">
            <img v-if="r.item.image" :src="r.item.image" :alt="r.item.title" style="width:40px;height:40px;border-radius:8px;object-fit:cover">
            <div style="flex:1;font-size:13px">
              <b>{{ r.item.title }}</b>
              <div style="color:var(--gray);font-size:12px">× {{ r.qty }} · {{ rReason(r) }}<span v-if="r.reason_detail">（{{ r.reason_detail }}）</span></div>
            </div>
            <button
              v-if="r.status === 0" class="btn btn-ghost btn-sm"
              :class="{ arm: arm.is(r.rma_no), loading: cancelingNo === r.rma_no }"
              :disabled="!!cancelingNo" @click="arm.hit(r.rma_no, () => cancelRma(r))"
            >{{ arm.is(r.rma_no) ? tt('Tap again to confirm', '再点一次确认') : tt('Withdraw', '撤销申请') }}</button>
            <a v-if="r.label_url" class="btn btn-secondary btn-sm" :href="r.label_url" target="_blank" rel="noopener">🖨 {{ tt('Print return label', '打印退货标签') }}</a>
          </div>

          <!-- 进度条（拒绝/部分退款单独提示） -->
          <div v-if="RSTEP_IDX[r.status] !== undefined" style="display:flex;gap:0;margin-top:8px">
            <div v-for="(s, i) in RSTEPS" :key="s[1]" style="flex:1;text-align:center">
              <div :style="{ background: i <= RSTEP_IDX[r.status] ? 'var(--plum)' : 'var(--gray-light)' }" style="height:5px;border-radius:3px;margin:0 3px"></div>
              <div style="font-size:11px;margin-top:4px" :style="{ color: i <= RSTEP_IDX[r.status] ? 'var(--ink)' : 'var(--gray)', fontWeight: i === RSTEP_IDX[r.status] ? '700' : '' }">{{ tt(s[0], s[1]) }}</div>
            </div>
          </div>
          <div v-else-if="r.status === 7" style="font-size:12.5px;color:var(--warn);margin-top:8px">⚠️ {{ tt('Partial refund completed', '部分退款已完成') }}{{ r.refunded_at ? ' · ' + fmt(r.refunded_at) : '' }}</div>
          <div v-else style="font-size:12.5px;color:var(--error);margin-top:8px">✖ {{ tt('This request was declined —', '申请已被拒绝，如有疑问请') }}<router-link to="/contact" style="color:var(--plum)">{{ tt('contact support', '联系客服') }}</router-link></div>
        </div>
      </div>

      <!-- 换货 -->
      <h3 v-if="exchanges.length" style="font-size:16px;margin:22px 0 12px">{{ tt('Exchanges', '换货记录') }}</h3>
      <div v-if="exchanges.length" style="display:grid;gap:12px">
        <div v-for="x in exchanges" :key="x.exchange_no" class="card" style="padding:18px">
          <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:flex-start">
            <div>
              <b>{{ x.exchange_no }}</b>
              <div style="font-size:12px;color:var(--gray)">{{ tt('Order', '订单') }} {{ x.order_no }} · {{ fmt(x.created_at) }}</div>
            </div>
            <span class="tag" :class="xClass(x)">{{ xLabel(x) }}</span>
            <span v-if="x.price_diff > 0" class="tag tag-pending">{{ tt(`Pay difference $${(x.price_diff / 100).toFixed(2)}`, `需补差价 $${(x.price_diff / 100).toFixed(2)}`) }}</span>
            <span v-else-if="x.price_diff < 0" class="tag tag-paid">{{ tt(`Refund difference $${(-x.price_diff / 100).toFixed(2)}`, `退差价 $${(-x.price_diff / 100).toFixed(2)}`) }}</span>
          </div>
          <div style="display:flex;gap:10px;align-items:center;margin-top:10px;padding-top:10px;border-top:1px dashed var(--gray-light);font-size:13px;flex-wrap:wrap">
            <span v-if="x.old_variant" style="color:var(--gray)">{{ x.old_variant.title }}</span>
            <span v-if="x.old_variant && x.new_variant">→</span>
            <b v-if="x.new_variant">{{ x.new_variant.title }}</b>
            <span v-if="x.new_variant" style="color:var(--gray)">（{{ '$' + (x.new_variant.price / 100).toFixed(2) }}）</span>
          </div>
          <div v-if="x.status === 2" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:8px">
            <button
              class="btn btn-primary btn-sm" :class="{ loading: payingXNo === x.exchange_no }"
              :disabled="payingXNo === x.exchange_no || !!cancelingNo" @click="payDiff(x)"
            >💳 {{ tt(`Pay difference $${(x.price_diff / 100).toFixed(2)}`, `支付差价 $${(x.price_diff / 100).toFixed(2)}`) }}</button>
            <span style="font-size:12.5px;color:var(--gray)">{{ tt('Prefer help?', '需要帮助？') }}<router-link to="/contact" style="color:var(--plum)">{{ tt('contact support', '联系客服') }}</router-link></span>
          </div>
          <div v-if="x.status === 0" style="margin-top:8px">
            <button
              class="btn btn-ghost btn-sm" :class="{ arm: arm.is(x.exchange_no), loading: cancelingNo === x.exchange_no }"
              :disabled="!!cancelingNo || !!payingXNo" @click="arm.hit(x.exchange_no, () => cancelExchange(x))"
            >{{ arm.is(x.exchange_no) ? tt('Tap again to confirm', '再点一次确认') : tt('Withdraw', '撤销申请') }}</button>
          </div>
        </div>
      </div>

      <div v-if="!returns.length && !exchanges.length" class="card" style="padding:30px;text-align:center;color:var(--gray)">
        {{ tt('No returns or exchanges yet 💅', '暂无退换货记录 💅') }}
      </div>
    </template>
  </div>
</template>
