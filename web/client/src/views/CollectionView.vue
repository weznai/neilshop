<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { i18n, tt } from '../i18n'
import ProductCard from '../components/ProductCard.vue'

/* GET /api/catalog/collections/{slug} → {id, slug, title, banner_image, products: [卡片]}；404 = 合集不存在
   后端全量返回（物化合集）/规则合集上限 100：前端客户端分页（首屏 12 + Load more），大合集不一次性渲染 */
const route = useRoute()
const router = useRouter()
const col = ref(null)
const loaded = ref(false)
const failed = ref(false)
const notFound = ref(false)
const PAGE_SIZE = 12
const shownCount = ref(PAGE_SIZE)

const allProducts = computed(() => (col.value && col.value.products) || [])
const shown = computed(() => allProducts.value.slice(0, shownCount.value))
const remaining = computed(() => Math.max(0, allProducts.value.length - shownCount.value))
/* Load more 进度同步 URL（replace 不产生历史）：刷新/分享恢复展开位置 */
function loadMore() {
  shownCount.value += PAGE_SIZE
  router.replace({ query: { ...route.query, shown: String(shownCount.value) } })
}

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
  const initShown = parseInt(route.query.shown, 10)
  shownCount.value = Number.isFinite(initShown) && initShown > PAGE_SIZE ? initShown : PAGE_SIZE
  try {
    col.value = await req('GET', '/api/catalog/collections/' + encodeURIComponent(String(route.params.slug || '')))
    /* 面包屑上报（StoreLayout gm:crumbs 覆盖默认推导；模板已前置 Home 链接，此处不重复 Home） */
    window.dispatchEvent(new CustomEvent('gm:crumbs', { detail: [
      { path: '/collections', title: tt('Collections', '合辑') },
      { title: col.value.title },
    ] }))
    /* 动态 SEO：按语言生成描述并拼接前几个商品标题（gm:seo 事件通道，路由切换自动复位） */
    try {
      const names = (col.value.products || []).slice(0, 3).map((x) => x.title).join(', ')
      const desc = i18n.lang === 'zh'
        ? `${col.value.title || ''} —— 精选穿戴甲与磁性睫毛合集，手工打造、沙龙级品质，满 $35 包邮。${names ? '包含 ' + names + '。' : ''}`
        : `${col.value.title || ''} — curated press-on nail & magnetic lash sets. Handmade, salon-quality glam delivered free over $35.${names ? ' Includes ' + names + '.' : ''}`
      window.dispatchEvent(new CustomEvent('gm:seo', { detail: {
        title: (col.value.title || 'Collection') + ' · GLOWMAG',
        description: desc.slice(0, 160),
        image: col.value.banner_image || undefined,
      } }))
    } catch (_) { /* SEO 失败不影响页面 */ }
  } catch (e) {
    if (e && e.status === 404) notFound.value = true
    else failed.value = true
  }
  loaded.value = true
}
onMounted(load)
watch(() => route.params.slug, () => load())
/* 站内切换语言：重拉合集（后端 locale 翻译口径，对齐 CollectionsView） */
watch(() => i18n.lang, load)
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

        <div v-if="col.products && col.products.length">
          <div class="grid grid-4">
            <ProductCard v-for="p in shown" :key="p.id" :p="p" />
          </div>
          <div v-if="remaining" style="text-align:center;margin-top:26px">
            <button class="btn btn-secondary" @click="loadMore">
              {{ tt(`Load more (${remaining} left)`, `加载更多（还剩 ${remaining} 件）`) }}
            </button>
          </div>
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
