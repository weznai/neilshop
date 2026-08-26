<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { i18n } from '../i18n'
import { useUiStore } from '../stores/ui'
import { req } from '../api/client'
import { GM_CATALOG } from '../data/catalog'
import { TRENDING } from '../data/trending'

const ui = useUiStore()
const router = useRouter()
const q = ref('')
const suggestions = ref(null) /* null = 未搜索（显示最近/热门） */
const sugLoading = ref(false)
/* 有联想分类/商品任一即进入结果区（无 products 但有 categories 时仍展示分类 + 查看全部） */
const hasCats = computed(() => !!(suggestions.value && suggestions.value.categories && suggestions.value.categories.length))
/* 联想行图兜底：回落 placehold + dataset 守卫防循环 */
const IMG_FALLBACK = 'https://placehold.co/72x72/E8B4B8/552338?text=GLOWMAG'
function imgFallback(e) {
  const img = e.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = IMG_FALLBACK
}
/* 最近浏览/最近搜索：localStorage 非响应式，改为 ref + 打开时重读 */
const recent = ref([])
const RECENT_KEY = 'gm_recent_searches'
const recentTerms = ref([])
function loadRecents() {
  try { recent.value = JSON.parse(localStorage.getItem('gm_recent') || '[]').filter((x) => x && x.id) }
  catch (_) { recent.value = [] }
  try { recentTerms.value = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]').filter((s) => typeof s === 'string') }
  catch (_) { recentTerms.value = [] }
}

let timer = null
let sugSeq = 0
watch(q, (v) => {
  clearTimeout(timer)
  const raw = v.trim()
  if (!raw) { suggestions.value = null; sugLoading.value = false; return }
  const seq = ++sugSeq
  sugLoading.value = true
  timer = setTimeout(async () => {
    try {
      const d = await req('GET', '/api/catalog/search?q=' + encodeURIComponent(raw))
      if (seq !== sugSeq) return
      suggestions.value = d
    } catch (_) {
      if (seq !== sugSeq) return
      suggestions.value = { products: [], categories: [] }
    } finally {
      if (seq === sugSeq) sugLoading.value = false
    }
  }, 300)
})

function saveRecentSearch(term) {
  const v = (term || '').trim()
  if (!v) return
  let arr = []
  try { arr = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]') } catch (_) { arr = [] }
  arr = [v, ...arr.filter((s) => s.toLowerCase() !== v.toLowerCase())].slice(0, 8)
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(arr)) } catch (_) { /* 隐私模式 */ }
}

/* 清空最近搜索（对齐 SearchView：移除存储 + 清本地 ref） */
function clearRecent() {
  recentTerms.value = []
  try { localStorage.removeItem(RECENT_KEY) } catch (_) { /* 隐私模式 */ }
}

function submit() {
  /* 高亮联想项时 Enter 直接跳商品（combobox 惯例）；否则按原行为提交搜索 */
  if (activeIdx.value >= 0 && options.value[activeIdx.value]) {
    saveRecentSearch(q.value.trim())
    ui.closeSearch()
    router.push('/product?id=' + options.value[activeIdx.value].id)
    return
  }
  const v = q.value.trim()
  if (!v) return
  saveRecentSearch(v)
  ui.closeSearch()
  router.push({ path: '/search', query: { q: v } })
}
function searchAll() {
  const v = q.value.trim()
  if (!v) return
  saveRecentSearch(v)
  ui.closeSearch()
  router.push({ path: '/search', query: { q: v } })
}
function go(val) {
  ui.closeSearch()
  router.push(val)
}
/* 最近搜索 chip：直接跳 /search?q=（不经弹窗内联想流程） */
function goTerm(term) {
  saveRecentSearch(term)
  ui.closeSearch()
  router.push({ path: '/search', query: { q: term } })
}

/* ===== a11y：焦点管理 / 简易 focus trap / 联想键盘导航（combobox 模式） ===== */
const box = ref(null)
const inputEl = ref(null)
const activeIdx = ref(-1)
let lastActive = null

const options = computed(() => ((suggestions.value && suggestions.value.products) || []).slice(0, 6))
const listOpen = computed(() => options.value.length > 0)
watch(options, () => { activeIdx.value = -1 })

watch(() => ui.searchOpen, async (open) => {
  if (open) {
    lastActive = document.activeElement
    /* 每次打开重置输入/联想并重读最近浏览（上次会话可能已变化） */
    q.value = ''
    suggestions.value = null
    activeIdx.value = -1
    loadRecents()
    await nextTick()
    if (inputEl.value) inputEl.value.focus({ preventScroll: true })
  } else {
    activeIdx.value = -1
    if (lastActive && lastActive !== document.body && document.contains(lastActive)) {
      try { lastActive.focus({ preventScroll: true }) } catch (_) { /* 触发元素已卸载 */ }
    }
    lastActive = null
  }
})

function dialogFocusables(root) {
  if (!root) return []
  return [...root.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
}
function boxKeydown(e) {
  if (!ui.searchOpen) return
  if (e.key === 'Escape') { e.stopPropagation(); ui.closeSearch(); return }
  if (e.key === 'Tab') {
    const f = dialogFocusables(box.value)
    if (!f.length) return
    const first = f[0]
    const last = f[f.length - 1]
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
  }
}
function inputKeydown(e) {
  if (!listOpen.value) return
  if (e.key === 'ArrowDown') { e.preventDefault(); activeIdx.value = Math.min(activeIdx.value + 1, options.value.length - 1) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); activeIdx.value = Math.max(activeIdx.value - 1, -1) }
  else if (e.key === 'Home') { e.preventDefault(); activeIdx.value = 0 }
  else if (e.key === 'End') { e.preventDefault(); activeIdx.value = options.value.length - 1 }
  else return
  /* 高亮行滚动进可视区（行元素已有 gm-sug-opt-{idx} id，与 aria-activedescendant 同源） */
  const el = document.getElementById('gm-sug-opt-' + activeIdx.value)
  if (el) el.scrollIntoView({ block: 'nearest' })
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
    <div
      ref="box" class="modal-box" style="max-width:560px"
      role="dialog" aria-modal="true" :aria-label="i18n.t('search.title')"
      @keydown="boxKeydown"
    >
      <button
        class="modal-x" style="font-size:22px"
        :aria-label="i18n.lang === 'zh' ? '关闭搜索' : 'Close search'"
        @click="ui.closeSearch()"
      >×</button>
      <h3 style="margin-bottom:16px">{{ i18n.t('search.title') }}</h3>
      <form @submit.prevent="submit">
        <input
          ref="inputEl" v-model="q" class="input" :placeholder="i18n.t('search.ph')" autocomplete="off"
          role="combobox" aria-autocomplete="list" :aria-expanded="listOpen"
          aria-controls="gm-sug-list"
          :aria-activedescendant="activeIdx >= 0 ? 'gm-sug-opt-' + activeIdx : undefined"
          @keydown="inputKeydown"
        >
      </form>
      <div class="sug-list">
        <div v-if="sugLoading" aria-live="polite">
          <div v-for="i in 3" :key="'sugsk' + i" class="sug-row" style="pointer-events:none">
            <span class="sk-shimmer" style="width:36px;height:36px;border-radius:8px;flex:none"></span>
            <span class="sk-shimmer" style="width:55%;height:14px;border-radius:7px"></span>
          </div>
        </div>
        <template v-else-if="suggestions === null">
          <template v-if="recentTerms.length">
            <div class="trend-chip-title" style="font-size:12px;color:var(--gray);margin-bottom:8px">
              {{ i18n.lang === 'zh' ? '最近搜索' : 'Recent searches' }}
              <button type="button" style="margin-left:8px;font-size:12px;color:var(--gray);text-decoration:underline" :aria-label="i18n.lang === 'zh' ? '清除最近搜索' : 'Clear recent searches'" @click="clearRecent">× {{ i18n.lang === 'zh' ? '清除' : 'Clear' }}</button>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
              <button v-for="r in recentTerms.slice(0, 6)" :key="r" class="trend-chip" style="margin:0" @click="goTerm(r)">{{ r }}</button>
            </div>
          </template>
          <template v-if="recent.length">
            <div class="trend-chip-title" style="font-size:12px;color:var(--gray);margin-bottom:8px">
              {{ i18n.t('recent.title') }}
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">
              <button
                v-for="r in recent.slice(0, 6)" :key="r.id" type="button"
                class="trend-chip" style="margin:0"
                @click="go('/product?id=' + r.id)"
              >
                {{ i18n.lang === 'zh' && r.titleZh ? r.titleZh : r.title }}
              </button>
            </div>
          </template>
        </template>
        <template v-else-if="listOpen || hasCats">
          <div v-if="listOpen" id="gm-sug-list" role="listbox" :aria-label="i18n.lang === 'zh' ? '搜索联想结果' : 'Search suggestions'">
            <a
              v-for="(p, idx) in options" :id="'gm-sug-opt-' + idx" :key="p.id"
              class="sug-row" :class="{ active: activeIdx === idx }"
              role="option" :aria-selected="activeIdx === idx"
              @click.prevent="go('/product?id=' + p.id)"
            >
              <img :src="p.hero_image" :alt="cardTitle(p)" loading="lazy" @error="imgFallback">
              <span class="sug-title">{{ cardTitle(p) }}</span>
              <span class="sug-price">${{ (p.price_min / 100).toFixed(2) }}</span>
            </a>
          </div>
          <div v-if="hasCats" style="margin-top:4px">
            <button
              v-for="c in suggestions.categories.slice(0, 4)" :key="c.slug"
              type="button" class="trend-chip"
              @click="go('/store?cat=' + c.slug + (q.trim() ? '&q=' + encodeURIComponent(q) : ''))"
            >{{ c.name }}</button>
          </div>
          <button class="btn btn-secondary btn-sm btn-block" style="margin-top:10px" @click="searchAll">
            {{ i18n.lang === 'zh' ? '查看全部结果 →' : 'View all results →' }}
          </button>
        </template>
        <div v-else class="sug-empty">{{ i18n.t('search.nomatch') }}</div>
      </div>
      <div style="margin-top:18px;font-size:13px;color:var(--gray)">
        <b>{{ i18n.t('search.trending') }}</b>
        <button
          v-for="t in TRENDING" :key="t.q" type="button" class="trend-chip"
          @click="go('/search?q=' + encodeURIComponent(t.q))"
        >{{ i18n.lang === 'zh' ? t.zh : t.en }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 键盘高亮态（aria-activedescendant 联动）：与 :hover 一致的底色反馈 */
.sug-row.active { background: var(--rose-pale); }
</style>
