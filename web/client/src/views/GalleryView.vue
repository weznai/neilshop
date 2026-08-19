<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../api/client'

const shots = ref([])
onMounted(async () => {
  try { shots.value = (await req('GET', '/api/content/ugc?public=1')).items || [] } catch (_) { shots.value = [] }
})
const SEED = Array.from({ length: 8 }, (_, i) => ({
  image_url: `https://placehold.co/300x300/F5D8DA/6D2E46?text=Look+${i + 1}`,
  instagram_handle: '@glowmag_fan',
  product: null,
}))
function esc(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head">
        <h2 class="section-title">#GLOWMAGGlam</h2>
        <a class="section-link" href="javascript:void(0)">Tag us on TikTok →</a>
      </div>
      <p style="text-align:center;color:var(--gray);margin-bottom:26px">4,800+ community looks — tap any shot to shop it.</p>
      <div class="grid grid-4">
        <div v-for="(u, i) in shots.length ? shots : SEED" :key="i" class="shot card" style="padding:0;overflow:hidden;animation:fadeUp .35s both">
          <div style="position:relative;aspect-ratio:1">
            <img :src="u.image_url" :alt="(u.instagram_handle || 'Glowmag Fan') + ' wearing GLOWMAG nails'" loading="lazy" style="width:100%;height:100%;object-fit:cover">
            <span v-if="u.instagram_handle" class="ontag" style="position:absolute;bottom:10px;left:10px;background:rgba(0,0,0,.45);color:#fff;font-size:11px;padding:3px 9px;border-radius:999px">
              On {{ esc(u.instagram_handle) }}
            </span>
          </div>
          <div v-if="u.product" style="padding:12px 14px;font-size:12.5px;display:flex;justify-content:space-between;align-items:center">
            <span>{{ u.product.title }}</span>
            <router-link
              class="btn btn-secondary btn-sm" style="font-size:11px"
              :to="u.product.id ? `/product?id=${u.product.id}` : `/product?slug=${encodeURIComponent(u.product.slug)}`"
            >Shop →</router-link>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
