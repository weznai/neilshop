<script setup>
import { useTocSpy } from '../composables/useTocSpy'

const SECS = [
  ['rates', 'Rates & speeds'],
  ['process', 'Processing & tracking'],
  ['lost', 'Lost or delayed'],
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
      <h1 class="page-title" style="font-family:var(--font-title);font-size:30px;margin-bottom:6px">Shipping Policy</h1>
      <div class="meta-row">
        <span>Last updated: Aug 2026</span><span class="meta-dot" /><span>Delivered by USPS / UPS / DHL</span>
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
          <h2 id="rates" style="scroll-margin-top:90px">Rates &amp; speeds</h2>
          <!-- v19 移动端补漏：4 列费率表在 375px 强行压列换行难读——外套横滑容器 + min-width（对齐 SizeGuide 表做法） -->
          <div class="rates-wrap">
            <div class="card" style="padding:12px">
              <table style="width:100%;border-collapse:collapse;font-size:13.5px">
                <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:10px">Region</th><th style="padding:10px">Method</th><th style="padding:10px">ETA</th><th style="padding:10px">Fee</th></tr></thead>
                <tbody>
                  <tr style="border-top:1px solid var(--gray-light)"><td style="padding:10px">🇺🇸 US</td><td>USPS Standard</td><td>3–6 business days</td><td>$4.99 — <b>free over $35</b></td></tr>
                  <tr style="border-top:1px solid var(--gray-light)"><td style="padding:10px">🇺🇸 US</td><td>UPS Express</td><td>1–3 business days</td><td>$14.99</td></tr>
                  <tr style="border-top:1px solid var(--gray-light)"><td style="padding:10px">🌍 International</td><td>DHL Standard</td><td>6–12 business days</td><td>$12.99</td></tr>
                </tbody>
              </table>
            </div>
          </div>
          <p>Rates above are our standard quotes — the exact fee and free-shipping threshold shown at <b>checkout always apply</b> (they can be updated by our ops team). Duties and taxes for international orders are the recipient's responsibility.</p>

          <h2 id="process" style="scroll-margin-top:90px">Processing &amp; tracking</h2>
          <p>Orders are packed within <b>24 hours</b> of payment. You'll get tracking by email the moment your box moves — no login needed to follow it on our <router-link to="/track" style="color:var(--plum)">Track Order</router-link> page. Pre-orders and backorders show their ETA on the product page.</p>

          <h2 id="lost" style="scroll-margin-top:90px">Lost or delayed packages</h2>
          <p>Parcel stuck 7+ days past the ETA? <router-link to="/contact" style="color:var(--plum)">Contact us</router-link> — we reship first and investigate second.</p>
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
