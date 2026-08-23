<script setup>
import { useTocSpy } from '../composables/useTocSpy'
import { i18n, tt } from '../i18n'

const SECS = [
  ['orders', '1 · Orders & payment', '1 · 订单与支付'],
  ['shipping', '2 · Shipping', '2 · 配送'],
  ['returns', '3 · Returns & exchanges', '3 · 退换货'],
  ['ip', '4 · Intellectual property', '4 · 知识产权'],
  ['liability', '5 · Liability', '5 · 责任'],
  ['law', '6 · Governing law', '6 · 适用法律'],
]
const { active } = useTocSpy(SECS.map((s) => s[0]))
function go(id) {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
function printPage() { window.print() }
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:960px">
      <h1 class="page-title" style="font-family:var(--font-title);font-size:30px;margin-bottom:6px">{{ tt('Terms of Service', '服务条款') }}</h1>
      <div class="meta-row">
        <span>{{ tt('Last updated: Aug 2026', '最后更新：2026 年 8 月') }}</span><span class="meta-dot" /><span>{{ tt('By using glowmag.com you agree to these terms', '使用 glowmag.com 即表示你同意以下条款') }}</span>
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
          <h2 id="orders" style="scroll-margin-top:90px">{{ tt('1 · Orders & payment', '1 · 订单与支付') }}</h2>
          <p>{{ tt('An order is an offer to purchase; the contract forms when we confirm shipment. Prices in USD; taxes calculated at checkout. We may cancel and refund orders affected by pricing errors or stock-outs.', '下单即为购买要约；合同在我们确认发货时成立。价格以美元计价；税费在结算时计算。因定价错误或缺货受影响的订单，我们可能会取消并退款。') }}</p>
          <h2 id="shipping" style="scroll-margin-top:90px">{{ tt('2 · Shipping', '2 · 配送') }}</h2>
          <p>{{ tt('See our ', '请参阅我们的') }}<router-link to="/shipping-policy" style="color:var(--plum)">{{ tt('Shipping Policy', '配送政策') }}</router-link>{{ tt('. Risk passes to you on delivery to the carrier.', '。货物交付承运人后，风险转移至你。') }}</p>
          <h2 id="returns" style="scroll-margin-top:90px">{{ tt('3 · Returns & exchanges', '3 · 退换货') }}</h2>
          <p>{{ tt('See our ', '请参阅我们的') }}<router-link to="/returns-policy" style="color:var(--plum)">{{ tt('Returns Policy', '退换货政策') }}</router-link>{{ tt(' — 30-day returns on unopened sets, free exchanges on faulty items.', '——未拆封套装 30 天内可退，质量问题免费换新。') }}</p>
          <h2 id="ip" style="scroll-margin-top:90px">{{ tt('4 · Intellectual property', '4 · 知识产权') }}</h2>
          <p>{{ tt('All site content, designs and product imagery are GLOWMAG property. UGC you submit grants us a license to feature it with credit; you keep ownership.', '本站所有内容、设计与产品图片均为 GLOWMAG 财产。你提交的 UGC 内容授予我们署名展示的许可；所有权仍归你所有。') }}</p>
          <h2 id="liability" style="scroll-margin-top:90px">{{ tt('5 · Liability', '5 · 责任') }}</h2>
          <p>{{ tt('Our liability is limited to the order value. Nothing limits liability for fraud or where prohibited by law. Products are cosmetic accessories — patch-test adhesives and follow instructions.', '我们的责任以订单金额为限。欺诈情形或法律另有禁止者不受此限。产品为美妆配饰——请先对胶水做皮肤测试，并遵照使用说明。') }}</p>
          <h2 id="law" style="scroll-margin-top:90px">{{ tt('6 · Governing law', '6 · 适用法律') }}</h2>
          <p>{{ tt('These terms are governed by the laws of the State of New York, USA.', '本条款受美国纽约州法律管辖。') }}</p>
        </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
@media (max-width: 768px) {
  .policy-grid { grid-template-columns: 1fr !important; gap: 16px; }
}
</style>
