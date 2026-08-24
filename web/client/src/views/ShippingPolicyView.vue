<script setup>
import { useTocSpy } from '../composables/useTocSpy'
import { updatedLabel } from '../composables/policyMeta'
import { i18n, tt } from '../i18n'

const SECS = [
  ['rates', 'Rates & speeds', '费率与时效'],
  ['process', 'Processing & tracking', '处理与物流跟踪'],
  ['lost', 'Lost or delayed', '丢件与延误'],
]
const { active } = useTocSpy(SECS.map((s) => s[0]))
function go(id) {
  const el = document.getElementById(id)
  history.replaceState(null, '', '#' + id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
function printPage() { window.print() }
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:960px">
      <h1 class="page-title" style="font-family:var(--font-title);font-size:30px;margin-bottom:6px">{{ tt('Shipping Policy', '配送政策') }}</h1>
      <div class="meta-row">
        <span>{{ updatedLabel(tt) }}</span><span class="meta-dot" /><span>{{ tt('Delivered by USPS / UPS / DHL', '由 USPS / UPS / DHL 承运') }}</span>
        <button class="print-link" type="button" @click="printPage">{{ tt('🖨 Print / Save PDF', '🖨 打印 / 保存 PDF') }}</button>
      </div>
      <div class="policy-grid" style="display:grid;grid-template-columns:200px 1fr;gap:32px">
        <aside class="policy-side">
          <div class="toc-card">
            <span class="toc-title">{{ tt('On this page', '本页目录') }}</span>
            <a v-for="[id, en, zh] in SECS" :key="id" class="toc-link" :class="{ on: active === id }" :href="'#' + id" @click.prevent="go(id)">{{ tt(en, zh) }}</a>
          </div>
        </aside>
        <article class="prose">
          <h2 id="rates" style="scroll-margin-top:84px">{{ tt('Rates & speeds', '费率与时效') }}</h2>
          <!-- v19 移动端补漏：4 列费率表在 375px 强行压列换行难读——外套横滑容器 + min-width（对齐 SizeGuide 表做法） -->
          <div class="rates-wrap">
            <div class="card" style="padding:12px">
              <table style="width:100%;border-collapse:collapse;font-size:13.5px">
                <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:10px">{{ tt('Region', '地区') }}</th><th style="padding:10px">{{ tt('Method', '方式') }}</th><th style="padding:10px">{{ tt('ETA', '时效') }}</th><th style="padding:10px">{{ tt('Fee', '运费') }}</th></tr></thead>
                <tbody>
                  <tr style="border-top:1px solid var(--gray-light)"><td style="padding:10px">🇺🇸 {{ tt('US', '美国') }}</td><td>USPS Standard</td><td>{{ tt('3–6 business days', '3–6 个工作日') }}</td><td>$4.99 — <b>{{ tt('free over $35', '满 $35 包邮') }}</b></td></tr>
                  <tr style="border-top:1px solid var(--gray-light)"><td style="padding:10px">🇺🇸 {{ tt('US', '美国') }}</td><td>UPS Express</td><td>{{ tt('1–3 business days', '1–3 个工作日') }}</td><td>$14.99</td></tr>
                  <tr style="border-top:1px solid var(--gray-light)"><td style="padding:10px">🇨🇦 {{ tt('Canada', '加拿大') }}</td><td>DHL Standard</td><td>{{ tt('4–9 business days', '4–9 个工作日') }}</td><td>{{ tt('Calculated at checkout', '见结算页报价') }}</td></tr>
                  <tr style="border-top:1px solid var(--gray-light)"><td style="padding:10px">🇬🇧 {{ tt('United Kingdom', '英国') }}</td><td>DHL Standard</td><td>{{ tt('5–10 business days', '5–10 个工作日') }}</td><td>{{ tt('Calculated at checkout', '见结算页报价') }}</td></tr>
                  <tr style="border-top:1px solid var(--gray-light)"><td style="padding:10px">🇦🇺 {{ tt('Australia', '澳大利亚') }}</td><td>DHL Standard</td><td>{{ tt('7–14 business days', '7–14 个工作日') }}</td><td>{{ tt('Calculated at checkout', '见结算页报价') }}</td></tr>
                  <tr style="border-top:1px solid var(--gray-light)"><td style="padding:10px">🌍 {{ tt('International', '国际') }}</td><td>DHL Standard</td><td>{{ tt('6–12 business days', '6–12 个工作日') }}</td><td>$12.99</td></tr>
                </tbody>
              </table>
            </div>
          </div>
          <p>{{ tt('We currently ship to the US, Canada, the UK and Australia — CA / UK / AU rates are quoted at checkout based on weight and destination.', '我们目前配送至美国、加拿大、英国与澳大利亚——加 / 英 / 澳运费将在结算页按重量与目的地实时报价。') }}</p>
          <p>{{ tt('Rates above are our standard quotes — the exact fee and free-shipping threshold shown at ', '以上费率为标准报价——结算页显示的确切运费与包邮门槛') }}<b>{{ tt('checkout always apply', '始终适用') }}</b>{{ tt(' (they can be updated by our ops team). Duties and taxes for international orders are the recipient\u2019s responsibility.', '（运营团队可能随时调整）。国际订单的关税与税费由收件人承担。') }}</p>

          <h2 id="process" style="scroll-margin-top:84px">{{ tt('Processing & tracking', '处理与物流跟踪') }}</h2>
          <p>{{ tt('Orders are packed within ', '订单在付款后') }}<b>{{ tt('24 hours', '24 小时') }}</b>{{ tt(' of payment. You\u2019ll get tracking by email the moment your box moves — no login needed to follow it on our ', '内完成打包。包裹一经发出，物流单号即会通过邮件发送——无需登录即可在我们的') }}<router-link to="/track" style="color:var(--plum)">{{ tt('Track Order', '订单跟踪') }}</router-link>{{ tt(' page. Pre-orders and backorders show their ETA on the product page.', '页面查询物流。预售与缺货商品的预计发货时间以商品页显示为准。') }}</p>

          <h2 id="lost" style="scroll-margin-top:84px">{{ tt('Lost or delayed packages', '丢件与延误包裹') }}</h2>
          <p>{{ tt('Parcel stuck 7+ days past the ETA? ', '包裹超过预计时效 7 天以上仍无进展？') }}<router-link to="/contact" style="color:var(--plum)">{{ tt('Contact us', '联系我们') }}</router-link>{{ tt(' — we reship first and investigate second.', '——我们优先补发，其次排查。') }}</p>
        </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
@media (max-width: 768px) {
  .policy-grid { grid-template-columns: 1fr !important; gap: 16px; }
}
/* 费率表横滑（窄屏）：容器出血滚动，表体保 460px 最小可读宽度 */
.rates-wrap { overflow-x: auto; }
.rates-wrap table { min-width: 460px; }
</style>
