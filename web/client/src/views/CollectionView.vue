<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../api/client'
import { i18n } from '../i18n'
import ProductCard from '../components/ProductCard.vue'

/* GET /api/catalog/collections/{slug} → {id, slug, title, banner_image, products: [卡片]}；404 = 合集不存在 */
const route = useRoute()
const col = ref(null)
const loaded = ref(false)
const failed = ref(false)
const notFound = ref(false)

const IMG_FALLBACK = 'https://placehold.co/1200x400/E8B4B8/552338?text=GLOWMAG'
function imgFallback(e) {
  const img = e.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = IMG_FALLBACK
}

async function load() {
  loaded.value = false
  failed.value = false
  notFound.value = false
  col.value = null
  try {
    col.value = await req('GET', '/api/catalog/collections/' + encodeURIComponent(String(route.params.slug || '')))
  } catch (e) {
    if (e && e.status === 404) notFound.value = true
    else failed.value = true
  }
  loaded.value = true
}
onMounted(load)
watch(() => route.params.slug, () => load())
</script>

<template>
  <section class="section" style="padding-top:0">
    <div class="container">
      <div v-if="!loaded" style="display:grid;gap:16px">
        <div class="skeleton" style="height:200px;border-radius:14px"></div>
        <div class="grid grid-4">
          <div v-for="i in 8" :key="i" class="sk-card">
            <div class="sk-img sk-shimmer"></div>
            <div class="sk-line sk-shimmer" style="width:70%;height:14px;margin-top:10px"></div>
          </div>
        </div>
      </div>

      <div v-else-if="notFound || failed" style="text-align:center;padding:60px 0;color:var(--gray)">
        <div style="font-size:44px;margin-bottom:10px">{{ failed ? '⚠️' : '▣' }}</div>
        <b style="display:block;color:var(--ink);margin-bottom:4px">{{ failed ? i18n.t('col.errT') : i18n.t('col.notFoundT') }}</b>
        <p style="font-size:13.5px">{{ failed ? i18n.t('col.errD') : i18n.t('col.notFoundD') }}</p>
        <div style="margin-top:14px;display:flex;gap:10px;justify-content:center;flex-wrap:wrap">
          <button v-if="failed" class="btn btn-secondary btn-sm" @click="load">↻ {{ i18n.t('col.retry') }}</button>
          <router-link v-else class="btn btn-primary btn-sm" to="/collections">{{ i18n.t('col.back') }}</router-link>
        </div>
      </div>

      <template v-else>
        <div class="col-hero">
          <img v-if="col.banner_image" :src="col.banner_image" :alt="col.title" @error="imgFallback">
          <h1>{{ col.title }}</h1>
        </div>

        <div v-if="col.products && col.products.length" class="grid grid-4">
          <ProductCard v-for="p in col.products" :key="p.id" :p="p" />
        </div>
        <div v-else style="text-align:center;padding:50px 0;color:var(--gray)">
          <div style="font-size:44px;margin-bottom:10px">▣</div>
          <b style="display:block;color:var(--ink);margin-bottom:4px">{{ i18n.t('col.emptyPT') }}</b>
          <p style="font-size:13.5px;margin-bottom:14px">{{ i18n.t('col.emptyPD') }}</p>
          <router-link class="btn btn-secondary btn-sm" to="/collections">{{ i18n.t('col.back') }}</router-link>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.sk-card { border-radius: 12px; }
.sk-img { aspect-ratio: 1; border-radius: 12px; }
.col-hero { position: relative; border-radius: 16px; overflow: hidden; margin-bottom: 26px; background: linear-gradient(135deg, var(--rose-pale), var(--rose)); min-height: 120px; display: flex; align-items: center; justify-content: center; }
.col-hero img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.col-hero h1 { position: relative; font-family: var(--font-title); font-size: 34px; color: #fff; text-shadow: 0 2px 14px rgba(31,27,30,.45); padding: 40px 20px; }
</style>
