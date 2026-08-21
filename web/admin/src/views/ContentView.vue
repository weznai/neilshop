<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import EmptyState from '../components/EmptyState.vue'

const tab = ref('reviews')
const reviews = ref([])
const faqs = ref([])
const articles = ref([])
const ugc = ref([])
const loaded = ref(false)
const pendingOnly = ref(true)
const FAQ_CATS = { 1: '尺码', 2: '佩戴', 3: '物流', 4: '退换', 5: '保养', 6: '账户' }
const UGC_STATUS = { 0: ['待审', 'tag-pending'], 1: ['已上架', 'tag-done'], 2: ['已拒绝', 'tag-error'] }

/* 四列表错误态：失败 toast + 卡内错误 EmptyState（重试入口） */
const errs = reactive({ reviews: false, faqs: false, articles: false, ugc: false })

/* 评价分页：后端支持 page/size（size ≤100），响应含 total */
const REV_SIZE = 100
const revPage = ref(1)
const revTotal = ref(0)
const revPages = computed(() => Math.max(1, Math.ceil(revTotal.value / REV_SIZE)))

/* 文章分页：GET /api/admin/ops/articles?page=&size=（size ≤100），响应含 total */
const ART_SIZE = 20
const artPage = ref(1)
const artTotal = ref(0)
const artPages = computed(() => Math.max(1, Math.ceil(artTotal.value / ART_SIZE)))

/* UGC：服务端 status + page/size 分页（对齐评价模式，后端 admin_ugc 已支持）
 * 「待审 N」角标取响应 total；当前 tab 计数也用 total（后端缺 total 时回退当前页条数） */
const UGC_SIZE = 100
const ugcStatus = ref(0)          /* 0 待审 / 1 已上架 / 2 已拒绝 / null 全部 */
const ugcPage = ref(1)
const ugcTotal = ref(0)
const ugcPages = computed(() => Math.max(1, Math.ceil(ugcTotal.value / UGC_SIZE)))
const ugcPending = ref(0)         /* tab 角标：status=0 的 total */

async function loadUgc() {
  const qs = new URLSearchParams({ page: ugcPage.value, size: UGC_SIZE })
  if (ugcStatus.value !== null) qs.set('status', ugcStatus.value)
  const d = await req('GET', '/api/admin/ops/ugc?' + qs)
  ugc.value = d.items || []
  ugcTotal.value = d.total ?? ugc.value.length
  if (ugcStatus.value === 0) ugcPending.value = ugcTotal.value
}
/* 待审角标刷新（操作后/切到其它 tab 时补一发 status=0 探测） */
async function refreshUgcPending() {
  try {
    const d = await req('GET', '/api/admin/ops/ugc?status=0&page=1&size=1')
    if (d.total != null) ugcPending.value = d.total
  } catch (_) { /* 探测失败保留旧值 */ }
}
function ugcTab(sv) { ugcStatus.value = sv; ugcPage.value = 1; loadUgc().catch(() => toast('UGC 列表加载失败', 'error')) }
function ugcGo(d) {
  const n = ugcPage.value + d
  if (n >= 1 && n <= ugcPages.value) { ugcPage.value = n; loadUgc().catch(() => toast('UGC 列表加载失败', 'error')) }
}

/* FAQ 分类筛选（后台 list 无 category 参数，前端过滤） */
const faqCat = ref(0)
const faqList = computed(() => faqs.value.filter((f) => !faqCat.value || f.category === faqCat.value))

/* 商品标题映射：评价/UGC 只有 product_id，用商品列表解析标题（GET /api/admin/catalog/products） */
const productTitles = reactive({})
const productName = (id) => productTitles[id] || ('商品 #' + id)

/* 评价图片 lightbox */
const lightbox = ref(null)

/* 图片加载失败占位（UGC 缩略图） */
function imgFail(row) { row.img_broken = true }

async function loadReviews() {
  const qs = new URLSearchParams({ page: revPage.value, size: REV_SIZE })
  if (pendingOnly.value) qs.set('status', 0)
  const d = await req('GET', '/api/admin/ops/reviews?' + qs)
  reviews.value = d.items || []
  revTotal.value = d.total ?? reviews.value.length
}
async function loadArticles() {
  const d = await req('GET', `/api/admin/ops/articles?page=${artPage.value}&size=${ART_SIZE}`)
  articles.value = d.items || []
  artTotal.value = d.total ?? articles.value.length
}
async function loadFaqs() { faqs.value = (await req('GET', '/api/admin/ops/faqs')).items || [] }

async function load() {
  loaded.value = false
  errs.reviews = errs.faqs = errs.articles = errs.ugc = false
  try { await loadReviews() } catch (_) { errs.reviews = true; reviews.value = []; toast('评价列表加载失败', 'error') }
  try { await loadFaqs() } catch (_) { errs.faqs = true; faqs.value = []; toast('FAQ 加载失败', 'error') }
  try { await loadArticles() } catch (_) { errs.articles = true; articles.value = []; toast('文章列表加载失败', 'error') }
  try { await loadUgc() } catch (_) { errs.ugc = true; ugc.value = []; toast('UGC 列表加载失败', 'error') }
  try {
    const rows = (await req('GET', '/api/admin/catalog/products?page=1&size=100')).items || []
    for (const p of rows) productTitles[p.id] = p.title
  } catch (_) { /* 标题映射缺失只影响展示名 */ }
  loaded.value = true
}
onMounted(load)

function revGo(d) {
  const n = revPage.value + d
  if (n >= 1 && n <= revPages.value) { revPage.value = n; loadReviews().catch(() => toast('评价列表加载失败', 'error')) }
}
function togglePending() { revPage.value = 1; loadReviews().catch(() => toast('评价列表加载失败', 'error')) }
function artGo(d) {
  const n = artPage.value + d
  if (n >= 1 && n <= artPages.value) { artPage.value = n; loadArticles().catch(() => toast('文章列表加载失败', 'error')) }
}
/* 错误态重试：清 flag → 重拉（失败再置回） */
async function retryReviews() { errs.reviews = false; try { await loadReviews() } catch (_) { errs.reviews = true; toast('评价列表加载失败', 'error') } }
async function retryFaqs() { errs.faqs = false; try { await loadFaqs() } catch (_) { errs.faqs = true; toast('FAQ 加载失败', 'error') } }
async function retryArticles() { errs.articles = false; try { await loadArticles() } catch (_) { errs.articles = true; toast('文章列表加载失败', 'error') } }
async function retryUgc() { errs.ugc = false; try { await loadUgc() } catch (_) { errs.ugc = true; toast('UGC 列表加载失败', 'error') } }

/* 驳回原因：自定义小弹层（ReasonIn 必填，原生 prompt 已弃用） */
const rejectDlg = ref(null) /* { review } */
const rejectReason = ref('')
const DEFAULT_REJECT = '不符合展示规范'
function askReject(r) { rejectDlg.value = r; rejectReason.value = DEFAULT_REJECT }
async function confirmReject() {
  const r = rejectDlg.value
  if (!r) return
  const reason = rejectReason.value.trim() || DEFAULT_REJECT
  try {
    await req('POST', `/api/admin/ops/reviews/${r.id}/reject`, { reason })
    toast('已驳回 ✓', 'success')
    rejectDlg.value = null
    load()
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}
async function approveReview(r) {
  /* 危险确认：与 UGC 上架对称（通过即公开展示） */
  if (!confirm(`通过评价 #${r.id}？将通过并公开展示在前台商品页。`)) return
  try {
    await req('POST', `/api/admin/ops/reviews/${r.id}/approve`)
    toast('已通过 ✓', 'success')
    load()
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}

async function ugcAct(u, approve) {
  const msg = approve ? `上架 UGC #${u.id}？（将展示在前台画廊）` : `拒绝 UGC #${u.id}？`
  if (!confirm(msg)) return
  try {
    await req('POST', `/api/admin/ops/ugc/${u.id}/${approve ? 'approve' : 'reject'}`)
    toast('操作成功 ✓', 'success')
    await loadUgc()
    if (ugcStatus.value !== 0) refreshUgcPending()
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}

/* FAQ 增改（FaqCreateIn/FaqUpdateIn） */
const faqDlg = ref(false)
const faqForm = reactive({ id: null, category: 1, question: '', answer_md: '', sort_order: 0, active: 1 })
function newFaq() {
  Object.assign(faqForm, { id: null, category: 1, question: '', answer_md: '', sort_order: faqs.value.length + 1, active: 1 })
  faqDlg.value = true
}
function editFaq(f) {
  Object.assign(faqForm, { id: f.id, category: f.category, question: f.question, answer_md: f.answer_md, sort_order: f.sort_order ?? 0, active: f.active ? 1 : 0 })
  faqDlg.value = true
}
async function saveFaq() {
  if (!faqForm.question.trim() || !faqForm.answer_md.trim()) { toast('问题与答案必填', 'error'); return }
  const body = {
    category: faqForm.category, question: faqForm.question.trim(),
    answer_md: faqForm.answer_md.trim(), sort_order: faqForm.sort_order | 0,
  }
  try {
    if (faqForm.id) await req('PUT', '/api/admin/ops/faqs/' + faqForm.id, { ...body, active: faqForm.active })
    else await req('POST', '/api/admin/ops/faqs', body)
    toast(faqForm.id ? '已保存 ✓' : '已新增 ✓', 'success')
    faqDlg.value = false
    faqs.value = (await req('GET', '/api/admin/ops/faqs')).items || []
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}
async function toggleFaq(f) {
  try {
    await req('PUT', '/api/admin/ops/faqs/' + f.id, { active: f.active ? 0 : 1 })
    f.active = f.active ? 0 : 1
    toast(f.active ? '已显示' : '已隐藏', 'success')
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}
async function delFaq(f) {
  if (!confirm('删除 FAQ #' + f.id + '？')) return
  try {
    await req('DELETE', '/api/admin/ops/faqs/' + f.id)
    faqs.value = faqs.value.filter((x) => x.id !== f.id)
    toast('已删除', 'success')
  } catch (e) { toast('删除失败：' + (e.data?.detail || e.message), 'error') }
}

/* 文章：发布/撤稿（PUT status）、删除 */
async function toggleArticle(a) {
  const to = a.status === 1 ? 0 : 1
  if (to === 1 && !confirm(`发布「${a.title}」？`)) return
  try {
    await req('PUT', '/api/admin/ops/articles/' + a.id, { status: to })
    a.status = to
    if (to === 1 && !a.published_at) a.published_at = new Date().toISOString().slice(0, 19)
    toast(to === 1 ? '已发布 ✓' : '已转为草稿', 'success')
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}
async function delArticle(a) {
  if (!confirm(`删除文章「${a.title}」？不可恢复。`)) return
  try {
    await req('DELETE', '/api/admin/ops/articles/' + a.id)
    articles.value = articles.value.filter((x) => x.id !== a.id)
    artTotal.value = Math.max(0, artTotal.value - 1)
    toast('已删除', 'success')
  } catch (e) { toast('删除失败：' + (e.data?.detail || e.message), 'error') }
}

/* 文章新建/编辑（ArticleCreateIn：slug/title/author/content_md/tags/status；slug 后端强制小写且唯一） */
const artDlg = ref(false)
const artForm = reactive({ id: null, slug: '', title: '', author: '', content_md: '', tagsStr: '', status: 0 })
function newArticle() {
  Object.assign(artForm, { id: null, slug: '', title: '', author: '', content_md: '', tagsStr: '', status: 0 })
  artDlg.value = true
}
function editArticle(a) {
  Object.assign(artForm, {
    id: a.id,
    slug: a.slug || '',
    title: a.title || '',
    author: a.author || '',
    content_md: a.content_md || '',
    tagsStr: (a.tags || []).join(', '),
    status: a.status ?? 0,
  })
  artDlg.value = true
}
async function saveArticle() {
  const slug = artForm.slug.trim().toLowerCase()
  if (!slug || !artForm.title.trim() || !artForm.author.trim() || !artForm.content_md.trim()) {
    toast('slug / 标题 / 作者 / 正文均为必填', 'error'); return
  }
  const body = {
    slug,
    title: artForm.title.trim(),
    author: artForm.author.trim(),
    content_md: artForm.content_md,
    tags: artForm.tagsStr.split(/[,，]/).map((t) => t.trim()).filter(Boolean),
    status: artForm.status ? 1 : 0,
  }
  try {
    if (artForm.id) await req('PUT', '/api/admin/ops/articles/' + artForm.id, body)
    else await req('POST', '/api/admin/ops/articles', body)
    artDlg.value = false
    await loadArticles()
    toast(artForm.id ? '文章已保存 ✓' : '文章已创建 ✓', 'success')
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">内容管理</h1>
      <span style="font-size:12.5px;color:var(--gray)">评价 / UGC / FAQ / 博客</span>
    </div>
    <div style="display:flex;gap:12px;align-items:center">
      <label v-if="tab === 'reviews'" style="display:flex;gap:8px;align-items:center;font-size:13px;color:var(--gray);cursor:pointer">
        <input v-model="pendingOnly" type="checkbox" style="width:15px;height:15px" @change="togglePending"> 只看待审
      </label>
      <button v-if="tab === 'faqs'" class="btn btn-primary btn-sm" @click="newFaq">＋ 新增 FAQ</button>
      <button v-if="tab === 'articles'" class="btn btn-primary btn-sm" @click="newArticle">＋ 新文章</button>
    </div>
  </div>

  <div class="otab" style="display:flex;gap:4px;border-bottom:1.5px solid var(--gray-light);margin-bottom:14px">
    <button
      v-for="[k, label] in [['reviews', `评价 (${revTotal})`], ['ugc', `UGC (待审 ${ugcPending})`], ['faqs', `FAQ (${faqs.length})`], ['articles', `博客 (${artTotal})`]]"
      :key="k"
      style="padding:9px 16px;font-size:13.5px;font-weight:600;border:none;background:none;cursor:pointer"
      :style="{ color: tab === k ? 'var(--plum)' : 'var(--gray)', borderBottom: tab === k ? '2.5px solid var(--plum)' : '2.5px solid transparent' }"
      @click="tab = k"
    >{{ label }}</button>
  </div>

  <!-- 评价 -->
  <div v-if="!loaded && tab === 'reviews'" class="card skeleton" style="min-height:220px"></div>
  <div v-else-if="tab === 'reviews'" class="card" style="padding:0">
    <div v-for="r in reviews" :key="r.id" style="display:flex;gap:14px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--gray-light);font-size:13px;flex-wrap:wrap">
      <div style="flex:1;min-width:0">
        <div><b :title="'product_id: ' + r.product_id">{{ productName(r.product_id) }}</b> · <span style="color:var(--gold)">{{ '★'.repeat(r.rating || 0) }}</span></div>
        <div style="color:var(--gray);margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="r.content">{{ r.content || '（无文字内容）' }}</div>
        <div v-if="r.status === 2 && r.reject_reason" style="color:var(--error);font-size:12px;margin-top:4px">驳回原因：{{ r.reject_reason }}</div>
        <div v-if="r.images && r.images.length" style="display:flex;gap:6px;margin-top:6px;align-items:center">
          <img v-for="(im, i) in r.images.slice(0, 4)" :key="i" :src="im" alt="" title="点击查看大图" style="width:40px;height:40px;border-radius:6px;object-fit:cover;cursor:zoom-in" @click="lightbox = im">
          <span v-if="r.images.length > 4" style="font-size:11px;color:var(--gray)">+{{ r.images.length - 4 }}</span>
        </div>
      </div>
      <span class="tag" :class="r.status === 1 ? 'tag-done' : r.status === 2 ? 'tag-error' : 'tag-pending'">
        {{ ['待审', '已发布', '已驳回'][r.status] || '待审' }}</span>
      <template v-if="r.status === 0">
        <button class="btn btn-primary btn-sm" @click="approveReview(r)">通过</button>
        <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="askReject(r)">驳回</button>
      </template>
    </div>
    <EmptyState
      v-if="loaded && errs.reviews" icon="⚠️" title="评价列表加载失败"
      :sub="'点击重试，或稍后再来'"
    >
      <template #action>
        <button class="btn btn-secondary btn-sm" @click="retryReviews">重试</button>
      </template>
    </EmptyState>
    <EmptyState
      v-else-if="loaded && !reviews.length"
      :icon="pendingOnly ? '🎉' : '📭'"
      :title="pendingOnly ? '没有待审评价，都处理完了' : '暂无评价'"
    />
    <div v-if="revPages > 1" style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;font-size:12.5px;color:var(--gray)">
      <span>第 {{ revPage }} / {{ revPages }} 页 · 共 {{ revTotal }} 条</span>
      <div style="display:flex;gap:8px">
        <button class="btn btn-secondary btn-sm" :disabled="revPage <= 1" @click="revGo(-1)">上一页</button>
        <button class="btn btn-secondary btn-sm" :disabled="revPage >= revPages" @click="revGo(1)">下一页</button>
      </div>
    </div>
  </div>

  <!-- UGC -->
  <div v-if="!loaded && tab === 'ugc'" class="card skeleton" style="min-height:220px"></div>
  <div v-else-if="tab === 'ugc'" class="card" style="padding:0">
    <div style="display:flex;gap:8px;padding:12px 18px;border-bottom:1px solid var(--gray-light);flex-wrap:wrap">
      <button
        v-for="[sv, sl] in [[0, '待审'], [1, '已上架'], [2, '已拒绝'], [null, '全部']]" :key="String(sv)"
        class="btn btn-sm" :class="ugcStatus === sv ? 'btn-primary' : 'btn-ghost'"
        @click="ugcTab(sv)"
      >{{ sl }}<template v-if="ugcStatus === sv">（{{ ugcTotal }}）</template></button>
    </div>
    <div v-for="u in ugc" :key="u.id" style="display:flex;gap:14px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--gray-light);font-size:13px;flex-wrap:wrap">
      <img v-if="!u.img_broken" :src="u.image_url" alt="UGC" title="点击查看大图" style="width:52px;height:52px;border-radius:9px;object-fit:cover;cursor:zoom-in;flex:none" @error="imgFail(u)" @click="lightbox = u.image_url">
      <div v-else title="图片加载失败" style="width:52px;height:52px;border-radius:9px;background:var(--gray-light);color:var(--gray);display:flex;align-items:center;justify-content:center;font-size:20px;flex:none;cursor:zoom-in" @click="lightbox = u.image_url">🖼️</div>
      <div style="flex:1;min-width:0">
        <b>{{ u.instagram_handle || '游客' }}</b>
        <span v-if="u.points_rewarded" class="tag tag-paid" style="margin-left:6px;font-size:10px">+{{ u.points_rewarded }}分</span>
        <div style="color:var(--gray);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="u.caption || ''">{{ u.caption || '—' }}</div>
        <div v-if="u.related_product_id" style="color:var(--gray);font-size:11.5px;margin-top:2px">关联商品：{{ productName(u.related_product_id) }}</div>
      </div>
      <span class="tag" :class="UGC_STATUS[u.status]?.[1]">{{ UGC_STATUS[u.status]?.[0] || '待审' }}</span>
      <template v-if="u.status === 0">
        <button class="btn btn-primary btn-sm" @click="ugcAct(u, true)">上架</button>
        <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="ugcAct(u, false)">拒绝</button>
      </template>
    </div>
    <EmptyState
      v-if="loaded && errs.ugc" icon="⚠️" title="UGC 列表加载失败"
      sub="点击重试，或稍后再来"
    >
      <template #action>
        <button class="btn btn-secondary btn-sm" @click="ugcPage = 1; retryUgc()">重试</button>
      </template>
    </EmptyState>
    <EmptyState
      v-else-if="loaded && !ugc.length"
      :icon="ugcStatus === 0 ? '🎉' : '📭'"
      :title="ugcStatus === 0 ? '没有待审 UGC，都处理完了' : ugcStatus === 1 ? '暂无已上架 UGC' : ugcStatus === 2 ? '暂无已拒绝 UGC' : '暂无 UGC 投稿'"
    />
    <div v-if="ugcPages > 1" style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;font-size:12.5px;color:var(--gray)">
      <span>第 {{ ugcPage }} / {{ ugcPages }} 页 · 共 {{ ugcTotal }} 条</span>
      <div style="display:flex;gap:8px">
        <button class="btn btn-secondary btn-sm" :disabled="ugcPage <= 1" @click="ugcGo(-1)">上一页</button>
        <button class="btn btn-secondary btn-sm" :disabled="ugcPage >= ugcPages" @click="ugcGo(1)">下一页</button>
      </div>
    </div>
  </div>

  <!-- FAQ -->
  <div v-if="!loaded && tab === 'faqs'" class="card skeleton" style="min-height:220px"></div>
  <div v-else-if="tab === 'faqs'" class="card" style="padding:0">
    <div style="display:flex;gap:10px;align-items:center;padding:12px 18px;border-bottom:1px solid var(--gray-light);flex-wrap:wrap">
      <span style="font-size:12.5px;color:var(--gray)">分类筛选</span>
      <select v-model.number="faqCat" class="input" style="width:auto;padding:6px 10px">
        <option :value="0">全部分类</option>
        <option v-for="(name, v) in FAQ_CATS" :key="v" :value="Number(v)">{{ name }}</option>
      </select>
      <span style="font-size:12px;color:var(--gray)">共 {{ faqList.length }} 条</span>
    </div>
    <div v-for="f in faqList" :key="f.id" style="display:flex;gap:14px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--gray-light);font-size:13px;flex-wrap:wrap">
      <div style="flex:1;min-width:0">
        <b>{{ f.question }}</b>
        <span class="tag tag-pending" style="margin-left:6px;font-size:10px">{{ FAQ_CATS[f.category] || f.category_name || f.category }}</span>
        <span style="color:var(--gray);font-size:11px;margin-left:6px">#{{ f.sort_order ?? 0 }}</span>
        <div style="color:var(--gray);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="f.answer_md">{{ f.answer_md }}</div>
      </div>
      <span class="tag" :class="f.active ? 'tag-done' : 'tag-pending'">{{ f.active ? '显示' : '隐藏' }}</span>
      <button class="btn btn-ghost btn-sm" @click="toggleFaq(f)">{{ f.active ? '隐藏' : '显示' }}</button>
      <button class="btn btn-secondary btn-sm" @click="editFaq(f)">编辑</button>
      <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="delFaq(f)">删除</button>
    </div>
    <EmptyState v-if="loaded && errs.faqs" icon="⚠️" title="FAQ 加载失败" sub="点击重试，或稍后再来">
      <template #action><button class="btn btn-secondary btn-sm" @click="retryFaqs">重试</button></template>
    </EmptyState>
    <EmptyState
      v-else-if="loaded && !faqList.length"
      :icon="faqCat ? '📭' : '📖'"
      :title="faqCat ? '该分类暂无 FAQ' : '暂无 FAQ'"
      :sub="faqCat ? '换个分类看看' : '点击右上角「新增 FAQ」创建'"
    />
  </div>

  <!-- 博客 -->
  <div v-if="!loaded && tab === 'articles'" class="card skeleton" style="min-height:220px"></div>
  <div v-else-if="tab === 'articles'" class="card" style="padding:0">
    <div v-for="a in articles" :key="a.id" style="display:flex;gap:14px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--gray-light);font-size:13px;flex-wrap:wrap">
      <img v-if="a.cover" :src="a.cover" alt="" style="width:52px;height:38px;border-radius:8px;object-fit:cover;flex:none">
      <div style="flex:1;min-width:0">
        <b>{{ a.title }}</b>
        <span v-for="t in (a.tags || []).slice(0, 3)" :key="t" class="tag tag-pending" style="margin-left:6px;font-size:10px">{{ t }}</span>
        <div style="color:var(--gray);margin-top:3px">{{ (a.published_at || '未发布').slice(0, 10) }} · {{ a.slug }} · {{ a.author || '—' }}</div>
      </div>
      <span class="tag" :class="a.status === 1 ? 'tag-paid' : 'tag-pending'">{{ a.status === 1 ? '已发布' : '草稿' }}</span>
      <button class="btn btn-secondary btn-sm" @click="editArticle(a)">编辑</button>
      <button class="btn btn-ghost btn-sm" @click="toggleArticle(a)">{{ a.status === 1 ? '转草稿' : '发布' }}</button>
      <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="delArticle(a)">删除</button>
    </div>
    <EmptyState v-if="loaded && errs.articles" icon="⚠️" title="文章列表加载失败" sub="点击重试，或稍后再来">
      <template #action><button class="btn btn-secondary btn-sm" @click="artPage = 1; retryArticles()">重试</button></template>
    </EmptyState>
    <EmptyState v-else-if="loaded && !articles.length" icon="📝" title="暂无文章" sub="点击右上角「新文章」开始创作" />
    <div v-if="artPages > 1" style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;font-size:12.5px;color:var(--gray)">
      <span>第 {{ artPage }} / {{ artPages }} 页 · 共 {{ artTotal }} 篇</span>
      <div style="display:flex;gap:8px">
        <button class="btn btn-secondary btn-sm" :disabled="artPage <= 1" @click="artGo(-1)">上一页</button>
        <button class="btn btn-secondary btn-sm" :disabled="artPage >= artPages" @click="artGo(1)">下一页</button>
      </div>
    </div>
  </div>

  <!-- 图片查看大图（评价/UGC 共用 lightbox） -->
  <div v-if="lightbox" class="modal open" @click.self="lightbox = null">
    <div class="modal-box" style="max-width:720px;padding:18px">
      <button class="modal-x" @click="lightbox = null">×</button>
      <img :src="lightbox" alt="" style="width:100%;border-radius:10px;display:block">
    </div>
  </div>

  <!-- 驳回原因弹层（替代原生 prompt） -->
  <div v-if="rejectDlg" class="modal open" @click.self="rejectDlg = null">
    <div class="modal-box" style="max-width:420px">
      <button class="modal-x" @click="rejectDlg = null">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">驳回评价 #{{ rejectDlg.id }}</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:12px">原因将记录在 reject_reason 并反馈给用户。</p>
      <div class="field">
        <label>驳回原因</label>
        <textarea v-model="rejectReason" class="input" rows="3" placeholder="如：图片涉及第三方水印"></textarea>
      </div>
      <div style="display:flex;gap:8px;margin-top:12px">
        <button class="btn btn-ghost" style="flex:1" @click="rejectDlg = null">取消</button>
        <button class="btn btn-primary" style="flex:1" @click="confirmReject">确认驳回</button>
      </div>
    </div>
  </div>

  <!-- 文章新建/编辑弹窗（slug 唯一且小写；发布时后端补 published_at） -->
  <div v-if="artDlg" class="modal open" @click.self="artDlg = false">
    <div class="modal-box" style="max-width:640px">
      <button class="modal-x" @click="artDlg = false">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:10px">{{ artForm.id ? '✏️ 编辑文章 #' + artForm.id : '📝 新文章' }}</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="field"><label>Slug（小写，URL 路径，唯一）</label>
          <input v-model="artForm.slug" class="input" placeholder="press-on-nails-101" style="text-transform:lowercase"></div>
        <div class="field"><label>作者</label><input v-model="artForm.author" class="input" placeholder="Maya Chen"></div>
        <div class="field" style="grid-column:1/-1"><label>标题 *</label><input v-model="artForm.title" class="input"></div>
        <div class="field" style="grid-column:1/-1"><label>正文（Markdown）</label><textarea v-model="artForm.content_md" class="input" rows="8"></textarea></div>
        <div class="field" style="grid-column:1/-1"><label>标签（逗号分隔）</label><input v-model="artForm.tagsStr" class="input" placeholder="howto, nails"></div>
      </div>
      <label style="display:flex;gap:10px;align-items:center;font-size:13.5px;cursor:pointer;margin-top:6px">
        <input v-model.number="artForm.status" type="checkbox" :true-value="1" :false-value="0" style="width:16px;height:16px"> 立即发布（取消勾选则存为草稿）
      </label>
      <button class="btn btn-primary btn-block" style="margin-top:14px" @click="saveArticle">保存</button>
    </div>
  </div>

  <!-- FAQ 编辑弹窗 -->
  <div v-if="faqDlg" class="modal open" @click.self="faqDlg = false">
    <div class="modal-box" style="max-width:560px">
      <button class="modal-x" @click="faqDlg = false">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:10px">{{ faqForm.id ? '编辑 FAQ #' + faqForm.id : '新增 FAQ' }}</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="field">
          <label>分类</label>
          <select v-model.number="faqForm.category" class="input">
            <option v-for="(name, v) in FAQ_CATS" :key="v" :value="Number(v)">{{ name }}</option>
          </select>
        </div>
        <div class="field">
          <label>排序（小的在前）</label>
          <input v-model.number="faqForm.sort_order" class="input" type="number">
        </div>
      </div>
      <div class="field"><label>问题</label><input v-model="faqForm.question" class="input"></div>
      <div class="field"><label>答案（Markdown）</label><textarea v-model="faqForm.answer_md" class="input" rows="5"></textarea></div>
      <label v-if="faqForm.id" style="display:flex;gap:10px;align-items:center;font-size:13.5px;cursor:pointer;margin-top:6px">
        <input v-model.number="faqForm.active" type="checkbox" :true-value="1" :false-value="0" style="width:16px;height:16px"> 前台显示
      </label>
      <button class="btn btn-primary btn-block" style="margin-top:14px" @click="saveFaq">保存</button>
    </div>
  </div>
</template>
