<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../api/client'

const route = useRoute()
const post = ref(null)
const err = ref(false)

onMounted(async () => {
  const slug = route.query.slug || 'press-on-101'
  try { post.value = await req('GET', '/api/content/posts/' + slug) } catch (_) { err.value = true }
})
const paragraphs = computed(() => ((post.value?.body_md || post.value?.content || '')
  .split(/\n{2,}/).filter(Boolean).slice(0, 10)))
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:720px">
      <div v-if="err" class="card" style="padding:40px;text-align:center;color:var(--gray)">
        Post not found — <router-link to="/blog" style="color:var(--plum)">back to journal</router-link>
      </div>
      <template v-else-if="post">
        <div style="border-radius:18px;overflow:hidden;margin-bottom:22px;aspect-ratio:2/1;background:var(--rose-pale)">
          <img :src="post.cover_image" :alt="post.title" style="width:100%;height:100%;object-fit:cover">
        </div>
        <span class="tag tag-pending">{{ (post.tag || 'journal').toUpperCase() }}</span>
        <h1 style="font-family:var(--font-title);font-size:32px;margin:12px 0 8px">{{ post.title }}</h1>
        <div style="font-size:13px;color:var(--gray);margin-bottom:22px">
          {{ (post.published_at || '').slice(0, 10) }} · By {{ post.author || 'GLOWMAG Team' }} · {{ post.min_read || 4 }} min read
        </div>
        <article style="font-size:15px;line-height:1.85;display:grid;gap:14px">
          <p v-for="(p, i) in paragraphs" :key="i">{{ p }}</p>
        </article>
      </template>
      <div v-else class="skeleton" style="min-height:300px" />
    </div>
  </section>
</template>
