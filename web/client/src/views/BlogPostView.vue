<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../api/client'

const route = useRoute()
const post = ref(null)
const err = ref(false)
const loading = ref(true)
const related = ref([])

function esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
function inline(t) {
  return t
    /* 图片语法 ![alt](url)：仅允许 src/alt 属性，URL 限 http(s)（先于链接规则匹配） */
    .replace(/!\[([^\]]*)\]\((https?:\/\/[^)\s]+)\)/g, '<img src="$2" alt="$1">')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
}
function mdHtml(md) {
  const lines = esc(md).split(/\r?\n/)
  const out = []
  let inList = false
  for (const raw of lines) {
    const l = raw.trim()
    if (!l) { if (inList) { out.push('</ul>'); inList = false } continue }
    let m
    if ((m = l.match(/^(#{1,4})\s+(.*)$/))) {
      if (inList) { out.push('</ul>'); inList = false }
      const h = Math.min(m[1].length + 1, 4)
      out.push(`<h${h}>${inline(m[2])}</h${h}>`)
    } else if ((m = l.match(/^[-*]\s+(.*)$/))) {
      if (!inList) { out.push('<ul>'); inList = true }
      out.push(`<li>${inline(m[1])}</li>`)
    } else {
      if (inList) { out.push('</ul>'); inList = false }
      out.push(`<p>${inline(l)}</p>`)
    }
  }
  if (inList) out.push('</ul>')
  return out.join('')
}
const body = computed(() => mdHtml(post.value?.content_md || ''))
const PH = 'https://placehold.co/1200x600/F5D8DA/6D2E46?text=GLOWMAG+Journal'
function coverFallback(e) { e.target.src = PH }

async function loadRelated(p) {
  related.value = []
  const t = (p.tags || [])[0]
  try {
    if (t) {
      const d = await req('GET', `/api/content/articles?page=1&size=4&tag=${encodeURIComponent(t)}`)
      related.value = (d.items || []).filter((x) => x.slug !== p.slug).slice(0, 3)
    }
    if (!related.value.length) {
      const d = await req('GET', '/api/content/articles?page=1&size=4')
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
     * publisher 补 logo（站内 favicon 绝对路径）；mainEntityOfPage 指向当前页） */
    try {
      const origin = typeof location !== 'undefined' ? location.origin : ''
      window.dispatchEvent(new CustomEvent('gm:seo', { detail: {
        title: post.value.title + ' | GLOWMAG Blog',
        description: (post.value.summary || '').slice(0, 160),
        image: post.value.cover, type: 'article',
        jsonLd: {
          '@context': 'https://schema.org', '@type': 'Article',
          headline: post.value.title, image: post.value.cover ? [post.value.cover] : undefined,
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
watch(() => route.query.slug, () => { if (route.name === 'blog-post') load() })
onMounted(load)
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:720px">
      <div v-if="loading" class="skeleton" style="min-height:320px" />

      <div v-else-if="err" class="card" style="padding:44px;text-align:center">
        <div style="font-size:38px;margin-bottom:8px">💅</div>
        <b style="font-size:16px">Post not found</b>
        <p style="font-size:13.5px;color:var(--gray);margin:8px 0 16px">
          This story moved or never existed — the journal still has plenty of glam.
        </p>
        <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap">
          <router-link to="/blog" class="btn btn-primary btn-sm">Back to journal</router-link>
          <router-link to="/store" class="btn btn-secondary btn-sm">Shop the looks</router-link>
        </div>
      </div>

      <template v-else-if="post">
        <div style="border-radius:18px;overflow:hidden;margin-bottom:22px;aspect-ratio:2/1;background:var(--rose-pale)">
          <img :src="post.cover || PH" :alt="post.title" style="width:100%;height:100%;object-fit:cover" @error="coverFallback">
        </div>
        <span v-for="t in (post.tags || []).slice(0, 3)" :key="t" class="tag tag-cat" style="margin-right:6px">{{ t.toUpperCase() }}</span>
        <h1 style="font-family:var(--font-title);font-size:32px;margin:12px 0 8px">{{ post.title }}</h1>
        <div style="font-size:13px;color:var(--gray);margin-bottom:22px">
          {{ (post.published_at || '').slice(0, 10) }} · By {{ post.author || 'GLOWMAG Team' }}
        </div>
        <article class="prose" style="font-size:15px" v-html="body" />

        <div v-if="related.length" style="margin-top:44px">
          <h3 style="font-family:var(--font-title);font-size:20px;margin-bottom:16px">Keep reading</h3>
          <div class="grid" style="grid-template-columns:repeat(3,1fr);gap:14px">
            <router-link
              v-for="r in related" :key="r.slug"
              class="card card-lift" style="padding:0;overflow:hidden;color:inherit"
              :to="{ path: '/blog/post', query: { slug: r.slug } }"
            >
              <div style="height:110px;overflow:hidden;background:var(--rose-pale)">
                <img :src="r.cover" :alt="r.title" style="width:100%;height:100%;object-fit:cover" loading="lazy">
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
.skeleton {
  background: linear-gradient(90deg, var(--gray-light) 25%, #fff 50%, var(--gray-light) 75%);
  background-size: 200% 100%;
  animation: gmSk 1.2s ease-in-out infinite;
  border-radius: 12px;
}
@keyframes gmSk { from { background-position: 200% 0 } to { background-position: -200% 0 } }
@media (max-width: 768px) {
  .grid { grid-template-columns: 1fr !important; }
}
</style>
