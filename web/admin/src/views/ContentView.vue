<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import { dDate, dt } from '../composables/format'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const route = useRoute()
const router = useRouter()
const tab = ref('reviews')
const reviews = ref([])
const faqs = ref([])
const articles = ref([])
const ugc = ref([])
const loaded = ref(false)
const pendingOnly = ref(true)
const FAQ_CATS = { 1: '尺码', 2: '佩戴', 3: '物流', 4: '退换', 5: '保养', 6: '账户' }
/* 语义色统一：已上架=tag-paid（绿）全站一致 */
const UGC_STATUS = { 0: ['待审', 'tag-pending'], 1: ['已上架', 'tag-paid'], 2: ['已拒绝', 'tag-error'] }

/* 四列表错误态：失败 toast + 卡内错误 EmptyState（重试入口） */
const errs = reactive({ reviews: false, faqs: false, articles: false, ugc: false })

/* 评价分页：后端支持 page/size（size ≤100），响应含 total */
const REV_SIZE = 50
const revPage = ref(1)
const revTotal = ref(0)
const revPending = ref(0)        /* tab 角标：status=0 的 total（独立探测，不随视图筛选漂移） */
const revPages = computed(() => Math.max(1, Math.ceil(revTotal.value / REV_SIZE)))
const revRating = ref(0)          /* 星级筛选：0 全部 / 1-5 星 */
const revProduct = ref(0)         /* 商品筛选：0 全部 / product_id（选项来自商品标题映射，onMounted 已拉取） */
/* 评价空态文案：星级/商品筛选生效→未匹配（仅待审视图保持“处理完”正向文案） */
const revFiltered = computed(() => revRating.value > 0 || revProduct.value > 0)

/* 批量审核勾选（评价）：仅 status=0 行可勾；翻页/筛选重拉时清空（见 loadReviews） */
const revSel = ref([])
const revPendingIds = computed(() => reviews.value.filter((r) => r.status === 0).map((r) => r.id))
const revAllChecked = computed(() => revPendingIds.value.length > 0 && revPendingIds.value.every((id) => revSel.value.includes(id)))
function toggleRevAll() { revSel.value = revAllChecked.value ? [] : [...revPendingIds.value] }
function toggleRevSel(id) {
  const i = revSel.value.indexOf(id)
  if (i > -1) revSel.value.splice(i, 1)
  else revSel.value.push(id)
}

/* 文章分页：GET /api/admin/ops/articles?page=&size=（size ≤100），响应含 total */
const ART_SIZE = 20
const artPage = ref(1)
const artTotal = ref(0)
const artPages = computed(() => Math.max(1, Math.ceil(artTotal.value / ART_SIZE)))
/* 文章状态筛选：status=published|draft 传后端（全部=不传）；切换回第 1 页重拉 */
const artStatus = ref(null)        /* null 全部 / 'published' 已发布 / 'draft' 草稿 */
function artTab(sv) { artStatus.value = sv; artPage.value = 1; loadArticles().catch(() => toast('文章列表加载失败', 'error')) }

/* UGC：服务端 status + page/size 分页（对齐评价模式，后端 admin_ugc 已支持）
 * 「待审 N」角标取响应 total；当前 tab 计数也用 total（后端缺 total 时回退当前页条数） */
const UGC_SIZE = 50
const ugcStatus = ref(0)          /* 0 待审 / 1 已上架 / 2 已拒绝 / null 全部 */
const ugcPage = ref(1)
const ugcTotal = ref(0)
const ugcPages = computed(() => Math.max(1, Math.ceil(ugcTotal.value / UGC_SIZE)))
const ugcPending = ref(0)         /* tab 角标：status=0 的 total */
const ugcSel = ref([])            /* 批量审核勾选（UGC）：翻页/切状态重拉时清空 */
const ugcPendingIds = computed(() => ugc.value.filter((u) => u.status === 0).map((u) => u.id))
const ugcAllChecked = computed(() => ugcPendingIds.value.length > 0 && ugcPendingIds.value.every((id) => ugcSel.value.includes(id)))
function toggleUgcAll() { ugcSel.value = ugcAllChecked.value ? [] : [...ugcPendingIds.value] }
function toggleUgcSel(id) {
  const i = ugcSel.value.indexOf(id)
  if (i > -1) ugcSel.value.splice(i, 1)
  else ugcSel.value.push(id)
}
/* UGC 空态文案：已上架/已拒绝 tab→未匹配（待审保持“处理完”、全部=暂无） */
const ugcFiltered = computed(() => ugcStatus.value === 1 || ugcStatus.value === 2)

async function loadUgc() {
  ugcSel.value = []
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
/* 待审角标刷新（评价）：独立 status=0 探测，语义与 UGC 角标一致 */
async function refreshRevPending() {
  try {
    const d = await req('GET', '/api/admin/ops/reviews?status=0&page=1&size=1')
    if (d.total != null) revPending.value = d.total
  } catch (_) { /* 探测失败保留旧值 */ }
}
function ugcTab(sv) { ugcStatus.value = sv; ugcPage.value = 1; loadUgc().catch(() => toast('UGC 列表加载失败', 'error')) }
function ugcGo(n) {
  if (n >= 1 && n <= ugcPages.value) { ugcPage.value = n; loadUgc().catch(() => toast('UGC 列表加载失败', 'error')) }
}

/* FAQ：category 筛选 + page/size 分页均传后端，响应 {items,total}（兼容裸数组回退） */
const FAQ_SIZE = 20
const faqPage = ref(1)
const faqTotal = ref(0)
const faqPages = computed(() => Math.max(1, Math.ceil(faqTotal.value / FAQ_SIZE)))
const faqCat = ref(0)              /* 0 全部 / 1-6 分类 */
function faqFilter() { faqPage.value = 1; loadFaqs().catch(() => toast('FAQ 加载失败', 'error')) }
function faqGo(n) {
  if (n >= 1 && n <= faqPages.value) { faqPage.value = n; loadFaqs().catch(() => toast('FAQ 加载失败', 'error')) }
}

/* 商品标题映射：评价/UGC 只有 product_id，用商品列表解析标题（翻页拉全，最多 10 页 × 100）；
 * 结果缓存 sessionStorage（带版本号），避免每次挂载全量拉取 */
const PT_CACHE_KEY = 'admin.productTitles.v2'   /* v2：{ts,data} 结构，键名升级防旧格式冲突 */
const PT_TTL = 10 * 60 * 1000                   /* 缓存 10 分钟，超时重拉（商品改名及时生效） */
const productTitles = reactive({})
const productName = (id) => productTitles[id] || ('商品 #' + id)
async function loadProductTitles() {
  try {
    const cached = sessionStorage.getItem(PT_CACHE_KEY)
    if (cached) {
      const { ts, data } = JSON.parse(cached)
      if (data && Date.now() - ts < PT_TTL) { Object.assign(productTitles, data); return }
    }
  } catch (_) { /* 缓存损坏则重拉 */ }
  for (let p = 1; p <= 10; p++) {
    let rows
    try { rows = (await req('GET', `/api/admin/catalog/products?page=${p}&size=100`)).items || [] }
    catch (_) { return /* 映射缺失只影响展示名 */ }
    for (const it of rows) productTitles[it.id] = it.title
    if (rows.length < 100) break
  }
  try { sessionStorage.setItem(PT_CACHE_KEY, JSON.stringify({ ts: Date.now(), data: productTitles })) } catch (_) { /* 存储不可用忽略 */ }
}

/* 评价图片 lightbox */
const lightbox = ref(null)

/* 图片加载失败占位（UGC 缩略图） */
function imgFail(row) { row.img_broken = true }

async function loadReviews() {
  revSel.value = []
  const qs = new URLSearchParams({ page: revPage.value, size: REV_SIZE })
  if (pendingOnly.value) qs.set('status', 0)
  if (revRating.value) qs.set('rating', revRating.value)
  if (revProduct.value) qs.set('product_id', revProduct.value)
  const d = await req('GET', '/api/admin/ops/reviews?' + qs)
  reviews.value = d.items || []
  revTotal.value = d.total ?? reviews.value.length
  if (pendingOnly.value && !revRating.value && !revProduct.value) revPending.value = revTotal.value
}
async function loadArticles() {
  const qs = new URLSearchParams({ page: artPage.value, size: ART_SIZE })
  if (artStatus.value) qs.set('status', artStatus.value)
  const d = await req('GET', '/api/admin/ops/articles?' + qs)
  articles.value = Array.isArray(d) ? d : (d.items || [])
  artTotal.value = d.total ?? articles.value.length
}
async function loadFaqs() {
  const qs = new URLSearchParams({ page: faqPage.value, size: FAQ_SIZE })
  if (faqCat.value) qs.set('category', faqCat.value)
  const d = await req('GET', '/api/admin/ops/faqs?' + qs)
  faqs.value = Array.isArray(d) ? d : (d.items || [])
  faqTotal.value = d.total ?? faqs.value.length
}

async function load() {
  loaded.value = false
  errs.reviews = errs.faqs = errs.articles = errs.ugc = false
  /* 首载并行拉取（各列表互不依赖），逐槽保持原错误处理 */
  const rs = await Promise.allSettled([loadReviews(), loadFaqs(), loadArticles(), loadUgc()])
  if (rs[0].status === 'rejected') { errs.reviews = true; reviews.value = []; toast('评价列表加载失败', 'error') }
  if (rs[1].status === 'rejected') { errs.faqs = true; faqs.value = []; toast('FAQ 加载失败', 'error') }
  if (rs[2].status === 'rejected') { errs.articles = true; articles.value = []; toast('文章列表加载失败', 'error') }
  if (rs[3].status === 'rejected') { errs.ugc = true; ugc.value = []; toast('UGC 列表加载失败', 'error') }
  loaded.value = true
}
/* 深链 ?tab= 直达 + 切换回写 URL（可分享） */
const TAB_KEYS = ['reviews', 'ugc', 'faqs', 'articles']
function setTab(k) {
  tab.value = k
  router.replace({ query: { ...route.query, tab: k } })
}
onMounted(() => {
  if (TAB_KEYS.includes(route.query.tab)) tab.value = route.query.tab
  /* 深链 ?pending=1/0：评价待审直达（Dashboard 以 /content?tab=reviews&pending=1 链入）；缺省保持待审 */
  if (route.query.pending !== undefined) pendingOnly.value = route.query.pending === '1'
  load()
  loadProductTitles()
  /* 深链 pending=0 进入时 loadReviews 不带 status=0，待审角标不会随列表刷新 → 挂载时独立探测一次 */
  refreshRevPending()
})

/* 审核后刷新：评价只重拉评价列表（不动其他 tab、骨架与商品映射） */
async function reloadReviews() {
  try { await loadReviews() } catch (_) { errs.reviews = true; toast('评价列表加载失败', 'error') }
  if (!pendingOnly.value) refreshRevPending()   /* 非待审视图时补一发待审计数探测 */
}
function revGo(n) {
  if (n >= 1 && n <= revPages.value) { revPage.value = n; loadReviews().catch(() => toast('评价列表加载失败', 'error')) }
}
function togglePending() {
  revPage.value = 1
  /* 待审开关回写 URL（可分享），与 ?tab= 深链同一套 replace 口径 */
  router.replace({ query: { ...route.query, pending: pendingOnly.value ? '1' : '0' } })
  loadReviews().catch(() => toast('评价列表加载失败', 'error'))
}
function artGo(n) {
  if (n >= 1 && n <= artPages.value) { artPage.value = n; loadArticles().catch(() => toast('文章列表加载失败', 'error')) }
}
/* 错误态重试：清 flag → 重拉（失败再置回） */
async function retryReviews() { errs.reviews = false; try { await loadReviews() } catch (_) { errs.reviews = true; toast('评价列表加载失败', 'error') } }
async function retryFaqs() { errs.faqs = false; try { await loadFaqs() } catch (_) { errs.faqs = true; toast('FAQ 加载失败', 'error') } }
async function retryArticles() { errs.articles = false; try { await loadArticles() } catch (_) { errs.articles = true; toast('文章列表加载失败', 'error') } }
async function retryUgc() { errs.ugc = false; try { await loadUgc() } catch (_) { errs.ugc = true; toast('UGC 列表加载失败', 'error') } }

/* 通用确认弹窗（替代原生 confirm）：askConfirm 装载标题/文案/危险态/按钮文案与待执行动作；
 * reasonLabel 模式（批量驳回评价）下 confirm 事件回传原因文本 */
const cd = reactive({ open: false, title: '', body: '', danger: false, confirmText: '确认', busy: false, reasonLabel: '', reasonPlaceholder: '', action: null })
function askConfirm(title, body, action, opts = {}) {
  Object.assign(cd, { open: true, title, body, danger: !!opts.danger, confirmText: opts.confirmText || '确认', busy: false, reasonLabel: opts.reasonLabel || '', reasonPlaceholder: opts.reasonPlaceholder || '', action })
}
function closeConfirm() { cd.open = false }
async function onCdConfirm(reason) {
  const fn = cd.action
  cd.busy = true
  try { if (fn) await fn(reason) } finally { cd.busy = false; cd.open = false }
}

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
    reloadReviews()
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}
/* 通过评价：确认后公开展示（危险确认，对齐 UGC 上架） */
function approveReview(r) {
  askConfirm('通过评价', `通过评价 #${r.id}？将通过并公开展示在前台商品页。`, async () => {
    try {
      await req('POST', `/api/admin/ops/reviews/${r.id}/approve`)
      toast('已通过 ✓', 'success')
      reloadReviews()
    } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
  }, { confirmText: '通过' })
}

/* 撤销审核（POST /{id}/unapprove：1|2 → 0 回到待审） */
function unapproveReview(r) {
  askConfirm('撤销审核', `将评价 #${r.id} 回到待审核状态？`, async () => {
    try {
      await req('POST', `/api/admin/ops/reviews/${r.id}/unapprove`)
      toast('已撤销 ✓', 'success')
      reloadReviews()
    } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
  }, { confirmText: '撤销' })
}

/* 批量审核评价（POST /reviews/bulk {ids,action,reason?}）：驳回走 reasonLabel 模式，body 提示将记录驳回原因（后端不发通知） */
function bulkReviews(action) {
  const ids = [...revSel.value]
  if (!ids.length) return
  if (action === 'reject') {
    askConfirm('批量驳回评价', `驳回选中的 ${ids.length} 条评价？将记录驳回原因。`, async (reason) => {
      try {
        const d = await req('POST', '/api/admin/ops/reviews/bulk', { ids, action, reason: reason || DEFAULT_REJECT })
        toast(`已处理 ${d.updated ?? ids.length} 条`, 'success')
        reloadReviews()
      } catch (e) { toast('批量驳回失败：' + (e.data?.detail || e.message), 'error') }
    }, { danger: true, confirmText: '驳回', reasonLabel: '驳回原因', reasonPlaceholder: '如：图片涉及第三方水印' })
  } else {
    askConfirm('批量通过评价', `通过选中的 ${ids.length} 条评价？将通过并公开展示在前台商品页。`, async () => {
      try {
        const d = await req('POST', '/api/admin/ops/reviews/bulk', { ids, action })
        toast(`已处理 ${d.updated ?? ids.length} 条`, 'success')
        reloadReviews()
      } catch (e) { toast('批量通过失败：' + (e.data?.detail || e.message), 'error') }
    }, { confirmText: '通过' })
  }
}

/* UGC 上架/拒绝：拒绝无 reason（后端 reject_ugc 不收 body），body 说明影响 */
function ugcAct(u, approve) {
  askConfirm(approve ? '上架 UGC' : '拒绝 UGC',
    approve ? `上架 UGC #${u.id}？该内容将公开展示在前台画廊。` : `拒绝 UGC #${u.id}？该内容将不会在前台展示。`,
    async () => {
      try {
        await req('POST', `/api/admin/ops/ugc/${u.id}/${approve ? 'approve' : 'reject'}`)
        toast('操作成功 ✓', 'success')
        await loadUgc()
        if (ugcStatus.value !== 0) refreshUgcPending()
      } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
    },
    { danger: !approve, confirmText: approve ? '上架' : '拒绝' })
}

/* 撤销审核（POST /ugc/{id}/unapprove：1|2 → 0 回到待审） */
function unapproveUgc(u) {
  askConfirm('撤销审核', `将 UGC #${u.id} 回到待审核状态？`, async () => {
    try {
      await req('POST', `/api/admin/ops/ugc/${u.id}/unapprove`)
      toast('已撤销 ✓', 'success')
      await loadUgc()
      if (ugcStatus.value !== 0) refreshUgcPending()
    } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
  }, { confirmText: '撤销' })
}

/* 批量审核 UGC（POST /ugc/bulk {ids,action}）：后端契约无 reason 字段 */
function bulkUgc(action) {
  const ids = [...ugcSel.value]
  if (!ids.length) return
  const approve = action === 'approve'
  askConfirm(approve ? '批量上架 UGC' : '批量拒绝 UGC',
    approve ? `上架选中的 ${ids.length} 条 UGC？将公开展示在前台画廊。` : `拒绝选中的 ${ids.length} 条 UGC？将不会在前台展示。`,
    async () => {
      try {
        const d = await req('POST', '/api/admin/ops/ugc/bulk', { ids, action })
        toast(`已处理 ${d.updated ?? ids.length} 条`, 'success')
        await loadUgc()
        if (ugcStatus.value !== 0) refreshUgcPending()
      } catch (e) { toast('批量操作失败：' + (e.data?.detail || e.message), 'error') }
    },
    { danger: !approve, confirmText: approve ? '上架' : '拒绝' })
}

/* 极简 Markdown 渲染（文章/FAQ 弹窗预览共用）：先整体转义再插入标签，防 XSS；
 * 支持 h1-h3（先长后短匹配）/ 无序列表 / 引用 / 粗体 / 斜体 / 链接 / 行内代码，对齐 client BlogPostView 先例 */
function md2html(src) {
  const esc = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
  const inline = (t) => t
    /* 行内代码先于加粗/链接，避免代码片段被二次加工 */
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/\*([^*]+)\*/g, '<i>$1</i>')
    /* 链接协议白名单：http(s) 外链新窗打开，/ 开头站内路径放行；其余（javascript: 等）剥语法留纯文本 */
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, text, href) => (/^https?:\/\//i.test(href)
      ? `<a href="${href}" target="_blank" rel="noopener">${text}</a>`
      : /^\/(?!\/)/.test(href) ? `<a href="${href}">${text}</a>` : text))
  const out = []
  let ul = false
  const closeUl = () => { if (ul) { out.push('</ul>'); ul = false } }
  for (const raw of esc(src).split(/\r?\n/)) {
    const l = raw.trim()
    let m
    if (!l) { closeUl(); continue }
    if ((m = l.match(/^###\s+(.*)$/))) { closeUl(); out.push(`<h3>${inline(m[1])}</h3>`) }
    else if ((m = l.match(/^##\s+(.*)$/))) { closeUl(); out.push(`<h2>${inline(m[1])}</h2>`) }
    else if ((m = l.match(/^#\s+(.*)$/))) { closeUl(); out.push(`<h1>${inline(m[1])}</h1>`) }
    else if ((m = l.match(/^[-*]\s+(.*)$/))) { if (!ul) { out.push('<ul>'); ul = true } out.push(`<li>${inline(m[1])}</li>`) }
    else if ((m = l.match(/^&gt;\s?(.*)$/))) { closeUl(); out.push(`<blockquote>${inline(m[1])}</blockquote>`) }
    else { closeUl(); out.push(`<p>${inline(l)}</p>`) }
  }
  closeUl()
  return out.join('')
}
/* 文章 / FAQ 弹窗各自独立的预览开关（切预览只是隐藏 textarea，v-model 内容不丢） */
const artPrev = ref(false)
const faqPrev = ref(false)

/* FAQ 增改（FaqCreateIn/FaqUpdateIn） */
const faqDlg = ref(false)
const faqForm = reactive({ id: null, category: 1, question: '', answer_md: '', sort_order: 0, active: 1 })
function newFaq() {
  Object.assign(faqForm, { id: null, category: 1, question: '', answer_md: '', sort_order: faqTotal.value + 1, active: 1 })
  faqPrev.value = false
  faqDlg.value = true
}
function editFaq(f) {
  Object.assign(faqForm, { id: f.id, category: f.category, question: f.question, answer_md: f.answer_md, sort_order: f.sort_order ?? 0, active: f.active ? 1 : 0 })
  faqPrev.value = false
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
    await loadFaqs()
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}
async function toggleFaq(f) {
  try {
    await req('PUT', '/api/admin/ops/faqs/' + f.id, { active: f.active ? 0 : 1 })
    f.active = f.active ? 0 : 1
    toast(f.active ? '已显示' : '已隐藏', 'success')
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}
function delFaq(f) {
  askConfirm('删除 FAQ', `删除 FAQ「${f.question}」？不可恢复。`, async () => {
    try {
      await req('DELETE', '/api/admin/ops/faqs/' + f.id)
      faqs.value = faqs.value.filter((x) => x.id !== f.id)
      faqTotal.value = Math.max(0, faqTotal.value - 1)
      toast('已删除', 'success')
    } catch (e) { toast('删除失败：' + (e.data?.detail || e.message), 'error') }
  }, { danger: true, confirmText: '删除' })
}

/* 文章：发布/撤稿（PUT status）、删除——发布与转草稿均需确认（转草稿会下线已发布文章） */
function toggleArticle(a) {
  if (a.status === 1) {
    askConfirm('转为草稿', `将「${a.title}」转为草稿？已发布文章将下线，前台不再展示。`, () => doToggleArticle(a), { confirmText: '转草稿' })
  } else {
    askConfirm('发布文章', `发布「${a.title}」？发布后将在前台博客可见。`, () => doToggleArticle(a), { confirmText: '发布' })
  }
}
async function doToggleArticle(a) {
  const to = a.status === 1 ? 0 : 1
  try {
    await req('PUT', '/api/admin/ops/articles/' + a.id, { status: to })
    a.status = to
    if (to === 1 && !a.published_at) a.published_at = new Date().toISOString().slice(0, 19)
    toast(to === 1 ? '已发布 ✓' : '已转为草稿', 'success')
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}
function delArticle(a) {
  askConfirm('删除文章', `删除文章「${a.title}」？不可恢复。`, async () => {
    try {
      await req('DELETE', '/api/admin/ops/articles/' + a.id)
      articles.value = articles.value.filter((x) => x.id !== a.id)
      artTotal.value = Math.max(0, artTotal.value - 1)
      toast('已删除', 'success')
    } catch (e) { toast('删除失败：' + (e.data?.detail || e.message), 'error') }
  }, { danger: true, confirmText: '删除' })
}

/* 文章前台链接：client 路由为 /blog/post?slug=（BlogPostView 按 query.slug 拉取），仅已发布可见 */
const artUrl = (a) => '/blog/post?slug=' + encodeURIComponent(a.slug)

/* ===== CSV 导出：仅当前 tab + 当前筛选，size=100 循环翻页上限 2000 行 ===== */
const exporting = ref(false)
const EXPORT_SIZE = 100
const EXPORT_MAX_ROWS = 2000
const REV_STATUS = ['待审', '已发布', '已驳回']
/* 各 tab 当前筛选参数（与列表拉取同口径） */
function exportParams() {
  if (tab.value === 'reviews') {
    /* 仅「只看待审」勾选时带 status=0，否则导出全量（与页面所见一致） */
    const qs = {}
    if (pendingOnly.value) qs.status = 0
    if (revRating.value) qs.rating = revRating.value
    if (revProduct.value) qs.product_id = revProduct.value
    return { url: '/api/admin/ops/reviews', qs }
  }
  if (tab.value === 'ugc') {
    const qs = {}
    if (ugcStatus.value !== null) qs.status = ugcStatus.value
    return { url: '/api/admin/ops/ugc', qs }
  }
  if (tab.value === 'faqs') {
    const qs = {}
    if (faqCat.value) qs.category = faqCat.value
    return { url: '/api/admin/ops/faqs', qs }
  }
  const qs = {}
  if (artStatus.value) qs.status = artStatus.value
  return { url: '/api/admin/ops/articles', qs }
}
/* 行内容按 tab 生成（列集与列表展示字段一致） */
function exportRow(it) {
  if (tab.value === 'reviews') {
    return [it.id, productName(it.product_id), it.rating || 0, it.content || '', REV_STATUS[it.status] || '待审', it.reject_reason || '', dt(it.created_at)]
  }
  if (tab.value === 'ugc') {
    return [it.id, it.instagram_handle || '游客', it.caption || '', it.related_product_id ? productName(it.related_product_id) : '', UGC_STATUS[it.status]?.[0] || '待审', it.points_rewarded || 0, dt(it.created_at)]
  }
  if (tab.value === 'faqs') {
    return [it.id, FAQ_CATS[it.category] || it.category || '', it.question, it.answer_md || '', it.sort_order ?? 0, it.active ? '显示中' : '隐藏']
  }
  return [it.id, it.slug, it.title, it.author || '', it.status === 1 ? '已发布' : '草稿', it.published_at ? dDate(it.published_at) : '', (it.tags || []).join('|')]
}
async function exportCsv() {
  if (exporting.value) return
  exporting.value = true
  try {
    const { url, qs } = exportParams()
    const fetchPage = (p) => req('GET', url + '?' + new URLSearchParams({ page: p, size: EXPORT_SIZE, ...qs }))
    const first = await fetchPage(1)
    const all = [...(first.items || [])]
    const totalMatch = first.total ?? all.length
    const maxPage = Math.min(Math.ceil(totalMatch / EXPORT_SIZE) || 1, Math.ceil(EXPORT_MAX_ROWS / EXPORT_SIZE))
    for (let p = 2; p <= maxPage; p++) {
      const d = await fetchPage(p)
      all.push(...(d.items || []))
    }
    if (all.length > EXPORT_MAX_ROWS) all.length = EXPORT_MAX_ROWS
    if (Math.ceil(totalMatch / EXPORT_SIZE) > maxPage || all.length >= EXPORT_MAX_ROWS) {
      toast('匹配结果过多，仅导出前 ' + all.length + ' 条', 'error')
    }
    const cell = (v) => {
      const s = String(v ?? '')
      return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
    }
    const head = {
      reviews: ['ID', '商品', '星级', '内容', '状态', '驳回原因', '时间'],
      ugc: ['ID', 'Instagram', '文案', '关联商品', '状态', '积分奖励', '时间'],
      faqs: ['ID', '分类', '问题', '答案', '排序', '显示'],
      articles: ['ID', 'Slug', '标题', '作者', '状态', '发布时间', '标签'],
    }[tab.value]
    const rows = [head, ...all.map(exportRow)]
    const csv = rows.map((r) => r.map(cell).join(',')).join('\n')
    const blobUrl = URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = tab.value + '_' + new Date().toISOString().slice(0, 10).replace(/-/g, '') + '.csv'
    a.click()
    URL.revokeObjectURL(blobUrl)
    toast('已导出 ' + all.length + ' 条 ✓', 'success')
  } catch (e) { toast('导出失败：' + (e.message || ''), 'error') }
  exporting.value = false
}

/* 文章新建/编辑（ArticleCreateIn：slug/title/author/content_md/tags/status/cover；slug 后端强制小写且唯一） */
const artDlg = ref(false)
const artForm = reactive({ id: null, slug: '', title: '', author: '', content_md: '', tagsStr: '', status: 0, cover: '' })
const artCoverDirty = ref(false)   /* 编辑态封面是否被改动过（未动过不提交 → 后端不改；空串=清除） */
function newArticle() {
  Object.assign(artForm, { id: null, slug: '', title: '', author: '', content_md: '', tagsStr: '', status: 0, cover: '' })
  artCoverDirty.value = false
  artPrev.value = false
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
    cover: a.cover || '',
  })
  artCoverDirty.value = false
  artPrev.value = false
  artDlg.value = true
}
async function saveArticle() {
  const slug = artForm.slug.trim().toLowerCase()
  if (!slug || !artForm.title.trim() || !artForm.author.trim() || !artForm.content_md.trim()) {
    toast('slug / 标题 / 作者 / 正文均为必填', 'error'); return
  }
  if (artForm.cover.trim().length > 500) { toast('封面 URL 不能超过 500 字符', 'error'); return }
  const body = {
    slug,
    title: artForm.title.trim(),
    author: artForm.author.trim(),
    content_md: artForm.content_md,
    tags: artForm.tagsStr.split(/[,，]/).map((t) => t.trim()).filter(Boolean),
    /* 编辑态锁定发布状态（弹窗隐藏「立即发布」，发布/转草稿只走列表行按钮）；新建按勾选 */
    status: artForm.status ? 1 : 0,
  }
  /* 封面：新建恒提交；编辑仅当动过才提交（undefined=不改，空串=清除） */
  if (!artForm.id || artCoverDirty.value) body.cover = artForm.cover.trim()
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
      <h1 class="page-title">内容管理</h1>
      <span class="page-sub">评价 / UGC / FAQ / 博客</span>
    </div>
    <div style="display:flex;gap:12px;align-items:center">
      <button class="btn btn-secondary btn-sm" :disabled="exporting" @click="exportCsv">{{ exporting ? '导出中…' : '⬇ CSV' }}</button>
      <button v-if="tab === 'faqs'" class="btn btn-primary btn-sm" @click="newFaq">＋ 新增 FAQ</button>
      <button v-if="tab === 'articles'" class="btn btn-primary btn-sm" @click="newArticle">＋ 新文章</button>
    </div>
  </div>

  <div class="otab">
    <button
      v-for="[k, label] in [['reviews', `评价 (待审 ${revPending})`], ['ugc', `UGC (待审 ${ugcPending})`], ['faqs', `FAQ (${faqTotal})`], ['articles', `博客 (${artTotal})`]]"
      :key="k"
      :class="{ on: tab === k }"
      style="background:none;border:none;cursor:pointer"
      @click="setTab(k)"
    >{{ label }}</button>
  </div>

  <!-- 评价 -->
  <div v-if="!loaded && tab === 'reviews'" class="card skeleton" style="min-height:220px"></div>
  <div v-else-if="tab === 'reviews'" class="card" style="padding:0">
    <div class="dhead" style="padding:12px 18px;border-bottom:1px solid var(--gray-light);margin-bottom:0">
      <h3 class="dtitle">评价</h3>
      <div class="filter-bar">
        <label style="display:flex;gap:8px;align-items:center;font-size:13px;color:var(--gray);cursor:pointer">
          <input v-model="pendingOnly" type="checkbox" style="width:15px;height:15px" @change="togglePending"> 只看待审
        </label>
        <label style="display:flex;gap:8px;align-items:center;font-size:13px;color:var(--gray);cursor:pointer" title="勾选当前页全部待审评价">
          <input type="checkbox" :checked="revAllChecked" :disabled="!revPendingIds.length" style="width:15px;height:15px" @change="toggleRevAll"> 全选待审
        </label>
        <select v-model.number="revRating" class="input" style="width:auto;padding:6px 10px" @change="togglePending">
          <option :value="0">全部星级</option>
          <option v-for="n in 5" :key="n" :value="n">{{ n }} 星</option>
        </select>
        <select v-model.number="revProduct" class="input" style="width:auto;max-width:220px;padding:6px 10px;text-overflow:ellipsis" title="按商品筛选评价" @change="togglePending">
          <option :value="0">全部商品</option>
          <option v-for="(title, id) in productTitles" :key="id" :value="Number(id)">{{ title }}</option>
        </select>
        <span v-if="revSel.length" style="font-size:12.5px;color:var(--plum)">已选 {{ revSel.length }} 条</span>
        <button class="btn btn-primary btn-sm" :disabled="!revSel.length" @click="bulkReviews('approve')">✓ 批量通过</button>
        <button class="btn btn-ghost btn-sm" style="color:var(--error)" :disabled="!revSel.length" @click="bulkReviews('reject')">✗ 批量驳回</button>
        <button class="btn btn-ghost btn-sm" :disabled="!revSel.length" @click="revSel = []">取消</button>
      </div>
    </div>
    <div v-for="r in reviews" :key="r.id" style="display:flex;gap:14px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--gray-light);font-size:13px;flex-wrap:wrap">
      <input v-if="r.status === 0" type="checkbox" :checked="revSel.includes(r.id)" style="width:15px;height:15px;flex:none;cursor:pointer" @change="toggleRevSel(r.id)">
      <div style="flex:1;min-width:0">
        <div><b :title="'product_id: ' + r.product_id">{{ productName(r.product_id) }}</b> · <span style="color:var(--gold)">{{ '★'.repeat(r.rating || 0) }}</span></div>
        <div style="color:var(--gray);margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="r.content">{{ r.content || '（无文字内容）' }}</div>
        <div v-if="r.status === 2 && r.reject_reason" style="color:var(--error);font-size:12px;margin-top:4px">驳回原因：{{ r.reject_reason }}</div>
        <div v-if="r.images && r.images.length" style="display:flex;gap:6px;margin-top:6px;align-items:center">
          <img v-for="(im, i) in r.images.slice(0, 4)" :key="i" :src="im" alt="" title="点击查看大图" style="width:40px;height:40px;border-radius:6px;object-fit:cover;cursor:zoom-in" @click="lightbox = im">
          <span v-if="r.images.length > 4" style="font-size:11px;color:var(--gray)">+{{ r.images.length - 4 }}</span>
        </div>
      </div>
      <span class="tag" :class="r.status === 1 ? 'tag-paid' : r.status === 2 ? 'tag-error' : 'tag-pending'">
        {{ ['待审', '已发布', '已驳回'][r.status] || '待审' }}</span>
      <template v-if="r.status === 0">
        <button class="btn btn-primary btn-sm" @click="approveReview(r)">通过</button>
        <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="askReject(r)">驳回</button>
      </template>
      <button v-else class="btn btn-ghost btn-sm" style="color:var(--gray)" @click="unapproveReview(r)">撤销审核</button>
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
      :icon="pendingOnly && !revFiltered ? '🎉' : '📭'"
      :title="revFiltered ? '未找到匹配的评价' : pendingOnly ? '没有待审评价，都处理完了' : '暂无评价'"
      :sub="revFiltered ? '试试调整或清除筛选' : ''"
    />
    <Pagination embed :page="revPage" :pages="revPages" :total="revTotal" unit="条" @go="revGo" />
  </div>

  <!-- UGC -->
  <div v-if="!loaded && tab === 'ugc'" class="card skeleton" style="min-height:220px"></div>
  <div v-else-if="tab === 'ugc'" class="card" style="padding:0">
    <div class="dhead" style="padding:12px 18px;border-bottom:1px solid var(--gray-light);margin-bottom:0">
      <h3 class="dtitle">UGC</h3>
      <div class="filter-bar">
        <button
          v-for="[sv, sl] in [[0, '待审'], [1, '已上架'], [2, '已拒绝'], [null, '全部']]" :key="String(sv)"
          class="mtab" :class="{ on: ugcStatus === sv }"
          @click="ugcTab(sv)"
        >{{ sl }}<template v-if="ugcStatus === sv">（{{ ugcTotal }}）</template></button>
        <label v-if="ugcStatus === 0" style="display:flex;gap:8px;align-items:center;font-size:13px;color:var(--gray);cursor:pointer" title="勾选当前页全部待审 UGC">
          <input type="checkbox" :checked="ugcAllChecked" :disabled="!ugcPendingIds.length" style="width:15px;height:15px" @change="toggleUgcAll"> 全选
        </label>
        <span v-if="ugcSel.length" style="font-size:12.5px;color:var(--plum)">已选 {{ ugcSel.length }} 条</span>
        <button class="btn btn-primary btn-sm" :disabled="!ugcSel.length" @click="bulkUgc('approve')">✓ 批量通过</button>
        <button class="btn btn-ghost btn-sm" style="color:var(--error)" :disabled="!ugcSel.length" @click="bulkUgc('reject')">✗ 批量驳回</button>
        <button class="btn btn-ghost btn-sm" :disabled="!ugcSel.length" @click="ugcSel = []">取消</button>
      </div>
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
        <input type="checkbox" :checked="ugcSel.includes(u.id)" style="width:15px;height:15px;flex:none;cursor:pointer" @change="toggleUgcSel(u.id)">
        <button class="btn btn-primary btn-sm" @click="ugcAct(u, true)">上架</button>
        <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="ugcAct(u, false)">拒绝</button>
      </template>
      <button v-else class="btn btn-ghost btn-sm" style="color:var(--gray)" @click="unapproveUgc(u)">撤销审核</button>
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
      :title="ugcFiltered ? '未找到匹配的 UGC' : ugcStatus === 0 ? '没有待审 UGC，都处理完了' : '暂无 UGC 投稿'"
      :sub="ugcFiltered ? '试试调整或清除筛选' : ''"
    />
    <Pagination embed :page="ugcPage" :pages="ugcPages" :total="ugcTotal" unit="条" @go="ugcGo" />
  </div>

  <!-- FAQ -->
  <div v-if="!loaded && tab === 'faqs'" class="card skeleton" style="min-height:220px"></div>
  <div v-else-if="tab === 'faqs'" class="card" style="padding:0">
    <div class="dhead" style="padding:12px 18px;border-bottom:1px solid var(--gray-light);margin-bottom:0">
      <h3 class="dtitle">FAQ</h3>
      <div class="filter-bar">
        <span style="font-size:12.5px;color:var(--gray)">分类筛选</span>
        <select v-model.number="faqCat" class="input" style="width:auto;padding:6px 10px" @change="faqFilter">
          <option :value="0">全部分类</option>
          <option v-for="(name, v) in FAQ_CATS" :key="v" :value="Number(v)">{{ name }}</option>
        </select>
        <span class="item-cnt">{{ faqTotal }} 条</span>
      </div>
    </div>
    <div v-for="f in faqs" :key="f.id" style="display:flex;gap:14px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--gray-light);font-size:13px;flex-wrap:wrap">
      <div style="flex:1;min-width:0">
        <b>{{ f.question }}</b>
        <span class="cat-chip" style="margin-left:6px">{{ FAQ_CATS[f.category] || f.category_name || f.category }}</span>
        <span style="color:var(--gray);font-size:11px;margin-left:6px">#{{ f.sort_order ?? 0 }}</span>
        <div style="color:var(--gray);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="f.answer_md">{{ f.answer_md }}</div>
      </div>
      <span class="tag" :class="f.active ? 'tag-paid' : 'tag-pending'">{{ f.active ? '显示中' : '隐藏' }}</span>
      <button class="btn btn-ghost btn-sm" @click="toggleFaq(f)">{{ f.active ? '隐藏' : '显示' }}</button>
      <button class="btn btn-secondary btn-sm" @click="editFaq(f)">编辑</button>
      <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="delFaq(f)">删除</button>
    </div>
    <EmptyState v-if="loaded && errs.faqs" icon="⚠️" title="FAQ 加载失败" sub="点击重试，或稍后再来">
      <template #action><button class="btn btn-secondary btn-sm" @click="retryFaqs">重试</button></template>
    </EmptyState>
    <EmptyState
      v-else-if="loaded && !faqs.length"
      :icon="faqCat ? '📭' : '📖'"
      :title="faqCat ? '未找到匹配的 FAQ' : '暂无 FAQ'"
      :sub="faqCat ? '试试调整或清除筛选' : '点击右上角「新增 FAQ」创建'"
    >
      <template #action><button class="btn btn-primary btn-sm" @click="newFaq">➕ 新建 FAQ</button></template>
    </EmptyState>
    <Pagination embed :page="faqPage" :pages="faqPages" :total="faqTotal" unit="条" @go="faqGo" />
  </div>

  <!-- 博客 -->
  <div v-if="!loaded && tab === 'articles'" class="card skeleton" style="min-height:220px"></div>
  <div v-else-if="tab === 'articles'" class="card" style="padding:0">
    <div class="dhead" style="padding:12px 18px;border-bottom:1px solid var(--gray-light);margin-bottom:0">
      <h3 class="dtitle">博客文章</h3>
      <div class="filter-bar">
        <button
          v-for="[sv, sl] in [[null, '全部'], ['published', '已发布'], ['draft', '草稿']]" :key="String(sv)"
          class="mtab" :class="{ on: artStatus === sv }"
          @click="artTab(sv)"
        >{{ sl }}</button>
        <span class="item-cnt">{{ artTotal }} 篇</span>
      </div>
    </div>
    <div v-for="a in articles" :key="a.id" style="display:flex;gap:14px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--gray-light);font-size:13px;flex-wrap:wrap">
      <img v-if="a.cover" :src="a.cover" alt="" style="width:52px;height:38px;border-radius:8px;object-fit:cover;flex:none">
      <div style="flex:1;min-width:0">
        <b>{{ a.title }}</b>
        <span v-for="t in (a.tags || []).slice(0, 3)" :key="t" class="cat-chip" style="margin-left:6px">{{ t }}</span>
        <div style="color:var(--gray);margin-top:3px">{{ a.published_at ? dDate(a.published_at) : '未发布' }} · {{ a.slug }} · {{ a.author || '—' }}</div>
      </div>
      <span class="tag" :class="a.status === 1 ? 'tag-paid' : 'tag-pending'">{{ a.status === 1 ? '已发布' : '草稿' }}</span>
      <a v-if="a.status === 1" class="btn btn-ghost btn-sm" :href="artUrl(a)" target="_blank" rel="noopener" title="在前台查看">↗</a>
      <button class="btn btn-secondary btn-sm" @click="editArticle(a)">编辑</button>
      <button class="btn btn-ghost btn-sm" @click="toggleArticle(a)">{{ a.status === 1 ? '转草稿' : '发布' }}</button>
      <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="delArticle(a)">删除</button>
    </div>
    <EmptyState v-if="loaded && errs.articles" icon="⚠️" title="文章列表加载失败" sub="点击重试，或稍后再来">
      <template #action><button class="btn btn-secondary btn-sm" @click="artPage = 1; retryArticles()">重试</button></template>
    </EmptyState>
    <EmptyState v-else-if="loaded && !articles.length" :icon="artStatus === null ? '📝' : '📭'" :title="artStatus === null ? '暂无文章' : '未找到匹配的文章'" :sub="artStatus === null ? '点击右上角「新文章」开始创作' : '试试调整或清除筛选'">
      <template #action><button class="btn btn-primary btn-sm" @click="newArticle">➕ 新建文章</button></template>
    </EmptyState>
    <Pagination embed :page="artPage" :pages="artPages" :total="artTotal" unit="篇" @go="artGo" />
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
        <div class="field" style="grid-column:1/-1"><label>封面图 URL（可选，空 = 无封面）</label>
          <div style="display:flex;gap:8px;align-items:center">
            <input v-model="artForm.cover" class="input" style="flex:1;min-width:0" placeholder="https://cdn.example.com/covers/nail-101.jpg" @input="artCoverDirty = true">
            <img v-if="artForm.cover" :src="artForm.cover" alt="" title="封面预览" style="width:52px;height:38px;border-radius:8px;object-fit:cover;flex:none" @error="$event.target.style.display = 'none'" @load="$event.target.style.display = ''">
          </div>
        </div>
        <div class="field" style="grid-column:1/-1"><label>正文（Markdown）</label>
          <div class="md-tabs">
            <button :class="{ on: !artPrev }" @click="artPrev = false">编辑</button>
            <button :class="{ on: artPrev }" @click="artPrev = true">预览</button>
          </div>
          <textarea v-show="!artPrev" v-model="artForm.content_md" class="input" rows="8"></textarea>
          <div v-show="artPrev" class="prose md-prev" v-html="md2html(artForm.content_md)"></div>
        </div>
        <div class="field" style="grid-column:1/-1"><label>标签（逗号分隔）</label><input v-model="artForm.tagsStr" class="input" placeholder="howto, nails"></div>
      </div>
      <!-- 发布状态：新建可选「立即发布」；编辑已发布文章时锁定（发布/转草稿走列表行按钮） -->
      <label v-if="!artForm.id" style="display:flex;gap:10px;align-items:center;font-size:13.5px;cursor:pointer;margin-top:6px">
        <input v-model.number="artForm.status" type="checkbox" :true-value="1" :false-value="0" style="width:16px;height:16px"> 立即发布（取消勾选则存为草稿）
      </label>
      <p v-else style="font-size:12px;color:var(--gray);margin-top:6px">发布状态已锁定：请使用列表行的「发布 / 转草稿」按钮切换。</p>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:14px">
        <button class="btn btn-secondary btn-sm" @click="artDlg = false">取消</button>
        <button class="btn btn-primary btn-sm" @click="saveArticle">保存</button>
      </div>
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
      <div class="field"><label>答案（Markdown）</label>
        <div class="md-tabs">
          <button :class="{ on: !faqPrev }" @click="faqPrev = false">编辑</button>
          <button :class="{ on: faqPrev }" @click="faqPrev = true">预览</button>
        </div>
        <textarea v-show="!faqPrev" v-model="faqForm.answer_md" class="input" rows="5"></textarea>
        <div v-show="faqPrev" class="prose md-prev" v-html="md2html(faqForm.answer_md)"></div>
      </div>
      <label v-if="faqForm.id" style="display:flex;gap:10px;align-items:center;font-size:13.5px;cursor:pointer;margin-top:6px">
        <input v-model.number="faqForm.active" type="checkbox" :true-value="1" :false-value="0" style="width:16px;height:16px"> 前台显示
      </label>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:14px">
        <button class="btn btn-secondary btn-sm" @click="faqDlg = false">取消</button>
        <button class="btn btn-primary btn-sm" @click="saveFaq">保存</button>
      </div>
    </div>
  </div>

  <!-- 通用确认弹窗（单条审核/删 FAQ/文章发布与删除/批量审核共用；reasonLabel 模式用于批量驳回评价） -->
  <ConfirmDialog :open="cd.open" :title="cd.title" :body="cd.body" :danger="cd.danger" :confirm-text="cd.confirmText" :reason-label="cd.reasonLabel" :reason-placeholder="cd.reasonPlaceholder" :busy="cd.busy" @confirm="onCdConfirm" @close="closeConfirm" />
</template>

<style scoped>
/* 中性分类 chips（FAQ 分类/文章标签：非状态语义，不用 tag-pending） */
.cat-chip{background:var(--gray-light);color:var(--gray);font-size:11px;border-radius:999px;padding:1px 8px}
/* Markdown 编辑/预览切换 pill（选中 plum 白字） */
.md-tabs{display:flex;gap:6px;margin-bottom:8px}
.md-tabs button{border:1px solid var(--gray-light);background:#fff;color:var(--gray);font-size:12px;font-weight:600;border-radius:999px;padding:3px 12px;cursor:pointer}
.md-tabs button.on{background:var(--plum);border-color:var(--plum);color:#fff}
/* 预览容器：对齐 textarea 视觉（限高滚动）；.prose 全局已有 p/li/ul/h2/b，此处补 h1/h3/引用/代码 */
.md-prev{max-height:300px;overflow-y:auto;border:1px solid var(--gray-light);border-radius:10px;padding:12px 14px;background:#fff;font-size:14px}
.md-prev h1{font-family:var(--font-title);font-size:20px;margin:14px 0 8px}
.md-prev h3{font-family:var(--font-title);font-size:16px;margin:12px 0 6px}
.md-prev blockquote{margin:8px 0;padding:6px 12px;border-left:3px solid var(--plum);background:var(--rose-pale);border-radius:0 8px 8px 0;color:#3A3438}
.md-prev code{background:var(--gray-light);border-radius:5px;padding:1px 6px;font-size:12.5px}
.md-prev a{color:var(--plum);font-weight:600}
</style>
