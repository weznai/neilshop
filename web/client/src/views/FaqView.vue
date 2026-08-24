<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { i18n, tt } from '../i18n'

const route = useRoute()
const router = useRouter()

const CATS = [
  [0, 'all', '✨'], [1, 'sizing', '📐'], [2, 'wearing', '💅'],
  [3, 'shipping', '🚚'], [4, 'returns', '↩️'], [5, 'care', '🫧'], [6, 'account', '👤'],
]
const faqs = ref([])
const cat = ref(parseInt(route.query.cat, 10) >= 1 && parseInt(route.query.cat, 10) <= 6 ? parseInt(route.query.cat, 10) : 0)
const q = ref(String(route.query.q || ''))
const open = ref(-1)
const loading = ref(true)
const loadErr = ref(false)

const shown = computed(() => {
  const kw = q.value.trim().toLowerCase()
  return faqs.value
    .filter((f) => cat.value === 0 || f.category === cat.value)
    .filter((f) => !kw || f.question.toLowerCase().includes(kw) || (f.answer_md || '').toLowerCase().includes(kw))
})
function catName(c) { return i18n.t('faq.cat.' + ((CATS.find((x) => x[0] === c) || [0, 'all'])[1])) }

/* 空态热门问题：优先取选码/物流/退换三类首条，无数据时回落列表前 3 条 */
const hotQs = computed(() => {
  const out = []
  for (const c of [1, 3, 4]) {
    const f = faqs.value.find((x) => x.category === c)
    if (f) out.push(f.question)
  }
  return out.length ? out.slice(0, 3) : faqs.value.slice(0, 3).map((f) => f.question)
})
function askHot(hq) { q.value = hq }

function esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
/* 关键词高亮（纯文本安全、大小写不敏感）：答案整体转义后 lowercase 扫描切片注入 <mark>（对齐 segs 逻辑），
 * 再做 mini-md 转换（不使用未转义原文拼 HTML） */
function mdHtml(s) {
  let t = esc(s)
  const kw = q.value.trim()
  if (kw) {
    const ek = esc(kw)
    const kl = ek.toLowerCase()
    if (kl) {
      const tl = t.toLowerCase()
      let out = ''
      let i = 0
      for (;;) {
        const j = tl.indexOf(kl, i)
        if (j < 0) { out += t.slice(i); break }
        out += t.slice(i, j) + '<mark class="gm-hl">' + t.slice(j, j + kl.length) + '</mark>'
        i = j + kl.length
      }
      t = out
    }
  }
  return t
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*[-*]\s+/gm, '')
    .replace(/^\s*\d{1,3}[.)]\s+/gm, '')
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
  open.value = -1
  clearTimeout(qTimer)
  qTimer = setTimeout(syncUrl, 400)
})
watch(() => i18n.lang, () => { open.value = -1 })
/* 外部 query 变化（页脚链接等，组件不重挂载）同步内部态；shown 为 computed 自动重算。
 * 内部操作经 syncUrl 写 URL 后回读，值相等时 no-op */
watch(() => route.query.cat, (v) => {
  const n = parseInt(v, 10)
  const c = Number.isFinite(n) && n >= 1 && n <= 6 ? n : 0
  if (c !== cat.value) { cat.value = c; open.value = -1 }
})
watch(() => route.query.q, (v) => {
  const t = String(v || '')
  if (t !== q.value) q.value = t
})

/* 吸顶 chips 让位滚动收缩后的 56px 顶栏（与 header scrolled 阈值同步） */
const catsNarrow = ref(false)
function onCatsScroll() { catsNarrow.value = window.scrollY > 10 }
onMounted(() => { onCatsScroll(); window.addEventListener('scroll', onCatsScroll, { passive: true }) })
onUnmounted(() => window.removeEventListener('scroll', onCatsScroll))

/* FAQPage 结构化数据（gm:seo 事件通道）：加载失败/空列表不注入（mainEntity 为空时跳过） */
function stripMd(s) {
  return String(s || '')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_`#>]/g, '')
    .replace(/\s*\n+\s*/g, ' ')
    .trim()
}
function pushJsonLd() {
  if (!faqs.value.length) return
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

onMounted(loadFaqs)
async function loadFaqs() {
  loading.value = true
  loadErr.value = false
  try { faqs.value = await req('GET', '/api/content/faqs') } catch (_) { faqs.value = []; loadErr.value = true }
  loading.value = false
  pushJsonLd()
}
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:760px">
      <div class="section-head"><h1 class="section-title">{{ i18n.t('faq.title') }}</h1></div>

      <div style="position:relative;margin-bottom:10px">
        <input v-model="q" class="input" :placeholder="i18n.t('faq.searchPh')" style="padding-left:40px;padding-right:40px">
        <span style="position:absolute;left:14px;top:50%;transform:translateY(-50%);color:var(--gray);font-size:15px">🔍</span>
        <button v-if="q" class="faq-clear" :aria-label="i18n.t('faq.clear')" @click="q = ''">✕</button>
      </div>

      <div class="faq-cats" :class="{ narrow: catsNarrow }">
        <button
          v-for="[c, key, icon] in CATS" :key="c"
          class="trend-chip" :class="{ on: cat === c }"
          @click="pickCat(c)"
        >{{ icon }} {{ i18n.t('faq.cat.' + key) }}</button>
      </div>

      <p v-if="!loading && shown.length" class="faq-count">
        {{ i18n.t('faq.count', shown.length) }}
      </p>

      <div v-if="loading" style="display:grid;gap:10px">
        <div v-for="i in 5" :key="i" class="skeleton" style="height:58px;border-radius:12px" />
      </div>

      <div v-else-if="loadErr" class="card" style="padding:40px;text-align:center">
        <div style="font-size:34px;margin-bottom:6px">💅</div>
        <b>{{ tt('Failed to load the FAQs', '常见问题加载失败') }}</b>
        <p style="font-size:13.5px;color:var(--gray);margin:6px 0 14px">
          {{ tt('Check your network and try again.', '请检查网络后重试。') }}
        </p>
        <button class="btn btn-primary btn-sm" :class="{ loading }" :disabled="loading" @click="loadFaqs">{{ tt('Retry', '重试') }}</button>
      </div>

      <div v-else-if="!shown.length" class="card" style="padding:40px;text-align:center">
        <div style="font-size:34px;margin-bottom:6px">🤔</div>
        <b>{{ i18n.t('faq.emptyT') }}</b>
        <p style="font-size:13.5px;color:var(--gray);margin:6px 0 14px">
          {{ i18n.t('faq.emptyD') }}
        </p>
        <div v-if="hotQs.length" class="faq-hot">
          <button v-for="hq in hotQs" :key="hq" class="trend-chip" @click="askHot(hq)">{{ hq }}</button>
        </div>
        <router-link to="/contact" class="btn btn-primary btn-sm">{{ i18n.t('footer.contact') }}</router-link>
      </div>

      <div v-else style="display:grid;gap:10px">
        <div v-for="(f, i) in shown" :id="'faq-' + f.id" :key="f.id" class="card faq-card" :class="{ 'faq-open': open === i }" style="padding:0;overflow:hidden">
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
          <div class="faq-a" :class="{ open: open === i }">
            <div class="faq-a-in" v-html="mdHtml(f.answer_md)" />
          </div>
        </div>
      </div>

      <p class="faq-still" v-html="i18n.t('faq.still')" />
    </div>
  </section>
</template>

<style scoped>
/* 搜索框清空钮 */
.faq-clear { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); width: 30px; height: 30px; border-radius: 50%; color: var(--gray); font-size: 14px; display: flex; align-items: center; justify-content: center; }
.faq-clear:hover { background: var(--rose-pale); color: var(--plum); }

/* 结果计数 */
.faq-count { font-size: 12.5px; color: var(--gray); margin: 0 0 14px; }

/* 分类 chips 吸顶（top 起步 64px，transition 与 header 收缩 .25s ease-out 同步，cream 底防透）；
   header 滚动收缩为 56px 时同步让位，防 8px 缝隙透出内容 */
.faq-cats { position: sticky; top: 64px; z-index: 90; background: var(--cream); padding: 8px 0 10px; margin-bottom: 6px; display: flex; gap: 8px; flex-wrap: wrap; transition: top .25s ease-out; }
.faq-cats.narrow { top: 56px; }

/* 空态热门问题 chips（单条超长省略，点击填入搜索框） */
.faq-hot { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; margin: 0 0 16px; }
.faq-hot .trend-chip { margin: 0; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 底部联系入口（v-html 注入的 <a>） */
.faq-still { text-align: center; margin-top: 20px; font-size: 13.5px; color: var(--gray); }
.faq-still :deep(a) { color: var(--plum); }

/* 打开态卡片：rose 边框 + 浅渐变底；#faq-id 锚点定位时避开吸顶头部 */
.faq-card { scroll-margin-top: 84px; }
.faq-card.faq-open { border-color: var(--rose); background: linear-gradient(180deg, #fff 40%, var(--rose-pale)); }

/* 答案展开动画：grid-template-rows 0fr→1fr 过渡 */
.faq-a { display: grid; grid-template-rows: 0fr; transition: grid-template-rows .28s ease-out; }
.faq-a.open { grid-template-rows: 1fr; }
.faq-a-in { overflow: hidden; min-height: 0; padding: 0 18px; font-size: 13.5px; color: var(--gray); line-height: 1.7; transition: padding-bottom .28s ease-out; }
.faq-a.open .faq-a-in { padding-bottom: 16px; }
</style>

<style>
.gm-hl { background: var(--rose-pale); color: inherit; font-weight: 700; padding: 0 2px; border-radius: 3px; }
</style>
