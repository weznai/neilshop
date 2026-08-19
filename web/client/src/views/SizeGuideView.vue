<script setup>
import { ref } from 'vue'
const picked = ref(-1)
const SIZES = [
  [0, 5.5, 3.5], [1, 6.0, 3.8], [2, 6.5, 4.0], [3, 7.0, 4.3], [4, 7.5, 4.5],
  [5, 8.0, 4.8], [6, 8.5, 5.0], [7, 9.0, 5.3], [8, 9.5, 5.5], [9, 10.0, 5.8],
]
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:760px">
      <div style="text-align:center;margin-bottom:30px">
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">Size Guide 📐</h1>
        <p style="color:var(--gray)">60 seconds to perfect-fit nails. Every set ships 24 tips (12 sizes × 2) — this is your cheat sheet.</p>
      </div>

      <div class="card" style="padding:22px;margin-bottom:18px">
        <h3 style="font-size:15px;margin-bottom:10px">Step 1 · Measure width (mm)</h3>
        <p style="font-size:13.5px;color:var(--gray);line-height:1.7">
          Place a ruler across the widest point of each nail bed. Note the mm for all 10 nails — pinkies and thumbs are almost always different sizes.
        </p>
      </div>

      <div class="card" style="padding:22px;margin-bottom:18px">
        <h3 style="font-size:15px;margin-bottom:10px">Step 2 · Match to size numbers</h3>
        <table style="width:100%;font-size:13.5px;border-collapse:collapse">
          <thead>
            <tr style="text-align:left;color:var(--gray)">
              <th style="padding:8px 0">Size #</th><th>Nail width (mm)</th><th>Cuticle width (mm)</th><th>Typical finger</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in SIZES" :key="s[0]"
              style="border-top:1px solid var(--gray-light);cursor:pointer"
              :style="{ background: picked === s[0] ? 'var(--rose-pale)' : '' }"
              @click="picked = s[0]"
            >
              <td style="padding:9px 0"><b>{{ s[0] }}</b></td><td>{{ s[1] }}</td><td>{{ s[2] }}</td>
              <td style="color:var(--gray)">{{ ['pinky', 'pinky/ring', 'ring', 'middle', 'middle/index', 'index', 'index/thumb', 'thumb', 'thumb', 'thumb'][s[0]] }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="picked >= 0" style="font-size:13px;color:var(--plum);font-weight:600;margin-top:10px">
          Size {{ picked }} selected — most hands use 2–3 sizes per set.
        </p>
      </div>

      <div class="card" style="padding:22px">
        <h3 style="font-size:15px;margin-bottom:10px">Between sizes?</h3>
        <p style="font-size:13.5px;color:var(--gray);line-height:1.7">
          Size <b>up</b> and file the sides down for a perfect custom fit — you can't add width. Still unsure? Our sets include all 12 sizes, so you can mix and match on application day.
        </p>
        <router-link to="/store?cat=nails" class="btn btn-primary" style="margin-top:12px">Shop nail sets →</router-link>
      </div>
    </div>
  </section>
</template>
