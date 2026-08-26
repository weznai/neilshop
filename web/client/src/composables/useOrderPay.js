/* 订单支付 composable（AccountView / OrdersView 共用）：
 * hosted 通道（redirect_url）跳收银台，mock 通道直付；
 * already_paid 幂等忽略（静默刷新），order_not_pending 状态漂移提示后刷新 */
import { ref } from 'vue'
import { req, intentNoChannel } from '../api/client'
import { useUiStore } from '../stores/ui'
import { i18n, tt } from '../i18n'

/* create-intent 统一入口（Checkout/Success/GiftCards/订单支付共用）：
 * provider 优先取调用方显式选择（结算页 paySel），否则读 gm_pay_provider；
 * 发起前先与 /api/payments/methods 对账——通道已下线则弃参回落后端默认并清除存储；
 * 响应 detail 含 provider_unavailable 时同样清存储并去参重试一次 */
export async function createOrderIntent(orderNo, email, providerSel) {
  const ui = useUiStore()
  let provider = providerSel != null ? String(providerSel).trim() : ''
  if (!provider) {
    try { provider = (localStorage.getItem('gm_pay_provider') || '').trim() } catch (_) { /* 隐私模式 */ }
  }
  if (provider && provider !== 'mock') {
    try {
      const d = await req('GET', '/api/payments/methods')
      const ids = (d.providers || []).map((p) => p.id)
      if (ids.length && !ids.includes(provider)) {
        provider = ''
        try { localStorage.removeItem('gm_pay_provider') } catch (_) { /* 隐私模式 */ }
      }
    } catch (_) { /* methods 拉取失败不拦截支付 */ }
  }
  const base = { order_no: orderNo }
  if (email) base.email = email
  const ib = { ...base }
  if (provider && provider !== 'mock') ib.provider = provider
  try {
    return await req('POST', '/api/payments/create-intent', ib)
  } catch (e) {
    const m = String((e.data && e.data.detail) || e.message || '')
    if (ib.provider && m.includes('provider_unavailable')) {
      try { localStorage.removeItem('gm_pay_provider') } catch (_) { /* 隐私模式 */ }
      ui.toast(i18n.t('pay.providerGone'), 'error')
      return await req('POST', '/api/payments/create-intent', base)
    }
    throw e
  }
}

export function useOrderPay(onPaid) {
  const ui = useUiStore()
  const payingNo = ref('')

  async function pay(o) {
    payingNo.value = o.order_no
    try {
      const intent = await createOrderIntent(o.order_no)
      if (intentNoChannel(intent)) {
        ui.toast(i18n.t('pay.unsupported_channel'), 'error')
        return
      }
      if (intent && intent.redirect_url) {
        window.location.href = intent.redirect_url
        setTimeout(() => {
          if (document.visibilityState !== 'hidden') {
            payingNo.value = ''
            ui.toast(tt('Redirecting to payment… if nothing happened, please retry', '正在跳转支付…若未打开请重试'), 'error')
          }
        }, 3000)
        return
      }
      const d = await req('POST', '/api/payments/mock-pay', { order_no: o.order_no, succeed: true })
      ui.toast(d.order_status === 1 ? tt('Payment successful — points will be credited after confirmation', '支付成功，积分将在确认后发放') : tt('Payment processing', '支付处理中'), 'success')
      await onPaid()
    } catch (e) {
      const d = e && e.data && e.data.detail || ''
      if (String(d).startsWith('order_not_pending')) { ui.toast(tt('Order status changed — refreshed', '订单状态已变化，已刷新'), 'error'); await onPaid() }
      else if (d === 'already_paid') { await onPaid() }
      else ui.toast(tt('Payment failed — please retry later', '支付失败，请稍后再试'), 'error')
    } finally { payingNo.value = '' }
  }

  return { payingNo, pay }
}
