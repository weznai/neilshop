<template>
  <section class="section">
    <div class="container" style="max-width:760px">
      <h1 style="font-family:var(--font-title);font-size:30px;margin-bottom:18px">Shipping Policy</h1>
      <div style="display:grid;gap:14px;font-size:14px;line-height:1.8">
        <table class="card" style="width:100%;border-collapse:collapse;padding:12px;font-size:13.5px">
          <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:10px">Region</th><th>Standard</th><th>Express</th><th>Free over</th></tr></thead>
          <tbody>
            <tr style="border-top:1px solid var(--gray-light)"><td style="padding:10px">🇺🇸 US</td><td>3–6 days · $4.99</td><td>1–3 days · $14.99</td><td>$35</td></tr>
            <tr style="border-top:1px solid var(--gray-light)"><td style="padding:10px">🇨🇦 CA</td><td>5–9 days · $9.99</td><td>2–5 days · $19.99</td><td>$60</td></tr>
            <tr style="border-top:1px solid var(--gray-light)"><td style="padding:10px">🇬🇧 UK / 🇦🇺 AU</td><td>7–12 days · $12.99</td><td>3–6 days · $24.99</td><td>$80</td></tr>
          </tbody>
        </table>
        <p>Orders placed before 2pm ET ship same business day. You'll get tracking by email the moment your box moves.</p>
        <p>Subscription boxes always ship free. Pre-orders and backorders show their ETA on the product page.</p>
        <p>Lost package? After 7 days past the ETA, <router-link to="/contact" style="color:var(--plum)">contact us</router-link> — we reship first, investigate second.</p>
      </div>
    </div>
  </section>
</template>
