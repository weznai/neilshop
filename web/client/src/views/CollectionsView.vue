<script setup>
import { onMounted, ref, watch } from 'vue'
import { req } from '../api/client'
import { i18n, tt } from '../i18n'

/* GET /api/catalog/collections → {items: [{id, slug, title, banner_image}]}（仅有效集合） */
const items = ref([])
const loaded = ref(false)
const failed = ref(false)

const IMG_FALLBACK = 'https://placehold.co/600x400/E8B4B8/552338?text=GLOWMAG'
function imgFallback(e) {
  const img = e.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = IMG_FALLBACK
}

async function load() {
  failed.value = false
  try {
    const d = await req('GET', '/api/catalog/collections')
    items.value = d.items || []
  } catch (_) { failed.value = true }
  loaded.value = true
}
onMounted(load)
watch(() => i18n.lang, load)
</script>

<template>
  <section class="section">
    <div class="container">
      <div style="text-align:center;margin-bottom:30px">
        <div style="font-size:44px;margin-bottom:6px">▣</div>
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">{{ i18n.t('col.title') }}</h1>
        <p style="color:var(--gray)">{{ i18n.t('col.sub') }}</p>
      </div>

      <div v-if="!loaded" class="grid grid-3">
        <div v-for="i in 3" :key="i" class="sk-card">
          <div class="sk-img sk-shimmer" style="aspect-ratio:3/2"></div>
          <div class="sk-line sk-shimmer" style="width:70%;height:16px;margin-top:12px"></div>
        </div>
      </div>

      <div v-else-if="failed" style="text-align:center;padding:60px 0;color:var(--gray)">
        <div style="font-size:44px;margin-bottom:10px">⚠️</div>
        <b style="display:block;color:var(--ink);margin-bottom:4px">{{ i18n.t('col.errT') }}</b>
        <p style="font-size:13.5px">{{ i18n.t('col.errD') }}</p>
        <div style="margin-top:14px">
          <button class="btn btn-secondary btn-sm" @click="load">↻ {{ i18n.t('col.retry') }}</button>
        </div>
      </div>

      <div v-else-if="!items.length" style="text-align:center;padding:60px 0;color:var(--gray)">
        <div style="font-size:44px;margin-bottom:10px">▣</div>
        <b style="display:block;color:var(--ink);margin-bottom:4px">{{ i18n.t('col.emptyT') }}</b>
        <p style="font-size:13.5px">{{ i18n.t('col.emptyD') }}</p>
      </div>

      <div v-else class="grid grid-3">
        <router-link v-for="c in items" :key="c.id" class="card col-card" :to="`/collection/${c.slug}`" style="padding:0;overflow:hidden">
          <div class="col-banner">
            <img v-if="c.banner_image" :src="c.banner_image" :alt="c.title" loading="lazy" @error="imgFallback">
            <span v-else class="col-banner-ph">▣</span>
          </div>
          <div style="padding:16px 18px;display:flex;justify-content:space-between;align-items:center;gap:10px">
            <b style="font-family:var(--font-title);font-size:17px">{{ c.title }}</b>
            <span style="color:var(--plum);font-weight:700">{{ tt('Shop →', '去逛 →') }}</span>
          </div>
        </router-link>
      </div>
    </div>
  </section>
</template>

<style scoped>
.sk-card { border-radius: 12px; }
.sk-img { border-radius: 12px; }
.col-card { transition: transform .18s ease-out, box-shadow .18s ease-out; color: inherit; }
.col-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-pop); }
.col-banner { position: relative; aspect-ratio: 3/2; background: linear-gradient(180deg, var(--rose-pale), #fff); overflow: hidden; }
.col-banner img { width: 100%; height: 100%; object-fit: cover; display: block; }
.col-banner-ph { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 40px; color: var(--plum); opacity: .5; }
</style>
