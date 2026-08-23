<script setup>
import { useTocSpy } from '../composables/useTocSpy'
import { i18n } from '../i18n'

const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)
const SECS = [
  ['returns', 'Returns', '退货'],
  ['exchanges', 'Exchanges', '换货'],
  ['exceptions', 'Exceptions', '例外情形'],
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
      <h1 class="page-title" style="font-family:var(--font-title);font-size:30px;margin-bottom:6px">{{ tt('Returns Policy', '退换货政策') }}</h1>
      <div class="meta-row">
        <span>{{ tt('Last updated: Aug 2026', '最后更新：2026 年 8 月') }}</span><span class="meta-dot" /><span>{{ tt('30-day window · free exchanges, always', '30 天退货窗口 · 换货永久免费') }}</span>
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
          <div class="grid grid-3 grid-m-1" style="margin-bottom:22px">
            <div class="card" style="padding:16px;text-align:center"><b style="font-size:20px">{{ tt('30 days', '30 天') }}</b><div style="font-size:12.5px;color:var(--gray)">{{ tt('Free returns window', '免费退货窗口') }}</div></div>
            <div class="card" style="padding:16px;text-align:center"><b style="font-size:20px">{{ tt('Free', '免费') }}</b><div style="font-size:12.5px;color:var(--gray)">{{ tt('Exchanges, always', '换货，永久免费') }}</div></div>
            <div class="card" style="padding:16px;text-align:center"><b style="font-size:20px">{{ tt('Instant', '即时') }}</b><div style="font-size:12.5px;color:var(--gray)">{{ tt('Refunds to original method', '原支付方式退款') }}</div></div>
          </div>
          <h2 id="returns" style="scroll-margin-top:90px">{{ tt('Returns', '退货') }}</h2>
          <p>{{ tt('Unopened, unused sets in original packaging within ', '自送达起') }}<b>{{ tt('30 days of delivery', '30 天内') }}</b>{{ tt(' — your order page shows the exact deadline. Start from ', '、保持原包装未拆封未使用的套装可退——订单页会显示确切的截止日期。从') }}<router-link to="/account/orders" style="color:var(--plum)">{{ tt('Account → Orders → Return', '账户 → 订单 → 退货') }}</router-link>{{ tt('; prepaid label by email. Refunds land 3–5 business days after we scan the return.', '发起；预付退货标签将通过邮件发送。我们扫描收到退货后 3–5 个工作日内退款到账。') }}</p>
          <h2 id="exchanges" style="scroll-margin-top:90px">{{ tt('Exchanges (the magic part)', '换货（最贴心的部分）') }}</h2>
          <p>{{ tt('Wrong size, shade, or a faulty tip? We reship the replacement ', '尺码不对、色号不合，还是甲片有瑕疵？我们会') }}<b>{{ tt('immediately', '立即补发') }}</b>{{ tt(' — you keep the original set. No label, no waiting. Select "Exchange" when starting your return.', '替换品——原套装无需寄回。无需退货标签，无需等待。发起退货时选择“换货”即可。') }}</p>
          <h2 id="exceptions" style="scroll-margin-top:90px">{{ tt('Exceptions', '例外情形') }}</h2>
          <p>{{ tt('For hygiene reasons, opened lash sets and gift cards are final sale. Subscription boxes can be cancelled anytime before renewal (manage in ', '出于卫生考虑，已拆封的睫毛套装与礼品卡为最终销售、不支持退换。订阅盒可在续订前随时取消（在') }}<router-link to="/subscribe" style="color:var(--plum)">{{ tt('Nail Club', '美甲月盒') }}</router-link>{{ tt(').', '中管理）。') }}</p>
          <p style="font-size:13px;color:var(--gray)">{{ tt('Figures above reflect our standard policy — the status shown on your order page at checkout time always takes precedence.', '以上数字为标准政策——以下单时订单页显示的状态为准。') }}</p>
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
