<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { errMessage, req } from '../api/client'
import { i18n, tt } from '../i18n'
import { useUiStore } from '../stores/ui'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()

const items = ref([])
const total = ref(0)
const page = ref(1)
const SIZE = 9
const tag = ref(String(route.query.tag || ''))
const loading = ref(false)
const loaded = ref(false)
const err = ref(false)
const moreErr = ref(false)
/* 标签切换竞态守卫：seq 不匹配的过期响应整体丢弃（按钮态已挡重复点击） */
let reqSeq = 0
/* 后端契约：GET /api/content/articles 响应含 tags: [{name,count}]（全量已发布聚合、热度降序）；
 * 无该键（旧后端）时回落前端已载列表聚合 */
const tagCounts = ref(null)
const PH = 'https://placehold.co/600x400/F5D8DA/6D2E46?text=GLOWMAG'

const hasMore = computed(() => items.value.length < total.value)
const tagsAvail = computed(() => {
  if (Array.isArray(tagCounts.value) && tagCounts.value.length) return tagCounts.value
  const m = new Map()
  for (const p of items.value) for (const t of (p.tags || [])) m.set(t, (m.get(t) || 0) + 1)
  return [...m.entries()].map(([name, count]) => ({ name, count }))
})
/* 无筛选时首篇文章升为 featured 横排卡 */
const featured = computed(() => (!tag.value && items.value.length ? items.value[0] : null))

/* page 只在请求成功后推进（失败不跳页、不清空已有列表）；响应 seq 落后时丢弃 */
async function load(reset) {
  const seq = ++reqSeq
  loading.value = true
  err.value = false
  moreErr.value = false
  const target = reset ? 1 : page.value + 1
  try {
    const d = await req('GET', `/api/content/articles?page=${target}&size=${SIZE}` + (tag.value ? `&tag=${encodeURIComponent(tag.value)}` : ''))
    if (seq !== reqSeq) return
    total.value = d.total || 0
    items.value = reset ? (d.items || []) : items.value.concat(d.items || [])
    page.value = target
    if (Array.isArray(d.tags)) tagCounts.value = d.tags.filter((t) => t && t.name)
  } catch (_) {
    if (seq !== reqSeq) return
    if (reset) { items.value = []; total.value = 0; err.value = true }
    else moreErr.value = true
  } finally {
    if (seq === reqSeq) loading.value = false
    loaded.value = true
  }
}
function pickTag(t) {
  tag.value = tag.value === t ? '' : t
  router.replace({ query: tag.value ? { tag: tag.value } : {} }).catch(() => {})
  load(true)
}
function loadMore() { load(false) }
function coverFallback(e) { e.target.src = PH }
/* 列表摘要剥 markdown 语法残留（加粗、链接、代码、标题符、行首列表标记等） */
function stripMd(s) {
  return String(s || '')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]*)\]\(([^)]*)\)/g, '$1')
    .replace(/[*_`#~]/g, '')
    .replace(/^\s*[-*]\s+/gm, '')
    .replace(/^\s*\d{1,3}[.)]\s+/gm, '')
    .trim()
}
/* 摘要前缀与标题重复时截去（后端 summary 修复中的前端兜底） */
function summary(p) {
  const s = stripMd(p.summary)
  const t = String(p.title || '').trim()
  if (t && s.toLowerCase().startsWith(t.toLowerCase())) {
    return s.slice(t.length).replace(/^[\s:：,，.。;；!！?？—–-]+/, '').trim()
  }
  return s
}
onMounted(() => load(true))

/* 空态订阅更新（复用页脚 newsletter 端点） */
const subEmail = ref('')
const subBusy = ref(false)
async function subscribe() {
  const v = subEmail.value.trim()
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) { ui.toast(i18n.t('footer.news.err'), 'error'); return }
  subBusy.value = true
  try {
    await req('POST', '/api/account/newsletter', { email: v, source: 'blog_empty' })
    ui.toast(i18n.t('footer.news.ok'), 'success')
    subEmail.value = ''
  } catch (e) {
    ui.toast(errMessage(e), 'error')
  } finally { subBusy.value = false }
}
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head"><h1 class="section-title">{{ i18n.t('blog.title') }}</h1></div>

      <div v-if="tagsAvail.length" class="blog-tags">
        <button class="pill" :class="{ on: !tag }" @click="pickTag('')">{{ i18n.t('blog.all') }}</button>
        <button
          v-for="t in tagsAvail" :key="t.name"
          class="pill" :class="{ on: tag === t.name }"
          @click="pickTag(t.name)"
        >#{{ t.name }}<span v-if="t.count" class="pcnt">{{ t.count }}</span></button>
      </div>

      <div v-if="!loaded" class="grid grid-3">
        <div v-for="i in 3" :key="i" class="card skeleton" style="min-height:280px;padding:0" />
      </div>

      <div v-else-if="err" class="card" style="padding:48px;text-align:center">
        <div style="font-size:36px;margin-bottom:8px">💅</div>
        <b>{{ i18n.t('blog.errT') }}</b>
        <p style="font-size:13.5px;color:var(--gray);margin:6px 0 14px">
          {{ i18n.t('blog.errD') }}
        </p>
        <button class="btn btn-primary btn-sm" :class="{ loading }" :disabled="loading" @click="load(true)">{{ i18n.t('blog.retry') }}</button>
      </div>

      <div v-else-if="!items.length" class="card" style="padding:48px;text-align:center">
        <div style="font-size:36px;margin-bottom:8px">💅</div>
        <b>{{ i18n.t('blog.emptyT') }}</b>
        <p style="font-size:13.5px;color:var(--gray);margin:6px 0 14px">
          {{ tag ? i18n.t('blog.emptyDTag', tag) : i18n.t('blog.emptyDAll') }}
        </p>
        <router-link v-if="tag" to="/blog" class="btn btn-secondary btn-sm" @click="pickTag(tag)">{{ i18n.t('blog.viewAll') }}</router-link>
        <router-link v-else to="/store" class="btn btn-primary btn-sm">{{ i18n.t('blog.shop') }}</router-link>
        <form style="display:flex;gap:8px;max-width:360px;margin:18px auto 0" @submit.prevent="subscribe">
          <input v-model="subEmail" class="input" type="email" :placeholder="tt('Email for new-post updates', '订阅新文章提醒')" autocomplete="email" aria-label="email">
          <button class="btn btn-secondary btn-sm" type="submit" :class="{ loading: subBusy }" :disabled="subBusy">{{ tt('Subscribe', '订阅') }}</button>
        </form>
      </div>

      <template v-else>
        <div class="grid grid-3">
          <template v-for="(p, i) in items" :key="p.slug + '_' + i">
            <!-- 首篇 featured 横排卡：桌面 span 2 列、左图右文，带 FEATURED 徽章 -->
            <router-link
              v-if="i === 0 && featured"
              class="card card-lift blog-card blog-feat"
              :to="{ path: '/blog/post', query: { slug: p.slug } }"
            >
              <div class="blog-cover feat-cover">
                <img :src="p.cover || PH" :alt="p.title" loading="lazy" @error="coverFallback">
              </div>
              <div class="feat-body">
                <div>
                  <span class="feat-badge">{{ i18n.t('blog.featured') }}</span>
                  <div>
                    <span v-for="t in (p.tags || []).slice(0, 3)" :key="t" class="tag tag-cat" style="margin-right:6px">{{ t.toUpperCase() }}</span>
                    <b class="feat-title">{{ p.title }}</b>
                    <p class="blog-sum feat-sum">{{ summary(p) }}</p>
                    <div class="blog-meta">{{ (p.published_at || '').slice(0, 10) }} · {{ p.author }}</div>
                  </div>
                </div>
              </div>
            </router-link>
            <router-link
              v-else
              class="card card-lift blog-card"
              :to="{ path: '/blog/post', query: { slug: p.slug } }"
            >
              <div class="blog-cover">
                <img :src="p.cover || PH" :alt="p.title" loading="lazy" @error="coverFallback">
              </div>
              <div class="blog-body">
                <span v-for="t in (p.tags || []).slice(0, 2)" :key="t" class="tag tag-cat" style="margin-right:6px">{{ t.toUpperCase() }}</span>
                <b class="blog-title">{{ p.title }}</b>
                <p class="blog-sum blog-sum-text">{{ summary(p) }}</p>
                <div class="blog-meta">{{ (p.published_at || '').slice(0, 10) }} · {{ p.author }}</div>
              </div>
            </router-link>
          </template>
        </div>
        <div v-if="hasMore" style="text-align:center;margin-top:26px">
          <button class="btn btn-secondary" :class="{ loading }" :disabled="loading" @click="loadMore">
            {{ moreErr ? i18n.t('blog.moreRetry') : i18n.t('blog.more') }}
          </button>
          <p v-if="moreErr" style="font-size:12.5px;color:var(--error);margin-top:8px">{{ i18n.t('blog.moreErr') }}</p>
        </div>
        <p v-else style="text-align:center;margin-top:22px;font-size:12.5px;color:var(--gray)">
          {{ i18n.t('blog.done', items.length, total) }}
        </p>
      </template>
    </div>
  </section>
</template>

<style scoped>
/* 标签 pills（选中态用全局 .pill.on） */
.blog-tags { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 22px; }

/* 卡片基础：封面统一 16/10 */
.blog-card { padding: 0; overflow: hidden; color: inherit; }
.blog-cover { aspect-ratio: 16/10; overflow: hidden; background: var(--rose-pale); }
.blog-cover img { width: 100%; height: 100%; object-fit: cover; }
.blog-body { padding: 16px 18px 18px; }
.blog-title { display: block; font-size: 15.5px; margin: 8px 0 6px; font-family: var(--font-title); }
.blog-meta { font-size: 12px; color: var(--gray); }
/* 摘要两行截断 */
.blog-sum { font-size: 13px; color: var(--gray); line-height: 1.6; margin: 0 0 10px; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

/* featured 横排卡：桌面 span 2 列左图右文，移动端上下堆叠 */
.blog-feat { display: grid; grid-template-columns: 1.05fr 1fr; grid-column: span 2; }
.feat-cover { aspect-ratio: auto; height: 100%; min-height: 260px; }
.feat-body { padding: 24px 26px; display: flex; flex-direction: column; justify-content: center; }
.feat-title { display: block; font-size: 21px; margin: 10px 0 8px; font-family: var(--font-title); line-height: 1.3; }
.feat-sum { font-size: 13.5px; margin-bottom: 12px; }
/* featured 徽章 */
.feat-badge { display: inline-block; background: var(--plum); color: #fff; font-size: 10px; font-weight: 700; letter-spacing: 1.5px; padding: 3px 10px; border-radius: 999px; margin-bottom: 10px; }
@media (max-width: 768px) {
  .blog-feat { grid-column: span 2; grid-template-columns: 1fr; }
  .feat-cover { height: auto; min-height: 0; aspect-ratio: 16/10; }
  .feat-body { padding: 16px 18px 18px; }
  .feat-title { font-size: 17.5px; }
}
</style>
