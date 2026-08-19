<script setup>
import { ref } from 'vue'

const open = ref(-1)
const FAQS = [
  ['How long do press-ons last?', 'With adhesive tabs: 3–7 days. With our brush-on glue: up to 2 weeks. Application area prep (clean, dry, buff lightly) is the #1 factor.'],
  ['Will they damage my natural nails?', 'No — our sets apply on top of your natural nail with zero drilling or filing into the nail plate. Removal is a 10-minute warm soak.'],
  ['How do I find my size?', 'Our Size Guide has a printable measurer; most people wear 2–3 sizes per hand, which is why every set includes 24 nail tips (12 sizes × 2).'],
  ['Can I reuse my set?', 'Yes — up to 60 wears. Wipe with alcohol after removal, store in the case, and re-apply with fresh tabs.'],
  ['How do magnetic lashes work?', 'Tiny magnets snap the lash band onto our magnetic liner (or the included anchor lashes) — no glue, no wait, 5 seconds per eye.'],
  ['What is your return policy?', '30-day free returns on unopened sets; exchanges always free (we reship instantly, you keep the original on faulty items).'],
  ['Do you ship internationally?', 'US/CA/UK/AU currently. US orders over $35 ship free; international rates calculated at checkout.'],
  ['How do Glow points work?', 'Earn 1 pt per $1, 50 pts per review, 500 pts per referral. 100 pts = $1 off. Redeem at checkout.'],
]
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:720px">
      <div class="section-head"><h2 class="section-title">FAQ ❓</h2></div>
      <div style="display:grid;gap:10px">
        <div v-for="(f, i) in FAQS" :key="i" class="card" style="padding:0;overflow:hidden">
          <button
            style="width:100%;display:flex;justify-content:space-between;gap:12px;align-items:center;padding:16px 18px;background:none;border:none;cursor:pointer;font:inherit;font-weight:600;font-size:14.5px;text-align:left"
            @click="open = open === i ? -1 : i"
          >
            {{ f[0] }}
            <span style="font-size:18px;color:var(--plum);transition:transform .2s" :style="{ transform: open === i ? 'rotate(45deg)' : '' }">+</span>
          </button>
          <div v-show="open === i" style="padding:0 18px 16px;font-size:13.5px;color:var(--gray);line-height:1.7">
            {{ f[1] }}
          </div>
        </div>
      </div>
      <p style="text-align:center;margin-top:20px;font-size:13.5px;color:var(--gray)">
        Still stuck? <router-link to="/contact" style="color:var(--plum)">Contact our glam team</router-link> — replies under 4h.
      </p>
    </div>
  </section>
</template>
