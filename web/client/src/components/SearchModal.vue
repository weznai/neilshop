<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { i18n } from '../i18n'
import { useUiStore } from '../stores/ui'
import { req } from '../api/client'
import { GM_CATALOG } from '../data/catalog'

const ui = useUiStore()
const router = useRouter()
const q = ref('')
const suggestions = ref(null) /* null = 未搜索（显示最近/热门） */
const trending = [
  ['french', '法式'], ['glitter', '亮片'], ['cat-eye', '猫眼'], ['short almond', '短杏仁'],
  ['natural', '自然款'], ['gift', '送礼'],
]
const recent = computed(() => JSON.parse(localStorage.getItem('gm_recent') || '[]'))

let timer = null
watch(q, (v) => {
  clearTimeout(timer)
  const raw = v.trim()
  if (!raw) { suggestions.value = null; return }
  timer = setTimeout(async () => {
    try {
      const d = await req('GET', '/api/catalog/search?q=' + encodeURIComponent(raw))
      suggestions.value = d
    } catch (_) {
      /* 回落本地目录联想 */
      const lo = raw.toLowerCase()
      suggestions.value = {
        products: GM_CATALOG.filter(
          (p) => p.title.toLowerCase().includes(lo) || (p.titleZh || '').includes(raw),
        ).slice(0, 6).map((p) => ({
          id: p.id, title: p.title, hero_image: p.img, price_min: p.price * 100,
        })),
        categories: [],
      }
    }
  }, 300)
})

function submit() {
  const v = q.value.trim()
  if (!v) return
  ui.closeSearch()
  router.push({ path: '/search', query: { q: v } })
}
function go(val) {
  ui.closeSearch()
  router.push(val)
}
function cardTitle(p) {
  if (i18n.lang === 'zh') {
    const hit = GM_CATALOG.find((c) => c.id === p.id)
    if (hit && hit.titleZh) return hit.titleZh
  }
  return p.title
}
</script>

<template>
  <div class="modal" :class="{ open: ui.searchOpen }" @click.self="ui.closeSearch()">
    <div class="modal-box" style="max-width:560px">
      <button class="modal-x" style="font-size:22px" @click="ui.closeSearch()">×</button>
      <h3 style="margin-bottom:16px">{{ i18n.t('search.title') }}</h3>
      <form @submit.prevent="submit">
        <input v-model="q" class="input" :placeholder="i18n.t('search.ph')" autocomplete="off">
      </form>
      <div class="sug-list">
        <template v-if="suggestions === null">
          <template v-if="recent.length">
            <div class="trend-chip-title" style="font-size:12px;color:var(--gray);margin-bottom:8px">
              {{ i18n.t('recent.title') }}
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">
              <a v-for="r in recent.slice(0, 6)" :key="r.id" class="trend-chip" @click.prevent="go('/product?id=' + r.id)">
                {{ i18n.lang === 'zh' && r.titleZh ? r.titleZh : r.title }}
              </a>
            </div>
          </template>
        </template>
        <template v-else-if="suggestions.products && suggestions.products.length">
          <a
            v-for="p in suggestions.products.slice(0, 6)" :key="p.id"
            class="sug-row" @click.prevent="go('/product?id=' + p.id)"
          >
            <img :src="p.hero_image" :alt="p.title">
            <span class="sug-title">{{ cardTitle(p) }}</span>
            <span class="sug-price">${{ (p.price_min / 100).toFixed(2) }}</span>
          </a>
          <div v-if="suggestions.categories && suggestions.categories.length" style="margin-top:4px">
            <a
              v-for="c in suggestions.categories.slice(0, 4)" :key="c.slug"
              class="trend-chip"
              @click.prevent="go(c.slug === 'press-on-nails' ? '/store?cat=nails' : c.slug === 'magnetic-lashes' ? '/store?cat=lashes' : '/store')"
            >{{ c.name }}</a>
          </div>
        </template>
        <div v-else class="sug-empty">{{ i18n.t('search.nomatch') }}</div>
      </div>
      <div style="margin-top:18px;font-size:13px;color:var(--gray)">
        <b>{{ i18n.t('search.trending') }}</b>
        <a
          v-for="[k, z] in trending" :key="k" class="trend-chip"
          @click.prevent="go('/search?q=' + encodeURIComponent(k))"
        >{{ i18n.lang === 'zh' ? z : k }}</a>
      </div>
    </div>
  </div>
</template>
