<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../api/client'
import { i18n, tt } from '../i18n'
import { useUiStore } from '../stores/ui'

const route = useRoute()
const ui = useUiStore()
const post = ref(null)
const err = ref(false)
const loading = ref(true)
const related = ref([])

function esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
function inline(t) {
  return t
    /* 图片语法 ![alt](url)：仅允许 src/alt 属性，URL 限 http(s) 或站内相对路径 /（先于链接规则匹配） */
    .replace(/!\[([^\]]*)\]\(((?:https?:\/\/|\/(?!\/))[^)\s]+)\)/g, '<img src="$2" alt="$1" loading="lazy" decoding="async">')
    /* 行内代码 `code`（先于加粗/链接，避免代码片段被二次加工） */
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    /* 链接协议白名单：http(s) 外链新窗打开；以 / 开头的站内路径当页跳转；
     * 其余（javascript: / data: / vbscript: 等）剥掉链接语法只保留纯文本 */
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, text, href) => {
      if (/^https?:\/\//i.test(href)) return `<a href="${href}" target="_blank" rel="noopener">${text}</a>`
      if (/^\/(?!\/)/.test(href)) return `<a href="${href}">${text}</a>`
      return text
    })
}
/* 状态机渲染：标题 / 无序 / 有序列表（1. 1)）/ 引用块（esc 后 ^&gt;）/ 行内代码 / 段落；
 * ul、ol、blockquote 三个开闭状态互斥，空行或换块型时先闭合 */
function mdHtml(md) {
  const lines = esc(md).split(/\r?\n/)
  const out = []
  let list = ''
  let quote = false
  const closeList = () => { if (list) { out.push(`</${list}>`); list = '' } }
  const closeQuote = () => { if (quote) { out.push('</blockquote>'); quote = false } }
  for (const raw of lines) {
    const l = raw.trim()
    let m
    if (!l) { closeList(); closeQuote(); continue }
    if (/^---+$/.test(l)) {
      closeList(); closeQuote()
      out.push('<hr>')
    } else if ((m = l.match(/^(#{1,4})\s+(.*)$/))) {
      closeList(); closeQuote()
      /* #→h2 ##→h3 ###→h4 ####→h5：四级标题不再与三级塌缩为同一级 */
      const h = m[1].length + 1
      out.push(`<h${h}>${inline(m[2])}</h${h}>`)
    } else if ((m = l.match(/^&gt;\s?(.*)$/))) {
      closeList()
      if (!quote) { out.push('<blockquote>'); quote = true }
      out.push(`<p>${inline(m[1])}</p>`)
    } else if ((m = l.match(/^[-*]\s+(.*)$/))) {
      closeQuote()
      if (list !== 'ul') { closeList(); out.push('<ul>'); list = 'ul' }
      out.push(`<li>${inline(m[1])}</li>`)
    } else if ((m = l.match(/^\d{1,3}[.)]\s+(.*)$/))) {
      closeQuote()
      if (list !== 'ol') { closeList(); out.push('<ol>'); list = 'ol' }
      out.push(`<li>${inline(m[1])}</li>`)
    } else {
      closeList(); closeQuote()
      out.push(`<p>${inline(l)}</p>`)
    }
  }
  closeList(); closeQuote()
  return out.join('')
}
const body = computed(() => mdHtml(post.value?.content_md || ''))
const PH = 'https://placehold.co/1200x600/F5D8DA/6D2E46?text=GLOWMAG+Journal'
function coverFallback(e) {
  const img = e.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = PH
}

/* 阅读时长：EN 词数 + CJK 字数折算（~200/分钟） */
const readMins = computed(() => {
  const txt = String(post.value?.content_md || '')
  const words = (txt.match(/[A-Za-z0-9_'’-]+/g) || []).length + (txt.match(/[\u4e00-\u9fff]/g) || []).length
  return Math.max(1, Math.round(words / 200))
})

/* SEO 纯文本派生：剥 md 语法后压平空白 */
function stripMd(s) {
  return String(s || '')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_`#>~]/g, '')
    .replace(/^\s*[-*]\s+/gm, '')
    .replace(/^\s*\d{1,3}[.)]\s+/gm, '')
    .replace(/\s*\n+\s*/g, ' ')
    .trim()
}
/* JSON-LD image 绝对化（相对路径挂当前 origin） */
function abs(u) {
  if (!u) return ''
  if (/^https?:\/\//i.test(u)) return u
  if (typeof location === 'undefined') return u
  try { return new URL(u, location.origin).href } catch (_) { return u }
}

async function loadRelated(p) {
  related.value = []
  const t = (p.tags || [])[0]
  try {
    if (t) {
      const d = await req('GET', `/api/content/articles?page=1&size=6&tag=${encodeURIComponent(t)}`)
      related.value = (d.items || []).filter((x) => x.slug !== p.slug).slice(0, 3)
    }
    if (!related.value.length) {
      const d = await req('GET', '/api/content/articles?page=1&size=6')
      related.value = (d.items || []).filter((x) => x.slug !== p.slug).slice(0, 3)
    }
  } catch (_) { related.value = [] }
}

async function load() {
  const slug = (route.query.slug || '').trim()
  post.value = null
  err.value = false
  loading.value = true
  if (!slug) { err.value = true; loading.value = false; return }
  try {
    post.value = await req('GET', '/api/content/articles/' + encodeURIComponent(slug))
    /* 动态 SEO：OG/JSON-LD Article（dateModified 无独立字段时回落 datePublished；
     * publisher 补 logo（站内 favicon 绝对路径）；mainEntityOfPage 指向当前页；
     * description 从 content_md 派生 160 字符纯文本（stripMd 后，无正文回落 summary）；
     * JSON-LD image 绝对化；标题后缀 · GLOWMAG 对齐全站 titleSuffix） */
    try {
      const origin = typeof location !== 'undefined' ? location.origin : ''
      const desc = stripMd(post.value.content_md).slice(0, 160) || String(post.value.summary || '').slice(0, 160)
      window.dispatchEvent(new CustomEvent('gm:seo', { detail: {
        title: post.value.title + ' · GLOWMAG',
        description: desc,
        image: post.value.cover, type: 'article',
        jsonLd: {
          '@context': 'https://schema.org', '@type': 'Article',
          headline: post.value.title, image: [abs(post.value.cover || PH)],
          datePublished: post.value.published_at || undefined,
          dateModified: post.value.published_at || undefined,
          mainEntityOfPage: { '@type': 'WebPage', '@id': origin + route.fullPath },
          author: { '@type': 'Person', name: post.value.author || 'GLOWMAG' },
          publisher: {
            '@type': 'Organization', name: 'GLOWMAG',
            logo: { '@type': 'ImageObject', url: origin + '/favicon.svg' },
          },
        },
      } }))
    } catch (_) { /* SEO 失败不影响页面 */ }
    loadRelated(post.value)
  } catch (_) {
    err.value = true
  } finally {
    loading.value = false
  }
}
watch(() => route.query.slug, () => { if (route.name === 'blog-post') { window.scrollTo({ top: 0 }); load() } })
onMounted(load)

/* ===== 分享：Copy link（剪贴板降级）/ X / Facebook ===== */
async function copyLink() {
  const url = location.href
  try { await navigator.clipboard.writeText(url) } catch (_) {
    const ta = document.createElement('textarea')
    ta.value = url; document.body.appendChild(ta); ta.select()
    try { document.execCommand('copy') } catch (__) { /* noop */ }
    document.body.removeChild(ta)
  }
  ui.toast(tt('Link copied', '链接已复制'), 'success')
}
function shareX() {
  window.open('https://twitter.com/intent/tweet?url=' + encodeURIComponent(location.href) + '&text=' + encodeURIComponent(post.value?.title || ''), '_blank', 'noopener')
}
function shareFb() {
  window.open('https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(location.href), '_blank', 'noopener')
}
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:720px">
      <div v-if="loading" class="skeleton" style="min-height:320px" />

      <div v-else-if="err" class="card" style="padding:44px;text-align:center">
        <div style="font-size:38px;margin-bottom:8px">💅</div>
        <b style="font-size:16px">{{ i18n.t('post.errT') }}</b>
        <p style="font-size:13.5px;color:var(--gray);margin:8px 0 16px">
          {{ i18n.t('post.errD') }}
        </p>
        <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap">
          <router-link to="/blog" class="btn btn-primary btn-sm">{{ i18n.t('post.back') }}</router-link>
          <router-link to="/store" class="btn btn-secondary btn-sm">{{ i18n.t('post.shop') }}</router-link>
        </div>
      </div>

      <template v-else-if="post">
        <div style="border-radius:18px;overflow:hidden;margin-bottom:22px;aspect-ratio:2/1;background:var(--rose-pale)">
          <img :src="post.cover || PH" :alt="post.title" style="width:100%;height:100%;object-fit:cover" @error="coverFallback">
        </div>
        <span v-for="t in (post.tags || []).slice(0, 3)" :key="t" class="tag tag-cat" style="margin-right:6px">{{ t.toUpperCase() }}</span>
        <h1 style="font-family:var(--font-title);font-size:32px;margin:12px 0 8px">{{ post.title }}</h1>
        <div class="post-meta">
          <span>{{ (post.published_at || '').slice(0, 10) }} · {{ i18n.t('post.by', post.author || i18n.t('post.fallbackAuthor')) }}</span>
          <span class="read-chip">⏱ {{ i18n.t('post.readTime', readMins) }}</span>
          <span style="display:inline-flex;gap:6px;margin-left:auto">
            <button class="trend-chip" @click="copyLink">{{ tt('Copy link', '复制链接') }}</button>
            <button class="trend-chip" @click="shareX">X</button>
            <button class="trend-chip" @click="shareFb">Facebook</button>
          </span>
        </div>
        <article class="prose" v-html="body" />

        <div v-if="related.length" style="margin-top:44px">
          <h3 style="font-family:var(--font-title);font-size:20px;margin-bottom:16px">{{ i18n.t('post.related') }}</h3>
          <div class="grid" style="grid-template-columns:repeat(3,1fr);gap:14px">
            <router-link
              v-for="r in related" :key="r.slug"
              class="card card-lift" style="padding:0;overflow:hidden;color:inherit"
              :to="{ path: '/blog/post', query: { slug: r.slug } }"
            >
              <div style="height:110px;overflow:hidden;background:var(--rose-pale)">
                <img :src="r.cover || PH" :alt="r.title" style="width:100%;height:100%;object-fit:cover" loading="lazy" @error="coverFallback">
              </div>
              <div style="padding:12px 14px">
                <b style="display:block;font-size:13.5px;font-family:var(--font-title)">{{ r.title }}</b>
                <div style="font-size:12px;color:var(--gray);margin-top:4px">{{ (r.published_at || '').slice(0, 10) }}</div>
              </div>
            </router-link>
          </div>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
/* 作者行 + 阅读时长 chip */
.post-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 13px; color: var(--gray); margin-bottom: 22px; }
.read-chip { background: var(--rose-pale); color: var(--plum); border-radius: 999px; padding: 2px 10px; font-size: 12px; font-weight: 600; }

/* 正文排版补全（v-html 内容经 :deep 穿透）：68ch 可读行宽 + h3/h4 层级 + 品牌链接/图片样式
 * + 列表（ul/ol）+ 引用块（rose 左边条 + rose-pale 底）+ 行内代码 */
.prose { max-width: 68ch; }
/* markdown # 一级标题映射为 h2：比 h3/h4 高一级的字号与边距 */
.prose :deep(h2) { font-family: var(--font-title); font-size: 22px; margin: 30px 0 12px; color: var(--ink); }
.prose :deep(h3) { font-family: var(--font-title); font-size: 19px; margin: 26px 0 10px; color: var(--ink); }
.prose :deep(h4) { font-family: var(--font-title); font-size: 16px; margin: 20px 0 8px; color: var(--ink); }
.prose :deep(h5) { font-family: var(--font-title); font-size: 14.5px; margin: 16px 0 6px; color: var(--ink); }
.prose :deep(a) { color: var(--plum); text-decoration: underline; text-underline-offset: 3px; text-decoration-color: var(--rose); }
.prose :deep(a:hover) { text-decoration-color: var(--plum); }
.prose :deep(img) { border-radius: 12px; margin: 16px 0; }
.prose :deep(ul), .prose :deep(ol) { margin: 12px 0; padding-left: 22px; }
.prose :deep(li) { margin: 4px 0; }
.prose :deep(blockquote) { margin: 16px 0; padding: 10px 16px; border-left: 3px solid var(--rose); background: var(--rose-pale); border-radius: 0 10px 10px 0; }
.prose :deep(blockquote p) { margin: 4px 0; }
.prose :deep(code) { background: var(--cream); border: 1px solid var(--gray-light); border-radius: 6px; padding: 1px 6px; font-size: .88em; font-family: ui-monospace, SFMono-Regular, Consolas, Menlo, monospace; }
/* 首段 drop-cap：font-title 3em rose（纯静态，无动画） */
.prose :deep(p:first-child::first-letter) { font-family: var(--font-title); font-size: 3em; font-weight: 700; color: var(--rose); float: left; line-height: .82; padding: 3px 8px 0 0; }
@media (max-width: 768px) {
  .grid { grid-template-columns: 1fr !important; }
}
</style>
