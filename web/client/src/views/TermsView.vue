<script setup>
import { useTocSpy } from '../composables/useTocSpy'

const SECS = [
  ['orders', '1 · Orders & payment'],
  ['shipping', '2 · Shipping'],
  ['returns', '3 · Returns & exchanges'],
  ['ip', '4 · Intellectual property'],
  ['liability', '5 · Liability'],
  ['law', '6 · Governing law'],
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
      <h1 class="page-title" style="font-family:var(--font-title);font-size:30px;margin-bottom:6px">Terms of Service</h1>
      <div class="meta-row">
        <span>Last updated: Aug 2026</span><span class="meta-dot" /><span>By using glowmag.com you agree to these terms</span>
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
          <h2 id="orders" style="scroll-margin-top:90px">1 · Orders &amp; payment</h2>
          <p>An order is an offer to purchase; the contract forms when we confirm shipment. Prices in USD; taxes calculated at checkout. We may cancel and refund orders affected by pricing errors or stock-outs.</p>
          <h2 id="shipping" style="scroll-margin-top:90px">2 · Shipping</h2>
          <p>See our <router-link to="/shipping-policy" style="color:var(--plum)">Shipping Policy</router-link>. Risk passes to you on delivery to the carrier.</p>
          <h2 id="returns" style="scroll-margin-top:90px">3 · Returns &amp; exchanges</h2>
          <p>See our <router-link to="/returns-policy" style="color:var(--plum)">Returns Policy</router-link> — 30-day returns on unopened sets, free exchanges on faulty items.</p>
          <h2 id="ip" style="scroll-margin-top:90px">4 · Intellectual property</h2>
          <p>All site content, designs and product imagery are GLOWMAG property. UGC you submit grants us a license to feature it with credit; you keep ownership.</p>
          <h2 id="liability" style="scroll-margin-top:90px">5 · Liability</h2>
          <p>Our liability is limited to the order value. Nothing limits liability for fraud or where prohibited by law. Products are cosmetic accessories — patch-test adhesives and follow instructions.</p>
          <h2 id="law" style="scroll-margin-top:90px">6 · Governing law</h2>
          <p>These terms are governed by the laws of the State of New York, USA.</p>
        </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
@media (max-width: 768px) {
  .policy-grid { grid-template-columns: 1fr !important; gap: 16px; }
}
/* TOC 命中态（Scrollspy）：plum + 左侧指示条 */
.toc-link.on { color: var(--plum); font-weight: 700; border-left: 3px solid var(--plum); padding-left: 10px; margin-left: -13px; }
/* 正文排版补全：68ch 行宽 + h3/h4 层级 + 品牌链接/圆角图片 */
.prose { max-width: 68ch; }
.prose h3 { font-family: var(--font-title); font-size: 18px; margin: 26px 0 10px; }
.prose h4 { font-family: var(--font-title); font-size: 15.5px; margin: 20px 0 8px; }
.prose a { color: var(--plum); text-decoration: underline; text-underline-offset: 3px; text-decoration-color: var(--rose); }
.prose a:hover { text-decoration-color: var(--plum); }
.prose img { border-radius: 12px; }
</style>
