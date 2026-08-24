<script setup>
import { useTocSpy } from '../composables/useTocSpy'
import { updatedLabel } from '../composables/policyMeta'
import { i18n, tt } from '../i18n'

const SECS = [
  ['collect', '1 · What we collect', '1 · 我们收集哪些信息'],
  ['use', '2 · How we use it', '2 · 我们如何使用'],
  ['ccpa', '3 · Your rights (CCPA)', '3 · 你的权利（CCPA）'],
  ['gdpr', '4 · Your rights (GDPR)', '4 · 你的权利（GDPR）'],
  ['cookies', '5 · Cookies', '5 · Cookie'],
  ['retention', '6 · Retention', '6 · 数据保留'],
  ['contact', '7 · Contact', '7 · 联系我们'],
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
      <h1 class="page-title" style="font-family:var(--font-title);font-size:30px;margin-bottom:6px">{{ tt('Privacy Policy', '隐私政策') }}</h1>
      <div class="meta-row">
        <span>{{ updatedLabel(tt) }}</span><span class="meta-dot" /><span>{{ tt('GDPR & CCPA aligned', '符合 GDPR 与 CCPA') }}</span>
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
          <p>{{ tt('This policy explains what GLOWMAG collects, why, and the controls you have.', '本政策说明 GLOWMAG 收集哪些信息、收集目的以及你可掌控的选项。') }}</p>
          <h2 id="collect" style="scroll-margin-top:84px">{{ tt('1 · What we collect', '1 · 我们收集哪些信息') }}</h2>
          <p>{{ tt('Account data (name, email, birthday if provided), order & shipping data, points and referral activity, device/browser info via essential cookies, and — with your consent — analytics and marketing signals.', '账户数据（姓名、邮箱、生日（如填写））、订单与配送数据、积分及推荐活动记录、通过必要 Cookie 获取的设备/浏览器信息，以及——在你同意后——分析与营销信号。') }}</p>
          <h2 id="use" style="scroll-margin-top:84px">{{ tt('2 · How we use it', '2 · 我们如何使用') }}</h2>
          <p>{{ tt('Fulfilling orders, returns and warranty; loyalty program operation; fraud prevention; with consent, site analytics and personalized recommendations. We never sell personal data.', '用于履行订单、退换货与保修；会员积分计划运营；防范欺诈；在获得同意后进行站点分析与个性化推荐。我们绝不会出售个人数据。') }}</p>
          <h2 id="ccpa" style="scroll-margin-top:84px">{{ tt('3 · Your rights (CCPA)', '3 · 你的权利（CCPA）') }}</h2>
          <p>{{ tt('California residents may request: disclosure of categories collected (', '加利福尼亚州居民可要求：披露所收集的信息类别（') }}<router-link to="/account/settings" style="color:var(--plum)">{{ tt('Export my data', '导出我的数据') }}</router-link>{{ tt('), deletion (', '）、删除（') }}<router-link to="/account/settings" style="color:var(--plum)">{{ tt('Delete account', '删除账户') }}</router-link>{{ tt('), and correction. We do not "sell" or "share" personal information as defined by CCPA.', '）以及更正。我们不会进行 CCPA 所定义的“出售”或“共享”个人信息的行为。') }}</p>
          <h2 id="gdpr" style="scroll-margin-top:84px">{{ tt('4 · Your rights (GDPR)', '4 · 你的权利（GDPR）') }}</h2>
          <p>{{ tt('Access, rectification, erasure, portability, restriction and objection. Exercise any right from Account → Settings, or by contacting privacy@glowmag.com. We respond within 30 days.', '访问、更正、删除、可携带、限制及反对。可在账户 → 设置中行使任何权利，或联系 privacy@glowmag.com。我们将在 30 天内回复。') }}</p>
          <h2 id="cookies" style="scroll-margin-top:84px">{{ tt('5 · Cookies', '5 · Cookie') }}</h2>
          <p>{{ tt('Essential cookies keep your cart and session working. Analytics / marketing / personalization cookies run only with your consent — manage anytime via the Cookie Settings link in the footer.', '必要 Cookie 用于维持购物车与会话正常运行。分析 / 营销 / 个性化 Cookie 仅在你同意后启用——可随时通过页脚的 Cookie 设置链接管理。') }}</p>
          <h2 id="retention" style="scroll-margin-top:84px">{{ tt('6 · Retention', '6 · 数据保留') }}</h2>
          <p>{{ tt('Order records are kept 7 years for tax compliance; account data until you delete it; anonymized analytics retained in aggregate. Deletion requests anonymize within 30 days.', '订单记录出于税务合规保留 7 年；账户数据保留至你删除为止；匿名化分析数据以汇总形式保留。删除请求将在 30 天内完成匿名化处理。') }}</p>
          <h2 id="contact" style="scroll-margin-top:84px">{{ tt('7 · Contact', '7 · 联系我们') }}</h2>
          <p>{{ tt('Privacy questions: privacy@glowmag.com · DPO: dpo@glowmag.com', '隐私问题：privacy@glowmag.com · 数据保护官（DPO）：dpo@glowmag.com') }}</p>
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
