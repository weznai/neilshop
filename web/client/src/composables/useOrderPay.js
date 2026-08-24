/* 订单支付 composable（AccountView / OrdersView 共用）：
 * hosted 通道（redirect_url）跳收银台，mock 通道直付；
 * already_paid 幂等忽略（静默刷新），order_not_pending 状态漂移提示后刷新 */
import { ref } from 'vue'
import { req, intentNoChannel } from '../api/client'
import { useUiStore } from '../stores/ui'
import { i18n, tt } from '../i18n'

export function useOrderPay(onPaid) {
  const ui = useUiStore()
  const payingNo = ref('')

  async function pay(o) {
    payingNo.value = o.order_no
    try {
      let provider = ''
      try { provider = (localStorage.getItem('gm_pay_provider') || '').trim() } catch (_) { /* 隐私模式 */ }
      const ib = { order_no: o.order_no }
      if (provider && provider !== 'mock') ib.provider = provider
      const intent = await req('POST', '/api/payments/create-intent', ib)
      if (intentNoChannel(intent)) {
        ui.toast(i18n.t('pay.unsupported_channel'), 'error')
        return
      }
      if (provider !== 'mock' && intent && intent.redirect_url) {
        window.location.href = intent.redirect_url
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
