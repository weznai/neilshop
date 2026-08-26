<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { useSessionStore } from '../stores/session'
import { toast } from '../composables/toast'
import { money } from '../composables/format'
import { PRODUCT_TITLES_KEY } from '../constants/cacheKeys'
import { uploadMedia, uploadErrText } from '../composables/upload'
import { md2html } from '../composables/md'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import EmptyState from '../components/EmptyState.vue'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
/* 响应式 pid：新建保存成功后 router.replace 挂 id，此处随之变为编辑态
 * （此前一次性快照导致重复保存会重复建品、变体区不出现）
 * 非法 id（NaN / <1）不静默落入新建模式：onMounted/watch 中 toast 后跳回 /products */
const pid = computed(() => {
  if (route.query.id === undefined) return null
  const n = parseInt(Array.isArray(route.query.id) ? route.query.id[0] : route.query.id, 10)
  return Number.isFinite(n) && n >= 1 ? n : null
})
const idInvalid = computed(() => route.query.id !== undefined && pid.value === null)
/* 复制模式：?copy={id} 载入源商品作底稿，但保持新建态（不设 id、slug 置空、定时清空）
 * 非法 copy（NaN/<1）与 pid 同款拦截，防落 NaN 请求或静默变新建 */
const copyId = computed(() => {
  if (route.query.copy === undefined) return null
  const n = parseInt(Array.isArray(route.query.copy) ? route.query.copy[0] : route.query.copy, 10)
  return Number.isFinite(n) && n >= 1 ? n : null
})
const copyInvalid = computed(() => route.query.copy !== undefined && copyId.value === null)

const form = reactive({
  slug: '', title: '', subtitle: '', price_min: 1599, price_max: 1599,
  compare_at_price: null, description_md: '', hero_image: '', images: [],
  video_url: '', category_id: 1, tags: [], is_new: false, is_best_seller: false,
})
const variants = ref([])
const cats = ref([])
const catsFailed = ref(false)
const busy = ref(false)
const newVar = reactive({ option1: '', option2: 'Default', price: 1599, stock: 10, weight_gram: 30, imgs: '' })
const schedAt = ref('')
const loadedSchedISO = ref(null)
const prodSched = ref(false)
const editing = ref(null)

/* ===== 图集草稿：textarea 绑定 galText 原文（超 8 行保留不截断），解析结果同步 form.images
 * 超限仅 toast 警告，保存时才截断到 8 张并提示数量 ===== */
const imgLines = (t) => (t || '').split(/\n+/).map((s) => s.trim()).filter(Boolean)
const galText = ref('')
const galLines = computed(() => imgLines(galText.value))
function setImages(arr) { form.images = arr; galText.value = arr.join('\n') }
watch(galText, () => { form.images = imgLines(galText.value) })
watch(() => galLines.value.length, (n, o) => { if (n > 8 && (o === undefined || o <= 8)) toast('最多 8 张，超出部分将被忽略', 'error') })

/* ===== 未保存变更跟踪：表单+定时一份基线；变体为即时保存，单独重置基线
 * 草稿亦纳入：newVar / 变体内联编辑中 / 翻译弹窗草稿任一非空即 dirty ===== */
const dirty = ref(false)
const formLoaded = ref(false)
const formSnap = ref('')
const varSnap = ref('')
const snapForm = () => JSON.stringify([form, schedAt.value])
const snapVars = () => JSON.stringify(variants.value)
function draftsDirty() {
  if (editing.value) return true
  if (newVar.option1.trim() || imgLines(newVar.imgs).length) return true
  if (trDlg.value && (trForm.title.trim() || trForm.subtitle.trim() || trForm.description_md.trim())) return true
  return false
}
function markClean() { formSnap.value = snapForm(); varSnap.value = snapVars(); dirty.value = draftsDirty() }
function markVarsClean() { varSnap.value = snapVars(); checkDirty() }
function checkDirty() {
  if (!formLoaded.value) return /* 加载期间触发的 watch 一律跳过，防首载误判 dirty */
  dirty.value = snapForm() !== formSnap.value || snapVars() !== varSnap.value || draftsDirty()
}
watch([form, schedAt], checkDirty, { deep: true })
watch(variants, checkDirty, { deep: true })
/* 草稿（newVar/editing/trForm）的 dirty 监听在 trForm 声明后注册（见多语言区块） */

/* ===== 离开拦截：SPA 内弹 ConfirmDialog 暂停导航；刷新/关页走原生 beforeunload ===== */
const leaveDlg = ref(false)
let pendingNext = null
onBeforeRouteLeave((to, from, next) => {
  if (!dirty.value) { next(); return }
  pendingNext = next
  leaveDlg.value = true
})
function confirmLeave() {
  leaveDlg.value = false
  dirty.value = false
  if (pendingNext) { const n = pendingNext; pendingNext = null; n() }
}
function cancelLeave() {
  leaveDlg.value = false
  if (pendingNext) { const n = pendingNext; pendingNext = null; n(false) }
}
function onUnload(e) {
  if (!dirty.value) return
  e.preventDefault()
  e.returnValue = '' /* Chrome 等需 returnValue 才弹原生离开提示 */
}

/* 图片预览失败标记：URL 变化时重置 */
const brokenHero = ref(false)
const brokenImgs = reactive({})
watch(() => form.hero_image, () => { brokenHero.value = false })
watch(() => form.images.join('\n'), () => { Object.keys(brokenImgs).forEach((k) => delete brokenImgs[k]) })

/* ===== 图片上传（POST /api/admin/media/upload，composables/upload 统一 401/403 兜底）
 * 单隐藏 input + 目标槽复用：pickImage 记来源后弹选择框，成功按目标回填；各入口共用一个 uploading ===== */
const fileInput = ref(null)
const upTarget = ref(null) /* 'hero' | 'gallery' | 'newVar' | 'editVar' */
const uploading = ref(false)
function pickImage(t) { if (uploading.value) return; upTarget.value = t; fileInput.value?.click() }
async function onPickFile(e) {
  const f = e.target.files && e.target.files[0]
  e.target.value = '' /* 复位 value，否则重选同一文件不触发 change */
  if (!f) return
  uploading.value = true
  try { applyUpUrl(await uploadMedia(f)) }
  catch (err) { const m = uploadErrText(err); if (m) toast(m, 'error') }
  finally { uploading.value = false }
}
/* 回填：主图覆盖；图集/变体图片为追加一行（各守上限，文案与保存校验一致）；图集写 galText 保持草稿同步 */
function applyUpUrl(url) {
  const t = upTarget.value
  if (t === 'hero') form.hero_image = url
  else if (t === 'gallery') {
    if (galLines.value.length >= 8) { toast('图集最多 8 张', 'error'); return }
    galText.value = appendLine(galText.value, url)
  } else if (t === 'newVar') {
    if (imgLines(newVar.imgs).length >= 6) { toast('变体图片最多 6 张（每行一张 URL）', 'error'); return }
    newVar.imgs = appendLine(newVar.imgs, url)
  } else if (t === 'editVar' && editing.value) {
    if (imgLines(editing.value.imgs).length >= 6) { toast('变体图片最多 6 张（每行一张 URL）', 'error'); return }
    editing.value.imgs = appendLine(editing.value.imgs, url)
  }
}
const appendLine = (t, url) => (t && t.trim() ? t.replace(/\s+$/, '') + '\n' + url : url)

/* 长表单锚点导航 */
const SECTIONS = [
  { id: 'sec-base', label: '基本信息' },
  { id: 'sec-pricing', label: '定价' },
  { id: 'sec-variants', label: '变体' },
  { id: 'sec-media', label: '媒体' },
  { id: 'sec-i18n', label: '多语言' },
]
function jump(id) { document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' }) }

const pad2 = (n) => String(n).padStart(2, '0')
const fmtLocal = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`

/* md2html 抽至 composables/md.js（与 ContentView 文章/FAQ 预览共用，实现完全一致） */
/* 描述编辑/预览切换（切预览只是隐藏 textarea，v-model 内容不丢） */
const descPrev = ref(false)
/* 后端 published_at 为 naive UTC（schemas._parse_published_at 统一落 UTC），展示/提交两端换算 */
const asUTC = (s) => (/[zZ]$|[+-]\d\d:\d\d$/.test(s) ? s : s + 'Z')
function schedQuick(days) { schedAt.value = fmtLocal(new Date(Date.now() + days * 864e5)) }

/* 变体分页拉全量：/api/admin/catalog/variants 支持 page/size（≤200），循环到拉满 total 防 >50 截断 */
async function loadVariants(id) {
  const all = []
  let p = 1
  let total = Infinity
  while (all.length < total && p <= 50) {
    const d = await req('GET', `/api/admin/catalog/variants?product_id=${id}&page=${p}&size=200`)
    all.push(...(d.items || []))
    total = d.total ?? all.length
    if (!(d.items || []).length) break
    p++
  }
  /* 拉满 50 页（50×200 条）仍不足 total：明确提示截断，防误以为已全量 */
  if (all.length < total) toast(`变体过多，仅加载前 ${all.length} 条`, 'error')
  /* 变体图片：优先用列表 item 的 images 字段（新契约）；老后端未回传（undefined）时
   * fallback 借前台 by-id 详情补齐（角标/编辑回显用），草稿商品或停用变体取不到则静默降级 */
  const lack = all.filter((v) => v.id && v.images === undefined)
  if (lack.length) {
    try {
      const det = await req('GET', '/api/catalog/products-by-id/' + id)
      const m = Object.fromEntries((det.variants || []).map((x) => [x.id, x.images || []]))
      lack.forEach((v) => { if (m[v.id]) v.images = m[v.id] })
    } catch (_) {}
  }
  return all
}

/* 编辑/复制加载态：期间表单整体禁用 + 覆盖层，防止用户对着默认假值保存 */
const loading = ref(false)
const loadFailed = ref(false)
const loadErrMsg = ref('')
/* 服务端商品回填（GET 载入与 PUT 保存成功后共用，回显规范化结果） */
function applyProduct(p) {
  Object.assign(form, {
    slug: p.slug, title: p.title, subtitle: p.subtitle || '',
    price_min: p.price_min, price_max: p.price_max, compare_at_price: p.compare_at_price,
    description_md: p.description_md || '', hero_image: p.hero_image || '',
    video_url: p.video_url || '',
    category_id: p.category_id, tags: p.tags || [],
    is_new: !!p.is_new, is_best_seller: !!p.is_best_seller,
  })
  setImages((p.images || []).slice(0, 8))
  prodSched.value = !!p.scheduled
  loadedSchedISO.value = p.scheduled ? new Date(asUTC(p.published_at)).toISOString() : null
  schedAt.value = loadedSchedISO.value ? fmtLocal(new Date(asUTC(p.published_at))) : ''
}

async function loadProduct(id) {
  formLoaded.value = false /* 重载期间暂停 dirty 判定，防切换编辑时误报未保存 */
  loading.value = true
  loadFailed.value = false
  try {
    const p = await req('GET', '/api/admin/catalog/products/' + id)
    applyProduct(p)
    variants.value = await loadVariants(id)
    formLoaded.value = true
    markClean()
    loadTranslations(id)
  } catch (e) {
    loadErrMsg.value = e.message || '请求失败'
    loadFailed.value = true
    /* formLoaded 仍置 true 并以当前值为基线：保证此后 dirty 跟踪生效 */
    formLoaded.value = true
    markClean()
    toast('商品加载失败：' + (e.message || ''), 'error')
  } finally { loading.value = false }
}
function retryLoad() { if (pid.value) loadProduct(pid.value) }

/* 变体操作（增/改/启停/删）成功后回刷价格区间：后端按在售变体重算，表单同步展示；
 * 仅回填两字段并重置表单基线，不触碰其他未保存编辑、不误报 dirty */
async function refreshPriceRange() {
  if (!pid.value) return
  try {
    const p = await req('GET', '/api/admin/catalog/products/' + pid.value)
    form.price_min = p.price_min
    form.price_max = p.price_max
    formSnap.value = snapForm()
  } catch (_) { /* 回刷失败不打扰：下次保存时服务端仍会重算 */ }
}

onMounted(async () => {
  window.addEventListener('beforeunload', onUnload)
  /* 非法 id（NaN/<1）：报错并跳回列表，不静默落入新建模式 */
  if (idInvalid.value) {
    toast('无效的商品 id：' + route.query.id, 'error')
    router.replace('/products')
    return
  }
  /* 非法 copy id（NaN/<1）：同上拦截，不落 NaN 请求 */
  if (copyInvalid.value) {
    toast('无效的商品 id：' + route.query.copy, 'error')
    router.replace('/products')
    return
  }
  try {
    const d = await req('GET', '/api/admin/catalog/categories')
    cats.value = Array.isArray(d) ? d : (d.items || [])
    if (!pid.value && cats.value.length && !cats.value.some((c) => c.id === form.category_id)) form.category_id = cats.value[0].id
  } catch (_) { catsFailed.value = true; toast('分类加载失败，保存前请刷新重试', 'error') }
  if (pid.value) loadProduct(pid.value)
  else if (copyId.value) loadCopy(copyId.value)
  else { formLoaded.value = true; markClean() }
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', onUnload))
/* 新建→编辑切换（同路由 query 变化）时重新拉取；id 变非法则同样拦截 */
watch(pid, (np, op) => {
  if (np && np !== op) loadProduct(np)
  else if (idInvalid.value) { toast('无效的商品 id：' + route.query.id, 'error'); router.replace('/products') }
})

/* 复制模式载入：变体/翻译剥 id 暂存，待新商品保存成功后逐个重建（sku 依新 slug 生成） */
const copyVars = ref([])
const copyTrs = ref([])
async function loadCopy(id) {
  formLoaded.value = false
  loading.value = true
  loadFailed.value = false
  try {
    const p = await req('GET', '/api/admin/catalog/products/' + id)
    Object.assign(form, {
      slug: '', title: p.title, subtitle: p.subtitle || '',
      price_min: p.price_min, price_max: p.price_max, compare_at_price: p.compare_at_price,
      description_md: p.description_md || '', hero_image: p.hero_image || '',
      video_url: p.video_url || '',
      category_id: p.category_id, tags: p.tags || [],
      is_new: !!p.is_new, is_best_seller: !!p.is_best_seller,
    })
    setImages((p.images || []).slice(0, 8))
    if (cats.value.length && !cats.value.some((c) => c.id === p.category_id)) form.category_id = cats.value[0].id
    /* 定时/状态置草稿：schedAt 清空即不随 POST 提交 published_at */
    prodSched.value = false
    loadedSchedISO.value = null
    schedAt.value = ''
    const src = await loadVariants(id)
    copyVars.value = src.map((v) => ({
      option1_value: v.option1_value, option2_value: v.option2_value || 'Default', price: v.price, stock: v.stock,
      images: (v.images || []).slice(0, 6),
    }))
    variants.value = src.map((v) => ({ ...v, id: null, sku: '', is_active: true })) /* 仅作预览，操作按钮已按 id 隐藏 */
    try { copyTrs.value = ((await req('GET', `/api/admin/catalog/products/${id}/translations`)) || []).map((t) => ({ locale: t.locale, title: t.title, subtitle: t.subtitle || null, description_md: t.description_md || null })) }
    catch (_) { copyTrs.value = [] }
    formLoaded.value = true
    markClean()
  } catch (e) {
    toast('源商品加载失败：' + (e.message || ''), 'error')
    formLoaded.value = true
    markClean()
  } finally { loading.value = false }
}

/* URL 前缀校验：主图/图集/变体图须 http(s):// 开头（空值放行） */
const badUrl = (u) => !!u && !/^https?:\/\//i.test(u)

/* 保存成功后失效 ContentView 的商品标题缓存（键名统一 constants/cacheKeys.js；新建/改名后需重拉） */
function clearTitleCache() { try { sessionStorage.removeItem(PRODUCT_TITLES_KEY) } catch (_) { /* 存储不可用忽略 */ } }

async function save() {
  if (loading.value) return
  if (!form.slug || !form.title) { toast('slug 与标题必填', 'error'); return }
  /* 新建时 slug 格式：小写字母/数字/连字符（如 nova-set） */
  if (!pid.value && !/^[a-z0-9]+(-[a-z0-9]+)*$/.test(form.slug)) { toast('slug 格式无效：仅小写字母、数字与连字符（如 nova-set）', 'error'); return }
  /* 价格（单位：分）须为非负整数；划线价可空，且须高于最低价 */
  for (const [k, label] of [['price_min', '最低价'], ['price_max', '最高价']]) {
    const v = form[k]
    if (v === null || v === '' || v === undefined || !Number.isInteger(Number(v)) || Number(v) < 0) { toast(label + '需为非负整数（单位：分）', 'error'); return }
  }
  const cap = form.compare_at_price
  if (cap !== null && cap !== '' && cap !== undefined) {
    if (!Number.isInteger(Number(cap)) || Number(cap) < 0) { toast('划线价需为非负整数（单位：分）', 'error'); return }
    if (Number(cap) <= Number(form.price_min)) { toast('划线价应高于最低价', 'error'); return }
  }
  if (!pid.value && !cats.value.length) { toast('分类未加载，无法保存，请刷新页面重试', 'error'); return }
  /* 价格倒挂直接阻止（不再静默纠正），由管理员修正后保存 */
  if (Number(form.price_max) < Number(form.price_min)) {
    toast(`价格倒挂：最高价（${form.price_max} 分）不能低于最低价（${form.price_min} 分），请修正后再保存`, 'error')
    return
  }
  if (badUrl(form.hero_image)) { toast('主图 URL 需以 http:// 或 https:// 开头', 'error'); return }
  const gi = form.images.findIndex(badUrl)
  if (gi >= 0) { toast(`图集第 ${gi + 1} 张 URL 需以 http:// 或 https:// 开头`, 'error'); return }
  /* 图集超 8 张：保存时才截断，并提示忽略数量 */
  if (form.images.length > 8) toast(`图集最多 8 张，已忽略超出部分（${form.images.length - 8} 张）`)
  busy.value = true
  const body = { ...form, images: form.images.slice(0, 8) }
  if (pid.value) delete body.slug
  if (!body.compare_at_price) body.compare_at_price = null
  const iso = schedAt.value ? new Date(schedAt.value).toISOString() : null
  if (iso !== loadedSchedISO.value) body.published_at = iso
  try {
    if (pid.value) {
      const d = await req('PUT', '/api/admin/catalog/products/' + pid.value, body)
      if (body.published_at !== undefined) {
        loadedSchedISO.value = body.published_at
        prodSched.value = body.published_at ? new Date(body.published_at) > new Date() : false
      }
      /* PUT 响应体回填表单（服务端规范化回显）后再 markClean */
      if (d && d.id) applyProduct(d)
      clearTitleCache()
      toast('保存成功 ✓', 'success')
      markClean()
    } else {
      const p = await req('POST', '/api/admin/catalog/products', body)
      /* 复制模式：新商品落库后重建变体与翻译（逐个调用；失败项汇总提示手动补录） */
      if (copyVars.value.length || copyTrs.value.length) {
        const newSlug = p.slug || form.slug
        let vok = 0, vfail = 0, tok = 0, tfail = 0, trunc = 0
        for (const v of copyVars.value) {
          const fullSku = rawSku(newSlug, v.option1_value, v.option2_value)
          if (fullSku.length > 64) trunc++
          const sku = fullSku.slice(0, 64)
          try { await req('POST', `/api/admin/catalog/products/${p.id}/variants`, { sku, option1_value: v.option1_value, option2_value: v.option2_value, price: v.price, stock: v.stock, images: v.images || [] }); vok++ }
          catch (_) { vfail++ }
        }
        for (const t of copyTrs.value) {
          try { await req('PUT', `/api/admin/catalog/products/${p.id}/translations`, { ...t }); tok++ }
          catch (_) { tfail++ }
        }
        const fails = vfail + tfail
        if (trunc) toast(`${trunc} 个变体 SKU 超长，已截断到 64 字符`, 'error')
        if (fails) toast(`副本重建：变体 ${vok}/${copyVars.value.length}、翻译 ${tok}/${copyTrs.value.length}，${fails} 项失败请手动补录`, 'error')
        copyVars.value = []
        copyTrs.value = []
      }
      clearTitleCache()
      toast('创建成功 ✓ 转编辑态', 'success')
      markClean()
      router.replace({ path: '/product-edit', query: { id: p.id } })
    }
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
  finally { busy.value = false }
}

async function addVariant() {
  if (!newVar.option1 || !newVar.option2) { toast('变体规格必填（如 Short Almond / Default）', 'error'); return }
  if (!Number.isInteger(newVar.price) || newVar.price < 0) { toast('价格需为非负整数（单位：分）', 'error'); return }
  if (!Number.isInteger(newVar.stock) || newVar.stock < 0) { toast('库存需为非负整数（单位：件）', 'error'); return }
  if (!Number.isInteger(newVar.weight_gram) || newVar.weight_gram < 0) { toast('重量需为非负整数（单位：克）', 'error'); return }
  const imgs = imgLines(newVar.imgs)
  if (imgs.length > 6) { toast('变体图片最多 6 张（每行一张 URL）', 'error'); return }
  const vi = imgs.findIndex(badUrl)
  if (vi >= 0) { toast(`变体图片第 ${vi + 1} 行 URL 需以 http:// 或 https:// 开头`, 'error'); return }
  const fullSku = rawSku(form.slug, newVar.option1, newVar.option2)
  if (fullSku.length > 64) toast(`SKU 超长（${fullSku.length} 字符），已截断到 64 字符`, 'error')
  const sku = fullSku.slice(0, 64)
  try {
    /* weight_gram 创建必填校验在上方；编辑态走 saveEdit（空=不修改） */
    await req('POST', `/api/admin/catalog/products/${pid.value}/variants`, {
      sku, option1_value: newVar.option1, option2_value: newVar.option2,
      price: newVar.price, stock: newVar.stock, weight_gram: newVar.weight_gram, images: imgs,
    })
    newVar.option1 = ''
    newVar.imgs = ''
    variants.value = await loadVariants(pid.value)
    markVarsClean()
    refreshPriceRange()
    toast('变体已添加 ✓ 价格区间已按在售变体重算', 'success')
  } catch (e) {
    const d = e.data?.detail
    if (typeof d === 'string' && d.includes('sku')) toast('添加失败：SKU 已存在——请修改规格名或联系技术', 'error')
    else toast('添加失败：' + (d || e.message), 'error')
  }
}
async function toggleVar(v) {
  try {
    await req('PUT', '/api/admin/catalog/variants/' + v.id, { is_active: !v.is_active })
    v.is_active = !v.is_active
    markVarsClean()
    refreshPriceRange()
    toast(v.is_active ? '已启用' : '已停用', 'success')
  } catch (e) { toast('操作失败', 'error') }
}
/* 删除变体：物理删除（级联清变体图/到货订阅）；被订单/购物车/退换引用 → 409 拒绝 */
const delVarDlg = ref(false)
const delVarBusy = ref(false)
const delVarTarget = ref(null)
const delVarBody = computed(() => delVarTarget.value
  ? `删除变体「${specText(delVarTarget.value)}」${delVarTarget.value.sku ? '（' + delVarTarget.value.sku + '）' : ''}？删除后不可恢复；被订单/购物车/退换引用的变体不可删除。`
  : '')
function askDelVar(v) { delVarTarget.value = v; delVarDlg.value = true }
async function doDelVar() {
  const v = delVarTarget.value
  if (!v || delVarBusy.value) return
  delVarBusy.value = true
  try {
    await req('DELETE', '/api/admin/catalog/variants/' + v.id)
    toast('变体已删除 ✓', 'success')
    delVarDlg.value = false
    variants.value = await loadVariants(pid.value)
    markVarsClean()
    refreshPriceRange()
  } catch (e) {
    if (e.status === 409) toast('该变体已被订单/退换引用，无法删除', 'error')
    else if (e.status === 404) {
      toast('变体不存在', 'error')
      delVarDlg.value = false
      variants.value = await loadVariants(pid.value)
      markVarsClean()
    }
    else toast('删除失败：' + (e.data?.detail || e.message), 'error')
  }
  delVarBusy.value = false
}
/* weight_gram 回显：无值（null/undefined）置空=不修改；PUT 契约 0..100000 */
function startEdit(v) { editing.value = { id: v.id, price: v.price, safety: v.safety_stock ?? 0, weight: v.weight_gram ?? null, imgs: (v.images || []).join('\n'), hadImgs: (v.images || []).length > 0 } }
async function saveEdit() {
  const ed = editing.value
  if (!ed) return
  if (!Number.isFinite(ed.price) || !Number.isFinite(ed.safety) || ed.price < 0 || ed.safety < 0) { toast('价格与安全库存需为非负数字', 'error'); return }
  /* 重量：空=不修改；填写才提交且须为 0..100000 整数 */
  const hasW = ed.weight !== null && ed.weight !== ''
  if (hasW && (!Number.isInteger(ed.weight) || ed.weight < 0 || ed.weight > 100000)) { toast('重量需为 0~100000 的整数（克）', 'error'); return }
  const imgs = imgLines(ed.imgs)
  if (imgs.length > 6) { toast('变体图片最多 6 张（每行一张 URL）', 'error'); return }
  const ei = imgs.findIndex(badUrl)
  if (ei >= 0) { toast(`变体图片第 ${ei + 1} 行 URL 需以 http:// 或 https:// 开头`, 'error'); return }
  try {
    /* images 仅在有输入或原有图时提交：后端缺省/null=保持原值、[]=清空，避免改价时误清图 */
    const body = { price: ed.price, safety_stock: ed.safety }
    if (hasW) body.weight_gram = ed.weight
    if (imgs.length || ed.hadImgs) body.images = imgs
    const d = await req('PUT', '/api/admin/catalog/variants/' + ed.id, body)
    const v = variants.value.find((x) => x.id === ed.id)
    if (v) { v.price = ed.price; v.safety_stock = ed.safety; if (body.weight_gram !== undefined) v.weight_gram = body.weight_gram; v.images = d.images || [] }
    editing.value = null
    markVarsClean()
    refreshPriceRange()
    toast('变体已更新 ✓', 'success')
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}
/* SKU 生成：slug-option1[-option2]（option2 有值才拼，防同 option1 不同 option2 撞码）；parts join 避免拼出 undefined
 * rawSku 保留全长用于超长提示，调用处 slice(0,64) 截断（与后端一致） */
const rawSku = (...parts) => parts.filter((p) => p && String(p).trim()).join('-').toUpperCase().replace(/\s+/g, '-')

/* 已落库且在售的变体（复制模式预览行 id=null 不算）：仅此时价格区间由在售变体自动汇总，前端只读防手工值被覆盖；
 * 全部停用时后端 _sync_price_range 保留原值 → 允许手工改价 */
const hasRealVars = computed(() => variants.value.some((v) => v.id && v.is_active))
/* 变体区头部汇总：总库存 / 变体数 / 低于安全线数量（口径同列表页 low_stock_count：stock ≤ safety） */
const varSum = computed(() => ({
  stock: variants.value.reduce((s, v) => s + (v.stock || 0), 0),
  low: variants.value.filter((v) => (v.stock || 0) <= (v.safety_stock ?? 0)).length,
}))
/* 规格展示：option2 存在且非 Default 时拼接（与库存页一致，如 "Short Almond / XL"） */
const specText = (v) => (v.option2_value && v.option2_value !== 'Default' ? v.option1_value + ' / ' + v.option2_value : v.option1_value)
/* 图集缩略图上移/下移/删除：操作 galText 行序并写回（textarea 与 form.images 同步） */
function moveImg(i, d) {
  const lines = imgLines(galText.value)
  const j = i + d
  if (j < 0 || j >= lines.length) return
  ;[lines[i], lines[j]] = [lines[j], lines[i]]
  galText.value = lines.join('\n')
}
function removeImg(i) {
  const lines = imgLines(galText.value)
  lines.splice(i, 1)
  galText.value = lines.join('\n')
}

/* ===== 多语言翻译（GET/PUT /products/{id}/translations、DELETE /{locale}；GET 返回裸数组）
 * 契约：locale 须匹配 ^[a-z]{2}-[A-Z]{2}$，title 必填，subtitle/description_md 可选 ===== */
const LOCALES = ['zh-CN', 'en-US', 'fr-FR', 'de-DE', 'ja-JP']
const LOCALE_LABEL = { 'zh-CN': '简体中文', 'en-US': 'English', 'fr-FR': 'Français', 'de-DE': 'Deutsch', 'ja-JP': '日本語' }
const translations = ref([])
const trDlg = ref(false)
const trEditing = ref(false)   /* true=编辑已有语言（locale 锁定） */
const trForm = reactive({ locale: 'zh-CN', title: '', subtitle: '', description_md: '' })
/* 草稿（newVar/editing/trForm）dirty 监听：trForm 声明后注册，防 TDZ */
watch([newVar, editing, trDlg, trForm], checkDirty, { deep: true })
async function loadTranslations(id) {
  try { translations.value = (await req('GET', `/api/admin/catalog/products/${id}/translations`)) || [] }
  catch (_) { translations.value = [] }
}
function newTr() {
  /* 默认选中尚未翻译的语言；全占时回退第一个 */
  const used = new Set(translations.value.map((t) => t.locale))
  Object.assign(trForm, { locale: LOCALES.find((l) => !used.has(l)) || LOCALES[0], title: '', subtitle: '', description_md: '' })
  trEditing.value = false
  trDlg.value = true
}
function editTr(t) {
  Object.assign(trForm, { locale: t.locale, title: t.title || '', subtitle: t.subtitle || '', description_md: t.description_md || '' })
  trEditing.value = true
  trDlg.value = true
}
async function saveTr() {
  if (!trForm.title.trim()) { toast('翻译标题必填', 'error'); return }
  if (!trEditing.value && translations.value.some((t) => t.locale === trForm.locale)) { toast('该语言已有翻译，请直接编辑', 'error'); return }
  try {
    await req('PUT', `/api/admin/catalog/products/${pid.value}/translations`, {
      locale: trForm.locale,
      title: trForm.title.trim(),
      subtitle: trForm.subtitle.trim() || null,
      description_md: trForm.description_md || null,
    })
    toast('翻译已保存 ✓', 'success')
    trDlg.value = false
    loadTranslations(pid.value)
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}
/* 删除翻译改用 ConfirmDialog（危险操作） */
const delDlgOpen = ref(false)
const delTarget = ref(null)
const delDlgBody = computed(() => {
  const t = delTarget.value
  return t ? `删除${LOCALE_LABEL[t.locale] || t.locale}（${t.locale}）翻译？前台该语言将回退默认内容。` : ''
})
function delTr(t) { delTarget.value = t; delDlgOpen.value = true }
async function doDelTr() {
  if (!delTarget.value) return
  try {
    await req('DELETE', `/api/admin/catalog/products/${pid.value}/translations/${delTarget.value.locale}`)
    toast('已删除', 'success')
    delDlgOpen.value = false
    loadTranslations(pid.value)
  } catch (e) { toast('删除失败：' + (e.data?.detail || e.message), 'error') }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">{{ pid ? '编辑商品 #' + pid : '新建商品' }}</h1>
      <span class="page-sub">{{ pid ? '保存即生效 · 上架/下架在列表页操作' : '草稿保存后可在列表页上架' }}</span>
    </div>
    <div style="display:flex;gap:10px">
      <a v-if="pid" class="btn btn-secondary" :href="'/product?id=' + pid" target="_blank" rel="noopener">前台预览 ↗</a>
      <router-link to="/products" class="btn btn-ghost">← 列表</router-link>
      <button v-if="session.hasPerm('catalog:manage')" class="btn btn-primary" :class="{ loading: busy }" :disabled="busy || loading" @click="save">保存</button>
    </div>
  </div>

  <div v-if="copyId && !pid" style="padding:10px 16px;margin-bottom:14px;background:var(--rose-pale);border:1px solid var(--rose);border-radius:10px;font-size:13px;color:var(--plum)">
    ⧉ 已从商品 #{{ copyId }} 复制，保存后生效为新商品——请填写新 Slug；{{ copyVars.length }} 个变体与 {{ copyTrs.length }} 条翻译将在保存后自动重建
  </div>

  <div class="achips">
    <button v-for="s in SECTIONS" :key="s.id" @click="jump(s.id)">{{ s.label }}</button>
  </div>

  <!-- 编辑态加载失败：错误空态 + 重试（表单隐藏，防对默认假值误保存） -->
  <div v-if="pid && loadFailed" class="card">
    <EmptyState icon="⚠️" title="商品加载失败" :sub="loadErrMsg">
      <template #action>
        <button class="btn btn-primary btn-sm" @click="retryLoad">重试</button>
        <router-link to="/products" class="btn btn-secondary btn-sm">← 返回列表</router-link>
      </template>
    </EmptyState>
  </div>

  <!-- 加载期间整体禁用（fieldset disabled）+ 覆盖层，防对默认假值操作/保存 -->
  <fieldset v-else :disabled="loading" :aria-busy="loading" class="form-shell">
  <div class="grid-2" style="align-items:start">
    <div style="display:grid;gap:16px">
      <div id="sec-base" class="card" style="padding:20px">
        <div class="dhead"><h3 class="dtitle">基本信息</h3></div>
        <div class="field"><label>标题</label><input v-model="form.title" class="input" maxlength="200"></div>
        <div v-if="!pid" class="field"><label>Slug</label><input v-model="form.slug" class="input" maxlength="150" placeholder="nova-set"></div>
        <div v-else class="field"><label>Slug（不可改）</label><input :value="form.slug" class="input" maxlength="150" disabled style="background:var(--rose-pale)"></div>
        <div class="field"><label>副标题</label><input v-model="form.subtitle" class="input" maxlength="300"></div>
        <div class="field">
          <label>分类</label>
          <select v-model="form.category_id" class="input" :disabled="!cats.length">
            <option v-if="form.category_id && !cats.some((c) => c.id === form.category_id)" :value="form.category_id">原分类 #{{ form.category_id }}（可能已删除）</option>
            <option v-for="c in cats" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
          <!-- 编辑态提交原 category_id 能保存成功，不吓唬用户；新建/复制才会因缺分类报错 -->
          <p v-if="!cats.length" :style="'font-size:11.5px;margin-top:4px;color:' + (pid ? 'var(--warn)' : 'var(--error)')">{{ pid ? '分类' + (catsFailed ? '加载失败' : '为空') + '，将按原分类保存，如需更换请刷新重试' : '分类' + (catsFailed ? '加载失败' : '为空') + '，保存会报「category not found」，请刷新重试' }}</p>
        </div>
        <div class="field"><label>描述（Markdown）</label>
          <div class="md-tabs">
            <button type="button" :class="{ on: !descPrev }" @click="descPrev = false">编辑</button>
            <button type="button" :class="{ on: descPrev }" @click="descPrev = true">预览</button>
          </div>
          <textarea v-show="!descPrev" v-model="form.description_md" class="input" rows="6"></textarea>
          <div v-show="descPrev" class="prose md-prev" v-html="md2html(form.description_md)"></div>
        </div>
      </div>

      <div id="sec-pricing" class="card" style="padding:20px">
        <div class="dhead">
          <h3 class="dtitle">定价（分）</h3>
          <span v-if="hasRealVars" style="font-size:11.5px;color:var(--gray)">存在变体时价格区间由在售变体自动汇总，手工值会被覆盖</span>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
          <div class="field"><label>最低价</label><input v-model.number="form.price_min" class="input" type="number" min="0" step="1" :disabled="hasRealVars" :style="hasRealVars ? 'background:var(--rose-pale)' : ''"><p class="phint">≈ {{ money(form.price_min) }}</p></div>
          <div class="field"><label>最高价</label><input v-model.number="form.price_max" class="input" type="number" min="0" step="1" :disabled="hasRealVars" :style="hasRealVars ? 'background:var(--rose-pale)' : ''"><p class="phint">≈ {{ money(form.price_max) }}</p></div>
          <div class="field"><label>划线价</label><input v-model.number="form.compare_at_price" class="input" type="number" min="0" step="1"><p v-if="form.compare_at_price" class="phint">≈ {{ money(form.compare_at_price) }}</p></div>
        </div>
        <p style="font-size:12px;color:var(--gray)">当前展示：{{ money(form.price_min) }}<span v-if="form.compare_at_price">（划线 {{ money(form.compare_at_price) }}）</span></p>
      </div>

      <div id="sec-variants" class="card" style="padding:20px">
        <div class="dhead">
          <h3 class="dtitle">变体管理</h3>
          <span v-if="variants.length" class="item-cnt" title="按变体现货汇总（低于安全线口径：stock ≤ 安全库存）">库存 {{ varSum.stock }} · 变体 {{ variants.length }} · 低安全线 {{ varSum.low }}</span>
        </div>
        <div v-if="variants.length" style="display:grid;gap:10px;margin-bottom:14px">
          <!-- 卡片式变体行：展示态单行可换行；编辑态两行 grid（规格/SKU/价格/安全库存 + 图片/操作），窄屏不溢出 -->
          <div v-for="(v, i) in variants" :key="v.id || 'copy' + i" class="var-card" style="font-size:13px">
            <template v-if="editing && editing.id === v.id">
              <div class="var-edit-grid">
                <div class="field"><label style="font-size:11px">规格</label><input class="input" :value="specText(v)" disabled style="background:var(--rose-pale)"></div>
                <div class="field"><label style="font-size:11px">SKU</label><input class="input" :value="v.sku" disabled maxlength="64" style="background:var(--rose-pale)"></div>
                <div class="field"><label style="font-size:11px">价格（分）</label><input v-model.number="editing.price" class="input" type="number" min="0" step="1"></div>
                <div class="field"><label style="font-size:11px">安全库存</label><input v-model.number="editing.safety" class="input" type="number" min="0" step="1"></div>
                <div class="field"><label style="font-size:11px">重量（克）</label><input v-model.number="editing.weight" class="input" type="number" min="0" max="100000" step="1" placeholder="空=不修改"></div>
              </div>
              <div class="var-edit-row2">
                <div class="field">
                  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                    <label style="margin:0;flex:1;font-size:11px">变体图片 URL（每行一张，≤6）</label>
                    <button class="btn btn-secondary btn-sm" style="flex:none;height:26px;padding:0 10px;font-size:11px" :disabled="uploading" @click="pickImage('editVar')">{{ uploading ? '上传中…' : '📎 上传' }}</button>
                  </div>
                  <textarea v-model="editing.imgs" class="input" rows="2" style="padding:6px 8px;font-size:12px" placeholder="https://…"></textarea>
                </div>
                <div style="display:flex;gap:8px;align-items:flex-end">
                  <button class="btn btn-primary btn-sm" @click="saveEdit">保存</button>
                  <button class="btn btn-ghost btn-sm" @click="editing = null">取消</button>
                </div>
              </div>
            </template>
            <template v-else>
              <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
                <b>{{ v.option1_value }}</b>
                <span v-if="v.option2_value && v.option2_value !== 'Default'" style="color:var(--gray)">/ {{ v.option2_value }}</span>
                <span v-if="v.sku" style="color:var(--gray);font-size:12px">{{ v.sku }}</span>
                <span v-else class="tag tag-sched" style="font-size:10px" title="SKU 将依新 slug 自动生成">保存后创建</span>
                <span v-if="v.images && v.images.length" class="tag" style="font-size:10px" :title="v.images.join('\n')">🖼×{{ v.images.length }}</span>
                <!-- 重量列：有值显示 g，无值 — -->
                <span style="color:var(--gray);font-size:12px" title="重量（克）">{{ v.weight_gram != null ? v.weight_gram + ' g' : '—' }}</span>
                <b style="margin-left:auto">{{ money(v.price) }}</b>
                <!-- 颜色语义与列表页统一：为 0 红 error、≤安全线黄 warn、充足灰 done -->
                <span class="tag" :class="!v.stock ? 'tag-error' : (v.stock <= (v.safety_stock ?? 0) ? 'tag-pending' : 'tag-done')" :title="`安全库存 ${v.safety_stock ?? 0}`">{{ v.stock }}</span>
                <!-- 复制预览行无 id（未落库），不提供操作；写操作需 catalog:manage -->
                <template v-if="v.id && session.hasPerm('catalog:manage')">
                  <button class="btn btn-ghost btn-sm" @click="startEdit(v)">编辑</button>
                  <button class="btn btn-ghost btn-sm" @click="toggleVar(v)">{{ v.is_active ? '停用' : '启用' }}</button>
                  <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="askDelVar(v)">删除</button>
                </template>
              </div>
            </template>
          </div>
        </div>
        <p v-else style="font-size:13px;color:var(--gray);margin-bottom:12px">暂无变体（新建商品请先保存再添加）</p>
        <!-- 新增变体 6 列 grid：<900px 降 3 列、<600px 降 2 列；写操作需 catalog:manage -->
        <div v-if="pid && session.hasPerm('catalog:manage')" class="var-new-grid">
          <div class="field"><label>规格（如 Short Almond）</label><input v-model="newVar.option1" class="input" maxlength="50"></div>
          <div class="field"><label>副规格</label><input v-model="newVar.option2" class="input" maxlength="50"></div>
          <div class="field"><label>价格（分）</label><input v-model.number="newVar.price" class="input" type="number" min="0" step="1"></div>
          <div class="field"><label>库存（件）</label><input v-model.number="newVar.stock" class="input" type="number" min="0" step="1"></div>
          <div class="field"><label>重量（克）</label><input v-model.number="newVar.weight_gram" class="input" type="number" min="0" step="1" placeholder="30"></div>
          <button class="btn btn-secondary" @click="addVariant">＋ 添加</button>
          <div class="field" style="grid-column:1/-1">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
              <label style="margin:0;flex:1">变体图片 URL（可选，每行一张，≤6）</label>
              <button class="btn btn-secondary btn-sm" style="flex:none" :disabled="uploading" @click="pickImage('newVar')">{{ uploading ? '上传中…' : '📎 上传' }}</button>
            </div>
            <textarea v-model="newVar.imgs" class="input" rows="2" placeholder="https://…"></textarea>
          </div>
        </div>
      </div>
    </div>

    <div style="display:grid;gap:16px">
      <div id="sec-media" class="card" style="padding:20px">
        <div class="dhead"><h3 class="dtitle">媒体</h3></div>
        <div class="field">
          <label>主图 URL</label>
          <div style="display:flex;gap:8px">
            <input v-model="form.hero_image" class="input" style="flex:1;min-width:0" maxlength="500" placeholder="https://…">
            <button class="btn btn-secondary btn-sm" style="flex:none" :disabled="uploading" @click="pickImage('hero')">{{ uploading ? '上传中…' : '📎 上传' }}</button>
          </div>
          <div style="margin-top:10px;border-radius:12px;overflow:hidden;aspect-ratio:1;background:var(--rose-pale);max-width:200px">
            <img v-if="form.hero_image && !brokenHero" :src="form.hero_image" alt="主图预览" style="width:100%;height:100%;object-fit:cover" @error="brokenHero = true">
            <div v-else-if="brokenHero" style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:var(--gray-light);color:var(--gray);font-size:12px">图片加载失败</div>
          </div>
        </div>
        <div class="field">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            <label style="margin:0;flex:1">图集（每行一个 URL，最多 8 张）</label>
            <button class="btn btn-secondary btn-sm" style="flex:none" :disabled="uploading" @click="pickImage('gallery')">{{ uploading ? '上传中…' : '📎 上传' }}</button>
          </div>
          <!-- 草稿原文绑定：超 8 行保留仅警告，保存时才截断；计数超限变红 -->
          <textarea v-model="galText" class="input" rows="4" placeholder="https://…"></textarea>
          <p style="font-size:11.5px" :style="{ color: galLines.length > 8 ? 'var(--error)' : 'var(--gray)' }">{{ galLines.length }}/8</p>
          <div v-if="form.images.length" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:4px">
            <div v-for="(img, i) in form.images" :key="i" style="position:relative;aspect-ratio:1;border-radius:8px;overflow:hidden;background:var(--rose-pale)">
              <img v-if="!brokenImgs[i]" :src="img" :alt="'图 ' + (i + 1)" style="width:100%;height:100%;object-fit:cover" @error="brokenImgs[i] = true">
              <div v-else style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:var(--gray-light);color:var(--gray);font-size:11px">图片加载失败</div>
              <div style="position:absolute;bottom:3px;left:3px;display:flex;gap:3px">
                <button type="button" class="thumb-btn" :disabled="i === 0" title="上移" @click="moveImg(i, -1)">▲</button>
                <button type="button" class="thumb-btn" :disabled="i === form.images.length - 1" title="下移" @click="moveImg(i, 1)">▼</button>
              </div>
              <button type="button" class="thumb-btn" style="position:absolute;top:3px;right:3px;width:auto;height:auto;line-height:1;padding:2px 5px;font-size:11px" :title="'删除第 ' + (i + 1) + ' 张'" @click="removeImg(i)">×</button>
            </div>
          </div>
        </div>
        <div class="field"><label>视频 URL（可选）</label><input v-model="form.video_url" class="input" maxlength="500"></div>
      </div>

      <div v-if="pid" class="card" style="padding:20px">
        <div class="dhead">
          <h3 class="dtitle">定时上架
            <span v-if="prodSched" class="tag tag-sched">已定时</span>
          </h3>
        </div>
        <div class="field">
          <label>上架时间（本地时区）</label>
          <input v-model="schedAt" class="input" type="datetime-local">
        </div>
        <div style="display:flex;gap:8px;margin-top:10px">
          <button class="btn btn-secondary btn-sm" @click="schedQuick(1)">+1 天</button>
          <button class="btn btn-secondary btn-sm" @click="schedQuick(3)">+3 天</button>
          <button class="btn btn-secondary btn-sm" @click="schedQuick(7)">+7 天</button>
          <button class="btn btn-ghost btn-sm" style="margin-left:auto" @click="schedAt = ''">清空</button>
        </div>
        <p style="font-size:11.5px;color:var(--gray);margin-top:8px">保存后生效：设定未来时间后需在列表页点「上架」激活，定时时间将保留，到点自动可见；清空并保存 = 取消定时（立即按当前状态可见）。</p>
      </div>

      <!-- 多语言（仅编辑态；GET 返回裸数组，locale 徽标 + 标题 + 编辑/删除） -->
      <div v-if="pid" id="sec-i18n" class="card" style="padding:20px">
        <div class="dhead">
          <h3 class="dtitle">多语言</h3>
          <button v-if="session.hasPerm('catalog:manage')" class="btn btn-secondary btn-sm" @click="newTr">＋ 添加语言</button>
        </div>
        <p v-if="!translations.length" style="font-size:12.5px;color:var(--gray)">暂无翻译，前台将展示上方主商品信息。</p>
        <div v-for="t in translations" :key="t.locale" style="display:flex;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--gray-light);font-size:13px">
          <span class="tag tag-cat" style="flex:none" :title="LOCALE_LABEL[t.locale] || t.locale">{{ t.locale }}</span>
          <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="t.title">{{ t.title }}</span>
          <button v-if="session.hasPerm('catalog:manage')" class="btn btn-ghost btn-sm" @click="editTr(t)">编辑</button>
          <button v-if="session.hasPerm('catalog:manage')" class="btn btn-ghost btn-sm" style="color:var(--error)" @click="delTr(t)">删除</button>
        </div>
      </div>

      <div class="card" style="padding:20px">
        <div class="dhead"><h3 class="dtitle">组织</h3></div>
        <div class="field"><label>标签（逗号分隔）</label>
          <input :value="form.tags.join(',')" class="input" @input="form.tags = $event.target.value.split(/[,，]/).map((s) => s.trim()).filter(Boolean)">
        </div>
        <label style="display:flex;gap:10px;align-items:center;font-size:13.5px;margin:8px 0;cursor:pointer">
          <input v-model="form.is_new" type="checkbox" style="width:16px;height:16px"> NEW 徽标
        </label>
        <label style="display:flex;gap:10px;align-items:center;font-size:13.5px;cursor:pointer">
          <input v-model="form.is_best_seller" type="checkbox" style="width:16px;height:16px"> 热销徽标
        </label>
      </div>
    </div>
  </div>
  <!-- 加载覆盖层：编辑/复制载入期间提示 -->
  <div v-if="loading" class="load-mask">加载商品数据…</div>
  </fieldset>

  <!-- 吸底保存条：dirty / 保存中才出现（写操作需 catalog:manage） -->
  <div v-if="(dirty || busy) && session.hasPerm('catalog:manage')" class="save-bar">
    <span class="save-dot" aria-hidden="true"></span>
    <span style="flex:1;font-size:13px">有未保存的修改</span>
    <button class="btn btn-primary" :class="{ loading: busy }" :disabled="busy || loading" @click="save">保存</button>
  </div>

  <!-- 多语言添加/编辑弹层（不点遮罩关闭，防误触丢稿，仅右上 × 可关） -->
  <div v-if="trDlg" class="modal open">
    <div class="modal-box" style="max-width:520px">
      <button class="modal-x" @click="trDlg = false">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">🌐 {{ trEditing ? '编辑' : '添加' }}翻译</h3>
      <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">同语言重复保存为覆盖更新；前台无翻译的语言回退主商品信息。</p>
      <div style="display:grid;gap:12px">
        <div class="field"><label>语言</label>
          <select v-model="trForm.locale" class="input" :disabled="trEditing" :style="trEditing ? 'background:var(--rose-pale)' : ''">
            <option v-for="l in LOCALES" :key="l" :value="l">{{ l }} · {{ LOCALE_LABEL[l] }}</option>
          </select>
        </div>
        <div class="field"><label>标题 *</label><input v-model="trForm.title" class="input"></div>
        <div class="field"><label>副标题（可选）</label><input v-model="trForm.subtitle" class="input"></div>
        <div class="field"><label>描述 Markdown（可选）</label><textarea v-model="trForm.description_md" class="input" rows="5"></textarea></div>
      </div>
      <button v-if="session.hasPerm('catalog:manage')" class="btn btn-primary btn-block" style="margin-top:14px" @click="saveTr">保存</button>
    </div>
  </div>

  <!-- 图片上传共用隐藏 input（主图/图集/变体三入口，见 pickImage） -->
  <input ref="fileInput" type="file" accept=".png,.jpg,.jpeg,.webp,.gif" style="display:none" @change="onPickFile">

  <!-- 离开确认（SPA 内未保存拦截） -->
  <ConfirmDialog :open="leaveDlg" title="未保存的修改" body="有未保存的修改，确认离开？" danger confirm-text="离开" @confirm="confirmLeave" @close="cancelLeave" />
  <!-- 删除翻译确认 -->
  <ConfirmDialog :open="delDlgOpen" title="删除翻译" :body="delDlgBody" danger confirm-text="删除" @confirm="doDelTr" @close="delDlgOpen = false" />
  <!-- 删除变体确认（409 variant in use 不可删） -->
  <ConfirmDialog :open="delVarDlg" title="删除变体" :body="delVarBody" danger confirm-text="删除" :busy="delVarBusy" @confirm="doDelVar" @close="delVarDlg = false" />
</template>

<style scoped>
.achips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.achips button{padding:5px 12px;font-size:12.5px;border:1px solid var(--gray-light);background:#fff;border-radius:999px;color:var(--gray);cursor:pointer}
.achips button:hover{color:var(--plum);border-color:var(--plum)}
.phint{font-size:11.5px;color:var(--gray);margin-top:3px}
/* 描述 Markdown 编辑/预览切换（样式同 ContentView） */
.md-tabs{display:flex;gap:6px;margin-bottom:8px}
.md-tabs button{border:1px solid var(--gray-light);background:#fff;color:var(--gray);font-size:12px;font-weight:600;border-radius:999px;padding:3px 12px;cursor:pointer}
.md-tabs button.on{background:var(--plum);border-color:var(--plum);color:#fff}
.md-prev{max-height:300px;overflow-y:auto;border:1px solid var(--gray-light);border-radius:10px;padding:12px 14px;background:#fff;font-size:14px}
.md-prev h1{font-family:var(--font-title);font-size:20px;margin:14px 0 8px}
.md-prev h3{font-family:var(--font-title);font-size:16px;margin:12px 0 6px}
.md-prev blockquote{margin:8px 0;padding:6px 12px;border-left:3px solid var(--plum);background:var(--rose-pale);border-radius:0 8px 8px 0;color:#3A3438}
.md-prev code{background:var(--gray-light);border-radius:5px;padding:1px 6px;font-size:12.5px}
.md-prev a{color:var(--plum);font-weight:600}
/* 表单外壳：fieldset 包裹 + 加载覆盖层（loading 期间整体禁用） */
.form-shell{border:none;padding:0;margin:0;position:relative;min-width:0}
.load-mask{position:absolute;inset:0;z-index:6;background:rgba(255,255,255,.72);display:flex;align-items:flex-start;justify-content:center;gap:10px;padding-top:110px;font-size:13.5px;color:var(--gray);border-radius:12px}
.load-mask::before{content:"";width:15px;height:15px;flex:none;margin-top:-1px;border:2px solid var(--gray-light);border-top-color:var(--plum);border-radius:50%;animation:gmSpin 1s linear infinite}
@keyframes gmSpin{to{transform:rotate(360deg)}}
/* 变体卡片行：编辑态两行 grid（规格/SKU/价格/安全库存/重量 + 图片/操作） */
.var-card{border:1px solid var(--gray-light);border-radius:10px;padding:10px 12px}
.var-card .field{margin-bottom:0}
.var-edit-grid{display:grid;grid-template-columns:1.2fr 1.6fr .8fr .8fr .7fr;gap:10px}
.var-edit-row2{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:end;margin-top:10px}
/* 新增变体表单：6 列 → <900px 3 列 → <600px 2 列 */
.var-new-grid{display:grid;grid-template-columns:1.2fr 1fr .6fr .5fr .5fr auto;gap:8px;align-items:end}
.var-new-grid .field{margin-bottom:0}
@media(max-width:900px){
  .var-edit-grid{grid-template-columns:1fr 1fr}
  .var-edit-row2{grid-template-columns:1fr}
  .var-new-grid{grid-template-columns:1fr 1fr 1fr}
}
@media(max-width:600px){
  .var-new-grid{grid-template-columns:1fr 1fr}
}
/* 图集缩略图小按钮（上移/下移/删除） */
.thumb-btn{width:18px;height:18px;border:none;border-radius:50%;background:rgba(0,0,0,.55);color:#fff;font-size:9px;line-height:18px;padding:0;cursor:pointer}
.thumb-btn:hover:not(:disabled){background:rgba(0,0,0,.8)}
.thumb-btn:disabled{opacity:.35;cursor:default}
/* 吸底保存条：dirty/保存中出现，红点呼吸提示未保存 */
.save-bar{position:sticky;bottom:12px;z-index:30;display:flex;align-items:center;gap:10px;margin-top:14px;padding:10px 16px;background:#fff;border:1px solid var(--gray-light);border-radius:12px;box-shadow:0 6px 22px rgba(31,27,30,.16)}
.save-dot{width:9px;height:9px;border-radius:50%;background:var(--error);animation:savePulse 1.6s infinite;flex:none}
@keyframes savePulse{50%{opacity:.35}}
</style>
