<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../api/client'

const tab = ref('reviews')
const reviews = ref([])
const faqs = ref([])
const articles = ref([])
const ugc = ref([])
const loaded = ref(false)
const RV = {}

async function load() {
  loaded.value = false
  try { reviews.value = (await req('GET', '/api/admin/ops/reviews?status=')).items || [] } catch (_) { /* */ }
  try { faqs.value = (await req('GET', '/api/admin/ops/faqs')).items || [] } catch (_) { /* */ }
  try { articles.value = (await req('GET', '/api/admin/ops/articles?page=1&size=50')).items || [] } catch (_) { /* */ }
  try { ugc.value = (await req('GET', '/api/admin/ops/ugc?status=0')).items || [] } catch (_) { /* */ }
  loaded.value = true
}
onMounted(load)

async function reviewAct(r, approve) {
  await req('POST', `/api/admin/ops/reviews/${r.id}/${approve ? 'approve' : 'reject'}`)
  window.$gmToast('已' + (approve ? '通过' : '驳回') + ' ✓', 'success')
  load()
}
async function ugcAct(u, approve) {
  await req('POST', `/api/admin/ops/ugc/${u.id}/${approve ? 'approve' : 'reject'}`)
  window.$gmToast('操作成功 ✓', 'success')
  load()
}
async function delFaq(f) {
  if (!confirm('删除 FAQ #' + f.id + '？')) return
  await req('DELETE', '/api/admin/ops/faqs/' + f.id)
  faqs.value = faqs.value.filter((x) => x.id !== f.id)
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">内容管理</h1>
      <span style="font-size:12.5px;color:var(--gray)">评价审核 / FAQ / 博客 / UGC</span>
    </div>
  </div>

  <div class="otab" style="display:flex;gap:4px;border-bottom:1.5px solid var(--gray-light);margin-bottom:14px">
    <button
      v-for="[k, label] in [['reviews', `评价审核 (${reviews.filter(r => r.status === 0).length})`], ['ugc', `UGC (${ugc.length})`], ['faqs', `FAQ (${faqs.length})`], ['articles', `博客 (${articles.length})`]]"
      :key="k"
      style="padding:9px 16px;font-size:13.5px;font-weight:600;border:none;background:none;cursor:pointer"
      :style="{ color: tab === k ? 'var(--plum)' : 'var(--gray)', borderBottom: tab === k ? '2.5px solid var(--plum)' : '2.5px solid transparent' }"
      @click="tab = k"
    >{{ label }}</button>
  </div>

  <div v-if="tab === 'reviews'" class="card" style="padding:0">
    <div v-for="r in reviews" :key="r.id" style="display:flex;gap:14px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--gray-light);font-size:13px">
      <div style="flex:1">
        <div><b>#{{ r.product_id }}</b> · {{ '★'.repeat(r.rating || 0) }} · {{ r.reviewer_name || '匿名' }}</div>
        <div style="color:var(--gray);margin-top:4px;max-width:560px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ r.content }}</div>
      </div>
      <span class="tag" :class="r.status === 1 ? 'tag-done' : 'tag-pending'">{{ ['待审', '已发布', '已驳回'][r.status] || '待审' }}</span>
      <template v-if="r.status === 0">
        <button class="btn btn-primary btn-sm" @click="reviewAct(r, true)">通过</button>
        <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="reviewAct(r, false)">驳回</button>
      </template>
    </div>
    <div v-if="loaded && !reviews.length" style="text-align:center;color:var(--gray);padding:24px 0">暂无评价</div>
  </div>

  <div v-else-if="tab === 'ugc'" class="card" style="padding:0">
    <div v-for="u in ugc" :key="u.id" style="display:flex;gap:14px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--gray-light);font-size:13px">
      <img :src="u.image_url" alt="UGC" style="width:52px;height:52px;border-radius:9px;object-fit:cover">
      <div style="flex:1">
        <b>{{ u.instagram_handle || '游客' }}</b>
        <div style="color:var(--gray)">{{ (u.created_at || '').slice(0, 10) }}</div>
      </div>
      <button class="btn btn-primary btn-sm" @click="ugcAct(u, true)">上架</button>
      <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="ugcAct(u, false)">拒绝</button>
    </div>
    <div v-if="loaded && !ugc.length" style="text-align:center;color:var(--gray);padding:24px 0">暂无待审 UGC</div>
  </div>

  <div v-else-if="tab === 'faqs'" class="card" style="padding:0">
    <div v-for="f in faqs" :key="f.id" style="display:flex;gap:14px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--gray-light);font-size:13px">
      <div style="flex:1"><b>{{ f.question }}</b><div style="color:var(--gray);margin-top:3px;max-width:560px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ f.answer }}</div></div>
      <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="delFaq(f)">删除</button>
    </div>
    <div v-if="loaded && !faqs.length" style="text-align:center;color:var(--gray);padding:24px 0">暂无 FAQ</div>
  </div>

  <div v-else class="card" style="padding:0">
    <div v-for="a in articles" :key="a.id" style="display:flex;gap:14px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--gray-light);font-size:13px">
      <div style="flex:1"><b>{{ a.title }}</b><div style="color:var(--gray)">{{ (a.published_at || '').slice(0, 10) }} · {{ a.slug }}</div></div>
      <span class="tag" :class="a.published ? 'tag-paid' : 'tag-pending'">{{ a.published ? '已发布' : '草稿' }}</span>
    </div>
    <div v-if="loaded && !articles.length" style="text-align:center;color:var(--gray);padding:24px 0">暂无文章</div>
  </div>
</template>
