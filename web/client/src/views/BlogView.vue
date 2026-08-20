<script setup>
import { computed, onMounted, ref } from 'vue'
import { req } from '../api/client'

const items = ref([])
const total = ref(0)
const page = ref(1)
const SIZE = 9
const tag = ref('')
const loading = ref(false)
const loaded = ref(false)
const err = ref(false)
const moreErr = ref(false)
const PH = 'https://placehold.co/600x400/F5D8DA/6D2E46?text=GLOWMAG'

const allTags = computed(() => [...new Set(items.value.flatMap((p) => p.tags || []))])
const hasMore = computed(() => items.value.length < total.value)

/* page 只在请求成功后推进（失败不跳页、不清空已有列表） */
async function load(reset) {
  if (loading.value) return
  loading.value = true
  err.value = false
  moreErr.value = false
  const target = reset ? 1 : page.value + 1
  try {
    const d = await req('GET', `/api/content/articles?page=${target}&size=${SIZE}` + (tag.value ? `&tag=${encodeURIComponent(tag.value)}` : ''))
    total.value = d.total || 0
    items.value = reset ? (d.items || []) : items.value.concat(d.items || [])
    page.value = target
  } catch (_) {
    if (reset) { items.value = []; total.value = 0; err.value = true }
    else moreErr.value = true
  } finally {
    loading.value = false
    loaded.value = true
  }
}
function pickTag(t) {
  tag.value = tag.value === t ? '' : t
  load(true)
}
function loadMore() { load(false) }
function coverFallback(e) { e.target.src = PH }
/* 列表摘要剥离 markdown 语法残留（加粗、链接、代码、标题符等） */
function stripMd(s) {
  return String(s || '')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]*)\]\(([^)]*)\)/g, '$1')
    .replace(/[*_`#~]/g, '')
    .trim()
}
onMounted(() => load(true))
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head"><h2 class="section-title">The GLOWMAG Journal</h2></div>

      <div v-if="allTags.length" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:22px">
        <button
          v-for="t in allTags" :key="t"
          class="trend-chip" :style="tag === t ? 'border-color:var(--plum);background:var(--rose-pale)' : ''"
          @click="pickTag(t)"
        >#{{ t }}</button>
      </div>

      <div v-if="!loaded" class="grid grid-3">
        <div v-for="i in 3" :key="i" class="card skeleton" style="min-height:280px;padding:0" />
      </div>

      <div v-else-if="err" class="card" style="padding:48px;text-align:center">
        <div style="font-size:36px;margin-bottom:8px">💅</div>
        <b>Couldn't load stories</b>
        <p style="font-size:13.5px;color:var(--gray);margin:6px 0 14px">
          Something went wrong on our side — your reading list is safe.
        </p>
        <button class="btn btn-primary btn-sm" :class="{ loading }" :disabled="loading" @click="load(true)">Try again</button>
      </div>

      <div v-else-if="!items.length" class="card" style="padding:48px;text-align:center">
        <div style="font-size:36px;margin-bottom:8px">💅</div>
        <b>No stories yet</b>
        <p style="font-size:13.5px;color:var(--gray);margin:6px 0 14px">
          {{ tag ? `Nothing tagged “${tag}” for now — check back soon.` : 'Fresh glam guides are on the way.' }}
        </p>
        <router-link v-if="tag" to="/blog" class="btn btn-secondary btn-sm" @click="pickTag(tag)">View all posts</router-link>
        <router-link v-else to="/store" class="btn btn-primary btn-sm">Shop best sellers</router-link>
      </div>

      <template v-else>
        <div class="grid grid-3">
          <router-link
            v-for="p in items" :key="p.slug" class="card blog-card card-lift"
            :to="{ path: '/blog/post', query: { slug: p.slug } }"
            style="padding:0;overflow:hidden;color:inherit"
          >
            <div style="height:180px;overflow:hidden;background:var(--rose-pale)">
              <img :src="p.cover || PH" :alt="p.title" style="width:100%;height:100%;object-fit:cover" loading="lazy" @error="coverFallback">
            </div>
            <div style="padding:16px 18px 18px">
              <span v-for="t in (p.tags || []).slice(0, 2)" :key="t" class="tag tag-cat" style="margin-right:6px">{{ t.toUpperCase() }}</span>
              <b style="display:block;font-size:15.5px;margin:8px 0 6px;font-family:var(--font-title)">{{ p.title }}</b>
              <p style="font-size:13px;color:var(--gray);line-height:1.6;margin:0 0 10px">{{ stripMd(p.summary) }}</p>
              <div style="font-size:12px;color:var(--gray)">{{ (p.published_at || '').slice(0, 10) }} · {{ p.author }}</div>
            </div>
          </router-link>
        </div>
        <div v-if="hasMore" style="text-align:center;margin-top:26px">
          <button class="btn btn-secondary" :class="{ loading }" :disabled="loading" @click="loadMore">
            {{ moreErr ? 'Retry load more' : 'Load more' }}
          </button>
          <p v-if="moreErr" style="font-size:12.5px;color:var(--error);margin-top:8px">Failed to load more — tap to retry, no posts skipped.</p>
        </div>
        <p v-else style="text-align:center;margin-top:22px;font-size:12.5px;color:var(--gray)">
          {{ items.length }} of {{ total }} posts — that's all for now ✨
        </p>
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
</style>
