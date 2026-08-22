<script setup>
import { useTocSpy } from '../composables/useTocSpy'

const SECS = [
  ['collect', '1 · What we collect'],
  ['use', '2 · How we use it'],
  ['ccpa', '3 · Your rights (CCPA)'],
  ['gdpr', '4 · Your rights (GDPR)'],
  ['cookies', '5 · Cookies'],
  ['retention', '6 · Retention'],
  ['contact', '7 · Contact'],
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
      <h1 class="page-title" style="font-family:var(--font-title);font-size:30px;margin-bottom:6px">Privacy Policy</h1>
      <div class="meta-row">
        <span>Last updated: Aug 2026</span><span class="meta-dot" /><span>GDPR &amp; CCPA aligned</span>
        <button class="print-link" type="button" @click="printPage">🖨 Print / Save PDF</button>
      </div>
      <div class="policy-grid" style="display:grid;grid-template-columns:200px 1fr;gap:32px">
        <aside class="policy-side">
          <div class="toc-card">
            <span class="toc-title">On this page</span>
            <a v-for="[id, label] in SECS" :key="id" class="toc-link" :class="{ on: active === id }" :href="'#' + id" @click.prevent="go(id)">{{ label }}</a>
          </div>
        </aside>
        <article class="prose">
          <p>This policy explains what GLOWMAG collects, why, and the controls you have.</p>
          <h2 id="collect" style="scroll-margin-top:90px">1 · What we collect</h2>
          <p>Account data (name, email, birthday if provided), order &amp; shipping data, points and referral activity, device/browser info via essential cookies, and — with your consent — analytics and marketing signals.</p>
          <h2 id="use" style="scroll-margin-top:90px">2 · How we use it</h2>
          <p>Fulfilling orders, returns and warranty; loyalty program operation; fraud prevention; with consent, site analytics and personalized recommendations. We never sell personal data.</p>
          <h2 id="ccpa" style="scroll-margin-top:90px">3 · Your rights (CCPA)</h2>
          <p>California residents may request: disclosure of categories collected (<router-link to="/account/settings" style="color:var(--plum)">Export my data</router-link>), deletion (<router-link to="/account/settings" style="color:var(--plum)">Delete account</router-link>), and correction. We do not "sell" or "share" personal information as defined by CCPA.</p>
          <h2 id="gdpr" style="scroll-margin-top:90px">4 · Your rights (GDPR)</h2>
          <p>Access, rectification, erasure, portability, restriction and objection. Exercise any right from Account → Settings, or by contacting privacy@glowmag.com. We respond within 30 days.</p>
          <h2 id="cookies" style="scroll-margin-top:90px">5 · Cookies</h2>
          <p>Essential cookies keep your cart and session working. Analytics / marketing / personalization cookies run only with your consent — manage anytime via the Cookie Settings link in the footer.</p>
          <h2 id="retention" style="scroll-margin-top:90px">6 · Retention</h2>
          <p>Order records are kept 7 years for tax compliance; account data until you delete it; anonymized analytics retained in aggregate. Deletion requests anonymize within 30 days.</p>
          <h2 id="contact" style="scroll-margin-top:90px">7 · Contact</h2>
          <p>Privacy questions: privacy@glowmag.com · DPO: dpo@glowmag.com</p>
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
