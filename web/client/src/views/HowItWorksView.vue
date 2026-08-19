<template>
  <section class="section">
    <div class="container">
      <div style="text-align:center;margin-bottom:34px">
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">How It Works</h1>
        <p style="color:var(--gray)">From box to bombshell in 5 minutes.</p>
      </div>
      <div class="grid grid-3">
        <div v-for="s in [
          ['1', 'Prep & clean', 'Wipe nails with the included alcohol pad. Lightly buff, push back cuticles. Pick your sizes — hold each nail tip over your natural nail to match.'],
          ['2', 'Apply adhesive', 'Use adhesive tabs for 3–7 day wear, or a thin layer of brush-on glue for up to 2 weeks. One drop per nail — less is more.'],
          ['3', 'Press & hold', 'Align the tip from cuticle to edge, press down, hold 5 seconds. Done! Avoid water for the first hour.'],
          ['4', 'Lash magic', 'Draw a thin magnetic liner line, wait 30 seconds to set, then let the lash band snap on. Adjust with fingers — no glue disasters.'],
          ['5', 'Wear & shine', 'Up to 2 weeks of wear. Chop, file, and paint them like natural nails if you want a fresh shape.'],
          ['6', 'Remove & reuse', '10-minute warm soapy soak (or glue remover), lift gently from the cuticle side. Clean, dry, store — ready for next glam.'],
        ]" :key="s[0]" class="card" style="padding:22px">
          <div style="width:52px;height:52px;border-radius:50%;background:linear-gradient(135deg,var(--rose),var(--plum));color:#fff;display:inline-flex;align-items:center;justify-content:center;font-family:var(--font-title);font-size:22px;font-weight:700;margin-bottom:12px">{{ s[0] }}</div>
          <b style="font-size:15px">{{ s[1] }}</b>
          <p style="font-size:13.5px;color:var(--gray);margin-top:6px;line-height:1.7">{{ s[2] }}</p>
        </div>
      </div>
      <div style="text-align:center;margin-top:26px">
        <router-link to="/store" class="btn btn-primary btn-lg">Shop starter kits →</router-link>
      </div>
    </div>
  </section>
</template>
