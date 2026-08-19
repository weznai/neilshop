<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../api/client'

const posts = ref([])
onMounted(async () => {
  try { posts.value = (await req('GET', '/api/content/posts')).items || [] } catch (_) { posts.value = [] }
})
const SEED = [
  { slug: 'press-on-101', title: 'Press-on 101: your first set', tag: 'GUIDES', min: 4, d: '2026-08-02', img: 'https://placehold.co/400x240/F5D8DA/6D2E46?text=Press-on+101' },
  { slug: 'magnetic-lash-hack', title: 'The 5-second magnetic lash hack', tag: 'LASHES', min: 3, d: '2026-07-21', img: 'https://placehold.co/400x240/DDD6E8/552338?text=Lash+Hack' },
  { slug: 'nail-trends-f26', title: 'Fall / Winter 2026 nail trends', tag: 'TRENDS', min: 6, d: '2026-07-10', img: 'https://placehold.co/400x240/FBEBD4/8A6D3B?text=Trends' },
  { slug: ' behind-the-glue', title: "What's actually in our glue", tag: 'INSIDE', min: 5, d: '2026-06-28', img: 'https://placehold.co/400x240/E8B4B8/552338?text=Glue' },
]
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head"><h2 class="section-title">The GLOWMAG Journal</h2></div>
      <div class="grid grid-3">
        <router-link v-for="p in posts.length ? posts : SEED" :key="p.slug" class="card blog-card" :to="{ path: '/blog/post', query: { slug: p.slug } }" style="padding:0;overflow:hidden;color:inherit">
          <div style="height:180px;overflow:hidden;background:var(--rose-pale)">
            <img :src="p.cover_image || p.img" :alt="p.title" style="width:100%;height:100%;object-fit:cover" loading="lazy">
          </div>
          <div style="padding:16px 18px 18px">
            <span class="tag tag-pending">{{ (p.tag || 'JOURNAL').toUpperCase() }}</span>
            <b style="display:block;font-size:15.5px;margin:8px 0 6px;font-family:var(--font-title)">{{ p.title }}</b>
            <div style="font-size:12px;color:var(--gray)">{{ (p.published_at || p.d || '').slice(0, 10) }} · {{ p.min || 4 }} min read</div>
          </div>
        </router-link>
      </div>
    </div>
  </section>
</template>
