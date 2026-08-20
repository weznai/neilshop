<script setup>
const SECS = [
  ['returns', 'Returns'],
  ['exchanges', 'Exchanges'],
  ['exceptions', 'Exceptions'],
]
function go(id) {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:960px">
      <h1 class="page-title" style="font-family:var(--font-title);font-size:30px;margin-bottom:6px">Returns Policy</h1>
      <div class="meta-row">
        <span>Last updated: Jan 2026</span><span class="meta-dot" /><span>30-day window · free exchanges, always</span>
      </div>
      <div class="policy-grid" style="display:grid;grid-template-columns:200px 1fr;gap:32px">
        <aside class="policy-side">
          <div class="toc-card">
            <span class="toc-title">On this page</span>
            <a v-for="[id, label] in SECS" :key="id" :href="'#' + id" @click.prevent="go(id)">{{ label }}</a>
          </div>
        </aside>
        <article class="prose">
          <div class="grid grid-3" style="margin-bottom:22px">
            <div class="card" style="padding:16px;text-align:center"><b style="font-size:20px">30 days</b><div style="font-size:12.5px;color:var(--gray)">Free returns window</div></div>
            <div class="card" style="padding:16px;text-align:center"><b style="font-size:20px">Free</b><div style="font-size:12.5px;color:var(--gray)">Exchanges, always</div></div>
            <div class="card" style="padding:16px;text-align:center"><b style="font-size:20px">Instant</b><div style="font-size:12.5px;color:var(--gray)">Refunds to original method</div></div>
          </div>
          <h2 id="returns" style="scroll-margin-top:90px">Returns</h2>
          <p>Unopened, unused sets in original packaging within <b>30 days of delivery</b> — your order page shows the exact deadline. Start from <router-link to="/account/orders" style="color:var(--plum)">Account → Orders → Return</router-link>; prepaid label by email. Refunds land 3–5 business days after we scan the return.</p>
          <h2 id="exchanges" style="scroll-margin-top:90px">Exchanges (the magic part)</h2>
          <p>Wrong size, shade, or a faulty tip? We reship the replacement <b>immediately</b> — you keep the original set. No label, no waiting. Select "Exchange" when starting your return.</p>
          <h2 id="exceptions" style="scroll-margin-top:90px">Exceptions</h2>
          <p>For hygiene reasons, opened lash sets and gift cards are final sale. Subscription boxes can be cancelled anytime before renewal (manage in <router-link to="/subscribe" style="color:var(--plum)">Nail Club</router-link>).</p>
          <p style="font-size:13px;color:var(--gray)">Figures above reflect our standard policy — the status shown on your order page at checkout time always takes precedence.</p>
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
