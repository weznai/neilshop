<script setup>
import { computed, ref, watch } from 'vue'
import { i18n } from '../i18n'

const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)
/* 选中尺码持久化（再次进入回显） */
function lsGet(k) { try { return localStorage.getItem(k) } catch (_) { return null } }
function lsSet(k, v) { try { localStorage.setItem(k, v) } catch (_) { /* 隐私模式忽略 */ } }
const saved = parseInt(lsGet('gm_size_pick'), 10)
const picked = ref(!isNaN(saved) && saved >= 0 && saved <= 9 ? saved : -1)
watch(picked, (v) => { if (v >= 0) lsSet('gm_size_pick', String(v)) })

const unit = ref('mm')
const SIZES = [
  [0, 5.5, 3.5], [1, 6.0, 3.8], [2, 6.5, 4.0], [3, 7.0, 4.3], [4, 7.5, 4.5],
  [5, 8.0, 4.8], [6, 8.5, 5.0], [7, 9.0, 5.3], [8, 9.5, 5.5], [9, 10.0, 5.8],
]
const FINGERS = ['pinky', 'pinky/ring', 'ring', 'middle', 'middle/index', 'index', 'index/thumb', 'thumb', 'thumb', 'thumb']

function conv(mm) {
  return unit.value === 'mm' ? mm.toFixed(1) : (mm / 25.4).toFixed(2)
}
const unitLabel = computed(() => (unit.value === 'mm' ? 'mm' : 'in'))
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:760px">
      <div style="text-align:center;margin-bottom:30px">
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">Size Guide 📐</h1>
        <p style="color:var(--gray)">{{ tt('60 seconds to perfect-fit nails. Every set ships 20 tips (10 sizes × 2) — this is your cheat sheet.', '60 秒找到贴合尺码。每套含 20 片甲片（10 个尺码 × 2）——这是你的选码速查表。') }}</p>
      </div>

      <div class="card" style="padding:22px;margin-bottom:18px">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px">
          <h3 style="font-size:15px;margin:0">Step 1 · Measure your nails</h3>
          <div style="display:inline-flex;border:1.5px solid var(--gray-light);border-radius:999px;overflow:hidden">
            <button
              v-for="u in ['mm', 'in']" :key="u"
              style="padding:6px 16px;font-size:12.5px;font-weight:700;border:none;cursor:pointer"
              :style="unit === u ? 'background:var(--plum);color:#fff' : 'background:transparent;color:var(--gray)'"
              @click="unit = u"
            >{{ u === 'mm' ? 'mm' : 'inch' }}</button>
          </div>
        </div>
        <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
          <img src="https://placehold.co/220x140/F5D8DA/6D2E46?text=Measure+widest+point" alt="How to measure nail width" style="border-radius:12px;flex:none" loading="lazy">
          <p style="font-size:13.5px;color:var(--gray);line-height:1.7;flex:1;min-width:220px">
            Place a ruler (or our printable sizer) across the <b>widest point</b> of each nail bed, as shown. Note the number for all 10 nails — pinkies and thumbs are almost always different sizes. Between sizes? <b>Size up</b> and file the sides down.
          </p>
        </div>
      </div>

      <div class="card" style="padding:22px;margin-bottom:18px;overflow-x:auto">
        <h3 style="font-size:15px;margin-bottom:10px">Step 2 · Match to size numbers</h3>
        <table style="width:100%;font-size:13.5px;border-collapse:collapse">
          <thead>
            <tr style="text-align:left;color:var(--gray)">
              <th style="padding:8px 0">Size #</th><th>Nail width ({{ unitLabel }})</th><th>Cuticle width ({{ unitLabel }})</th><th>Typical finger</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in SIZES" :key="s[0]"
              style="border-top:1px solid var(--gray-light);cursor:pointer"
              :style="{ background: picked === s[0] ? 'var(--rose-pale)' : '' }"
              @click="picked = s[0]"
            >
              <td style="padding:9px 0"><b>{{ s[0] }}</b></td><td>{{ conv(s[1]) }}</td><td>{{ conv(s[2]) }}</td>
              <td style="color:var(--gray)">{{ FINGERS[s[0]] }}</td>
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
          Size <b>up</b> and file the sides down for a perfect custom fit — you can't add width. Still unsure? {{ tt('Our sets include all 10 sizes, so you can mix and match on application day.', '每套包含全部 10 个尺码，佩戴当天可自由混搭。') }} Need a hand? <router-link to="/contact" style="color:var(--plum)">Ask our team</router-link> — we size nails daily.
        </p>
        <router-link to="/store?cat=nails" class="btn btn-primary" style="margin-top:12px">Shop nail sets →</router-link>
      </div>
    </div>
  </section>
</template>
