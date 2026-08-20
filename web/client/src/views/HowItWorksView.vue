<script setup>
import { onMounted } from 'vue'

const STEPS = [
  ['1', 'Pick & size', 'Choose a style, then match sizes with the interactive Size Guide — no salon visit, no drills. Every set includes 24 tips (12 sizes × 2) so you can mix per finger.', '/size-guide', 'Open Size Guide'],
  ['2', 'Prep & clean', 'Wipe nails with the included alcohol pad. Lightly buff, push back cuticles. A clean, dry nail bed is the #1 factor for long wear.'],
  ['3', 'Apply adhesive', 'Use adhesive tabs for 3–7 day wear, or a thin layer of brush-on glue for up to 2 weeks. One drop per nail — less is more.'],
  ['4', 'Press & hold', 'Align the tip from cuticle to edge, press down, hold 5 seconds per nail. Avoid water for the first hour. Done — it is a one-time purchase you own, not a rental subscription.'],
  ['5', 'Wear & shine', 'Up to 2 weeks of salon-grade glam per wear. Chop, file and paint them like natural nails if you want a fresh shape.'],
  ['6', 'Remove & reuse', '10-minute warm soapy soak, lift gently from the cuticle side — never pry. Clean, dry, store in the case: one set, up to many re-wears.'],
]

/* HowTo 结构化数据（gm:seo 事件通道，seo.js 统一注入 head） */
onMounted(() => {
  try {
    window.dispatchEvent(new CustomEvent('gm:seo', { detail: { jsonLd: {
      '@context': 'https://schema.org',
      '@type': 'HowTo',
      name: 'How to apply GLOWMAG press-on nails',
      description: 'Apply salon-quality press-on nails at home in about 5 minutes.',
      step: STEPS.map((s) => ({ '@type': 'HowToStep', name: s[1], text: s[2] })),
    } } }))
  } catch (_) { /* SEO 失败不影响页面 */ }
})
</script>

<template>
  <section class="section">
    <div class="container">
      <div style="text-align:center;margin-bottom:34px">
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">How It Works</h1>
        <p style="color:var(--gray)">Your set is yours to keep — from box to bombshell in 5 minutes.</p>
      </div>
      <div class="grid grid-3">
        <div v-for="s in STEPS" :key="s[0]" class="card" style="padding:22px">
          <div style="width:52px;height:52px;border-radius:50%;background:linear-gradient(135deg,var(--rose),var(--plum));color:#fff;display:inline-flex;align-items:center;justify-content:center;font-family:var(--font-title);font-size:22px;font-weight:700;margin-bottom:12px">{{ s[0] }}</div>
          <b style="font-size:15px">{{ s[1] }}</b>
          <p style="font-size:13.5px;color:var(--gray);margin-top:6px;line-height:1.7">{{ s[2] }}</p>
          <router-link v-if="s[3]" :to="s[3]" class="btn btn-secondary btn-sm" style="margin-top:10px">{{ s[4] }} →</router-link>
        </div>
      </div>

      <div class="card" style="padding:22px 24px;margin-top:22px;display:flex;gap:18px;align-items:center;flex-wrap:wrap">
        <div style="font-size:34px">👁️</div>
        <div style="flex:1;min-width:240px">
          <b>Wearing magnetic lashes instead?</b>
          <p style="font-size:13.5px;color:var(--gray);margin-top:4px;line-height:1.7">
            Draw a thin magnetic liner line, wait 30 seconds to set, then let the lash band snap on. Adjust with fingers — no glue disasters, 5 seconds per eye.
          </p>
        </div>
        <router-link to="/store?cat=lashes" class="btn btn-primary btn-sm">Shop magnetic lashes →</router-link>
      </div>

      <div style="text-align:center;margin-top:26px">
        <router-link to="/store" class="btn btn-primary btn-lg">Shop starter kits →</router-link>
      </div>
    </div>
  </section>
</template>
