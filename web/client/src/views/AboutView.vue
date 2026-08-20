<template>
  <section class="section">
    <div class="container" style="max-width:760px">
      <div style="text-align:center;margin-bottom:34px">
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">Our Story</h1>
        <p style="color:var(--gray)">Salon glam, minus the salon.</p>
      </div>
      <div style="display:grid;gap:18px;font-size:15px;line-height:1.85">
        <p>GLOWMAG started in a tiny Brooklyn apartment in 2023 — one heat press, a jar of rhinestones, and a belief that <b>great nails shouldn't cost $90 and two hours</b>.</p>
        <p>Today our studio handcrafts 70+ press-on styles and magnetic lashes worn by 40,000+ customers across the US, CA, UK and AU. Every set is gel-cured, sized to 24 nail widths, and reusable up to 60 wears.</p>
        <div class="grid grid-3" style="margin:8px 0">
          <div class="card" style="padding:18px;text-align:center"><b style="font-size:24px">40k+</b><div style="font-size:12.5px;color:var(--gray)">Happy customers</div></div>
          <div class="card" style="padding:18px;text-align:center"><b style="font-size:24px">4.8/5</b><div style="font-size:12.5px;color:var(--gray)">23,000+ reviews</div></div>
          <div class="card" style="padding:18px;text-align:center"><b style="font-size:24px">70+</b><div style="font-size:12.5px;color:var(--gray)">Handcrafted styles</div></div>
        </div>
        <p>We're climate-neutral shipping, cruelty-free always, and our packaging is 100% recyclable — because glam shouldn't cost the earth.</p>
        <div class="card" style="padding:20px;display:flex;gap:14px;align-items:center;flex-wrap:wrap">
          <div style="font-size:30px">💅</div>
          <div style="flex:1;min-width:220px">
            <b>New to press-ons?</b>
            <p style="font-size:13.5px;color:var(--gray);margin:4px 0 0">See how a set goes from box to bombshell in 5 minutes — and how to make it last 2 weeks.</p>
          </div>
          <router-link to="/how-it-works" class="btn btn-secondary btn-sm">How it works →</router-link>
          <router-link to="/blog" class="btn btn-ghost btn-sm">Read the Journal</router-link>
        </div>
      </div>
    </div>
  </section>
</template>
