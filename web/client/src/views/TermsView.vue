<script setup>
const SECS = [
  ['orders', '1 · Orders & payment'],
  ['shipping', '2 · Shipping'],
  ['returns', '3 · Returns & exchanges'],
  ['ip', '4 · Intellectual property'],
  ['liability', '5 · Liability'],
  ['law', '6 · Governing law'],
]
function go(id) {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:960px">
      <h1 class="page-title" style="font-family:var(--font-title);font-size:30px;margin-bottom:6px">Terms of Service</h1>
      <div class="meta-row">
        <span>Last updated: Aug 2026</span><span class="meta-dot" /><span>By using glowmag.com you agree to these terms</span>
      </div>
      <div class="policy-grid" style="display:grid;grid-template-columns:200px 1fr;gap:32px">
        <aside class="policy-side">
          <div class="toc-card">
            <span class="toc-title">On this page</span>
            <a v-for="[id, label] in SECS" :key="id" :href="'#' + id" @click.prevent="go(id)">{{ label }}</a>
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
</style>
