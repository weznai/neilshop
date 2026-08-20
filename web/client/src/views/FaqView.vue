<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'

const route = useRoute()
const router = useRouter()

const CATS = [
  [0, 'All', '✨'], [1, 'Sizing', '📐'], [2, 'Wearing', '💅'],
  [3, 'Shipping', '🚚'], [4, 'Returns', '↩️'], [5, 'Care', '🫧'], [6, 'Account', '👤'],
]
const faqs = ref([])
const cat = ref(parseInt(route.query.cat, 10) >= 1 && parseInt(route.query.cat, 10) <= 6 ? parseInt(route.query.cat, 10) : 0)
const q = ref(String(route.query.q || ''))
const open = ref(-1)
const loading = ref(true)

const shown = computed(() => {
  const kw = q.value.trim().toLowerCase()
  return faqs.value
    .filter((f) => cat.value === 0 || f.category === cat.value)
    .filter((f) => !kw || f.question.toLowerCase().includes(kw) || (f.answer_md || '').toLowerCase().includes(kw))
})
function catName(c) { return (CATS.find((x) => x[0] === c) || ['', 'Other'])[1] }

function esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
/* 关键词高亮（纯文本安全）：答案先整体转义、再注入 <mark>、最后做 md 转换（不使用未转义原文拼 HTML） */
function mdHtml(s) {
  let t = esc(s)
  const kw = q.value.trim()
  if (kw) {
    const ek = esc(kw)
    t = t.split(ek).join('<mark class="gm-hl">' + ek + '</mark>')
  }
  return t
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/\n{2,}/g, '<br><br>')
    .replace(/\n/g, '<br>')
}
/* 问题渲染：按关键词切段，<mark> 用模板组件拼接，不经 v-html */
function segs(text) {
  const kw = q.value.trim()
  const s = String(text || '')
  if (!kw) return [{ t: s, hit: false }]
  const lower = s.toLowerCase()
  const k = kw.toLowerCase()
  const out = []
  let i = 0
  for (;;) {
    const j = lower.indexOf(k, i)
    if (j < 0) { if (i < s.length) out.push({ t: s.slice(i), hit: false }); break }
    if (j > i) out.push({ t: s.slice(i, j), hit: false })
    out.push({ t: s.slice(j, j + k.length), hit: true })
    i = j + k.length
  }
  return out
}

function toggle(i) { open.value = open.value === i ? -1 : i }

/* 搜索词与分类同步 URL（?cat=&q=，replace 不产生历史记录） */
function syncUrl() {
  const query = {}
  if (cat.value) query.cat = String(cat.value)
  if (q.value.trim()) query.q = q.value.trim()
  router.replace({ query }).catch(() => {})
}
function pickCat(c) { cat.value = c; open.value = -1; syncUrl() }
let qTimer = null
watch(q, () => {
  clearTimeout(qTimer)
  qTimer = setTimeout(syncUrl, 400)
})

/* FAQPage 结构化数据（gm:seo 事件通道） */
function stripMd(s) {
  return String(s || '')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_`#>]/g, '')
    .replace(/\s*\n+\s*/g, ' ')
    .trim()
}
function pushJsonLd() {
  try {
    window.dispatchEvent(new CustomEvent('gm:seo', { detail: { jsonLd: {
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      mainEntity: faqs.value.map((f) => ({
        '@type': 'Question',
        name: f.question,
        acceptedAnswer: { '@type': 'Answer', text: stripMd(f.answer_md) },
      })),
    } } }))
  } catch (_) { /* SEO 失败不影响页面 */ }
}

onMounted(async () => {
  try { faqs.value = await req('GET', '/api/content/faqs') } catch (_) { faqs.value = [] }
  loading.value = false
  pushJsonLd()
})
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:760px">
      <div class="section-head"><h2 class="section-title">FAQ ❓</h2></div>

      <div style="position:relative;margin-bottom:16px">
        <input v-model="q" class="input" placeholder="Search answers — try “size”, “shipping”, “points”…" style="padding-left:40px">
        <span style="position:absolute;left:14px;top:50%;transform:translateY(-50%);color:var(--gray);font-size:15px">🔍</span>
      </div>

      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px">
        <button
          v-for="[c, label, icon] in CATS" :key="c"
          class="trend-chip"
          :style="cat === c ? 'border-color:var(--plum);background:var(--rose-pale);color:var(--plum)' : ''"
          @click="pickCat(c)"
        >{{ icon }} {{ label }}</button>
      </div>

      <div v-if="loading" style="display:grid;gap:10px">
        <div v-for="i in 5" :key="i" class="skeleton" style="height:58px;border-radius:12px" />
      </div>

      <div v-else-if="!shown.length" class="card" style="padding:40px;text-align:center">
        <div style="font-size:34px;margin-bottom:6px">🤔</div>
        <b>No matching answers</b>
        <p style="font-size:13.5px;color:var(--gray);margin:6px 0 14px">
          Try another keyword — or ask our glam team directly.
        </p>
        <router-link to="/contact" class="btn btn-primary btn-sm">Contact us</router-link>
      </div>

      <div v-else style="display:grid;gap:10px">
        <div v-for="(f, i) in shown" :key="f.id" class="card" style="padding:0;overflow:hidden">
          <button
            style="width:100%;display:flex;justify-content:space-between;gap:12px;align-items:center;padding:16px 18px;background:none;border:none;cursor:pointer;font:inherit;font-weight:600;font-size:14.5px;text-align:left"
            @click="toggle(i)"
          >
            <span style="display:flex;align-items:center;gap:10px;min-width:0">
              <span class="tag tag-cat" style="flex:none;font-size:10.5px">{{ catName(f.category) }}</span>
              <span><template v-for="(sg, si) in segs(f.question)" :key="si"><mark v-if="sg.hit" class="gm-hl">{{ sg.t }}</mark><template v-else>{{ sg.t }}</template></template></span>
            </span>
            <span style="font-size:18px;color:var(--plum);transition:transform .2s;flex:none" :style="{ transform: open === i ? 'rotate(45deg)' : '' }">+</span>
          </button>
          <div v-show="open === i" style="padding:0 18px 16px;font-size:13.5px;color:var(--gray);line-height:1.7" v-html="mdHtml(f.answer_md)" />
        </div>
      </div>

      <p style="text-align:center;margin-top:20px;font-size:13.5px;color:var(--gray)">
        Still stuck? <router-link to="/contact" style="color:var(--plum)">Contact our glam team</router-link> — replies under 4h.
      </p>
    </div>
  </section>
</template>

<style scoped>
.skeleton {
  background: linear-gradient(90deg, var(--gray-light) 25%, #fff 50%, var(--gray-light) 75%);
  background-size: 200% 100%;
  animation: gmSk 1.2s ease-in-out infinite;
}
@keyframes gmSk { from { background-position: 200% 0 } to { background-position: -200% 0 } }
</style>

<style>
.gm-hl { background: #F3E1F0; color: inherit; padding: 0 2px; border-radius: 3px; }
</style>
