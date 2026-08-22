<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const route = useRoute()
const router = useRouter()
/* 响应式 pid：新建保存成功后 router.replace 挂 id，此处随之变为编辑态
 * （此前一次性快照导致重复保存会重复建品、变体区不出现） */
const pid = computed(() => (route.query.id ? parseInt(route.query.id, 10) : null))
/* 复制模式：?copy={id} 载入源商品作底稿，但保持新建态（不设 id、slug 置空、定时清空） */
const copyId = computed(() => (route.query.copy ? parseInt(route.query.copy, 10) : null))

const form = reactive({
  slug: '', title: '', subtitle: '', price_min: 1599, price_max: 1599,
  compare_at_price: null, description_md: '', hero_image: '', images: [],
  video_url: '', category_id: 1, tags: [], is_new: false, is_best_seller: false,
})
const variants = ref([])
const cats = ref([])
const catsFailed = ref(false)
const busy = ref(false)
const newVar = reactive({ option1: '', option2: 'Default', price: 1599, stock: 10, weight_gram: 30 })
const schedAt = ref('')
const loadedSchedISO = ref(null)
const prodSched = ref(false)
const editing = ref(null)

/* ===== 未保存变更跟踪：表单+定时一份基线；变体为即时保存，单独重置基线 ===== */
const dirty = ref(false)
const formLoaded = ref(false)
const formSnap = ref('')
const varSnap = ref('')
const snapForm = () => JSON.stringify([form, schedAt.value])
const snapVars = () => JSON.stringify(variants.value)
function markClean() { formSnap.value = snapForm(); varSnap.value = snapVars(); dirty.value = false }
function markVarsClean() { varSnap.value = snapVars(); checkDirty() }
function checkDirty() {
  if (!formLoaded.value) return /* 加载期间触发的 watch 一律跳过，防首载误判 dirty */
  dirty.value = snapForm() !== formSnap.value || snapVars() !== varSnap.value
}
watch([form, schedAt], checkDirty, { deep: true })
watch(variants, checkDirty, { deep: true })

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
  return all
}

async function loadProduct(id) {
  formLoaded.value = false /* 重载期间暂停 dirty 判定，防切换编辑时误报未保存 */
  try {
    const p = await req('GET', '/api/admin/catalog/products/' + id)
    Object.assign(form, {
      slug: p.slug, title: p.title, subtitle: p.subtitle || '',
      price_min: p.price_min, price_max: p.price_max, compare_at_price: p.compare_at_price,
      description_md: p.description_md || '', hero_image: p.hero_image || '',
      images: (p.images || []).slice(0, 8), video_url: p.video_url || '',
      category_id: p.category_id, tags: p.tags || [],
      is_new: !!p.is_new, is_best_seller: !!p.is_best_seller,
    })
    prodSched.value = !!p.scheduled
    loadedSchedISO.value = p.scheduled ? new Date(asUTC(p.published_at)).toISOString() : null
    schedAt.value = loadedSchedISO.value ? fmtLocal(new Date(asUTC(p.published_at))) : ''
    variants.value = await loadVariants(id)
    formLoaded.value = true
    markClean()
    loadTranslations(id)
  } catch (e) { toast('商品加载失败：' + (e.message || ''), 'error') }
}

onMounted(async () => {
  window.addEventListener('beforeunload', onUnload)
  try {
    cats.value = await req('GET', '/api/admin/catalog/categories')
    if (!pid.value && cats.value.length && !cats.value.some((c) => c.id === form.category_id)) form.category_id = cats.value[0].id
  } catch (_) { catsFailed.value = true; toast('分类加载失败，保存前请刷新重试', 'error') }
  if (pid.value) loadProduct(pid.value)
  else if (copyId.value) loadCopy(copyId.value)
  else { formLoaded.value = true; markClean() }
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', onUnload))
/* 新建→编辑切换（同路由 query 变化）时重新拉取 */
watch(pid, (np, op) => { if (np && np !== op) loadProduct(np) })

/* 复制模式载入：变体/翻译剥 id 暂存，待新商品保存成功后逐个重建（sku 依新 slug 生成） */
const copyVars = ref([])
const copyTrs = ref([])
async function loadCopy(id) {
  formLoaded.value = false
  try {
    const p = await req('GET', '/api/admin/catalog/products/' + id)
    Object.assign(form, {
      slug: '', title: p.title, subtitle: p.subtitle || '',
      price_min: p.price_min, price_max: p.price_max, compare_at_price: p.compare_at_price,
      description_md: p.description_md || '', hero_image: p.hero_image || '',
      images: (p.images || []).slice(0, 8), video_url: p.video_url || '',
      category_id: p.category_id, tags: p.tags || [],
      is_new: !!p.is_new, is_best_seller: !!p.is_best_seller,
    })
    if (cats.value.length && !cats.value.some((c) => c.id === p.category_id)) form.category_id = cats.value[0].id
    /* 定时/状态置草稿：schedAt 清空即不随 POST 提交 published_at */
    prodSched.value = false
    loadedSchedISO.value = null
    schedAt.value = ''
    const src = await loadVariants(id)
    copyVars.value = src.map((v) => ({
      option1_value: v.option1_value, option2_value: v.option2_value || 'Default', price: v.price, stock: v.stock,
    }))
    variants.value = src.map((v) => ({ ...v, id: null, sku: '', is_active: true })) /* 仅作预览，操作按钮已按 id 隐藏 */
    try { copyTrs.value = ((await req('GET', `/api/admin/catalog/products/${id}/translations`)) || []).map((t) => ({ locale: t.locale, title: t.title, subtitle: t.subtitle || null, description_md: t.description_md || null })) }
    catch (_) { copyTrs.value = [] }
    formLoaded.value = true
    markClean()
  } catch (e) { toast('源商品加载失败：' + (e.message || ''), 'error') }
}

async function save() {
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
  busy.value = true
  const body = { ...form, images: form.images.slice(0, 8) }
  if (pid.value) delete body.slug
  if (!body.compare_at_price) body.compare_at_price = null
  const iso = schedAt.value ? new Date(schedAt.value).toISOString() : null
  if (iso !== loadedSchedISO.value) body.published_at = iso
  try {
    if (pid.value) {
      await req('PUT', '/api/admin/catalog/products/' + pid.value, body)
      if (body.published_at !== undefined) {
        loadedSchedISO.value = body.published_at
        prodSched.value = body.published_at ? new Date(body.published_at) > new Date() : false
      }
      toast('保存成功 ✓', 'success')
      markClean()
    } else {
      const p = await req('POST', '/api/admin/catalog/products', body)
      /* 复制模式：新商品落库后重建变体与翻译（逐个调用；失败项汇总提示手动补录） */
      if (copyVars.value.length || copyTrs.value.length) {
        const newSlug = p.slug || form.slug
        let vok = 0, vfail = 0, tok = 0, tfail = 0
        for (const v of copyVars.value) {
          const sku = (newSlug + '-' + v.option1_value).toUpperCase().replace(/\s+/g, '-').slice(0, 64)
          try { await req('POST', `/api/admin/catalog/products/${p.id}/variants`, { sku, option1_value: v.option1_value, option2_value: v.option2_value, price: v.price, stock: v.stock }); vok++ }
          catch (_) { vfail++ }
        }
        for (const t of copyTrs.value) {
          try { await req('PUT', `/api/admin/catalog/products/${p.id}/translations`, { ...t }); tok++ }
          catch (_) { tfail++ }
        }
        const fails = vfail + tfail
        if (fails) toast(`副本重建：变体 ${vok}/${copyVars.value.length}、翻译 ${tok}/${copyTrs.value.length}，${fails} 项失败请手动补录`, 'error')
        copyVars.value = []
        copyTrs.value = []
      }
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
  const sku = (form.slug + '-' + newVar.option1).toUpperCase().replace(/\s+/g, '-').slice(0, 64)
  try {
    /* weight_gram 仅创建时支持（VariantUpdateIn 无此字段） */
    await req('POST', `/api/admin/catalog/products/${pid.value}/variants`, {
      sku, option1_value: newVar.option1, option2_value: newVar.option2,
      price: newVar.price, stock: newVar.stock, weight_gram: newVar.weight_gram,
    })
    newVar.option1 = ''
    variants.value = await loadVariants(pid.value)
    markVarsClean()
    toast('变体已添加 ✓', 'success')
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
    toast(v.is_active ? '已启用' : '已停用', 'success')
  } catch (e) { toast('操作失败', 'error') }
}
function startEdit(v) { editing.value = { id: v.id, price: v.price, safety: v.safety_stock ?? 0 } }
async function saveEdit() {
  const ed = editing.value
  if (!ed) return
  if (!Number.isFinite(ed.price) || !Number.isFinite(ed.safety) || ed.price < 0 || ed.safety < 0) { toast('价格与安全库存需为非负数字', 'error'); return }
  try {
    await req('PUT', '/api/admin/catalog/variants/' + ed.id, { price: ed.price, safety_stock: ed.safety })
    const v = variants.value.find((x) => x.id === ed.id)
    if (v) { v.price = ed.price; v.safety_stock = ed.safety }
    editing.value = null
    markVarsClean()
    toast('变体已更新 ✓', 'success')
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}
const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

/* ===== 多语言翻译（GET/PUT /products/{id}/translations、DELETE /{locale}；GET 返回裸数组）
 * 契约：locale 须匹配 ^[a-z]{2}-[A-Z]{2}$，title 必填，subtitle/description_md 可选 ===== */
const LOCALES = ['zh-CN', 'en-US', 'fr-FR', 'de-DE', 'ja-JP']
const LOCALE_LABEL = { 'zh-CN': '简体中文', 'en-US': 'English', 'fr-FR': 'Français', 'de-DE': 'Deutsch', 'ja-JP': '日本語' }
const translations = ref([])
const trDlg = ref(false)
const trEditing = ref(false)   /* true=编辑已有语言（locale 锁定） */
const trForm = reactive({ locale: 'zh-CN', title: '', subtitle: '', description_md: '' })
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
      <span class="page-sub">保存即生效 · 上架/下架在列表页操作</span>
    </div>
    <div style="display:flex;gap:10px">
      <a v-if="pid" class="btn btn-secondary" :href="'/product?id=' + pid" target="_blank" rel="noopener">前台预览 ↗</a>
      <router-link to="/products" class="btn btn-ghost">← 列表</router-link>
      <button class="btn btn-primary" :class="{ loading: busy }" :disabled="busy" @click="save">保存</button>
    </div>
  </div>

  <div v-if="copyId && !pid" style="padding:10px 16px;margin-bottom:14px;background:var(--rose-pale);border:1px solid var(--rose);border-radius:10px;font-size:13px;color:var(--plum)">
    ⧉ 已从商品 #{{ copyId }} 复制，保存后生效为新商品——请填写新 Slug；{{ copyVars.length }} 个变体与 {{ copyTrs.length }} 条翻译将在保存后自动重建
  </div>

  <div class="achips">
    <button v-for="s in SECTIONS" :key="s.id" @click="jump(s.id)">{{ s.label }}</button>
  </div>

  <div class="grid-2" style="align-items:start">
    <div style="display:grid;gap:16px">
      <div id="sec-base" class="card" style="padding:20px">
        <div class="dhead"><h3 class="dtitle">基本信息</h3></div>
        <div class="field"><label>标题</label><input v-model="form.title" class="input"></div>
        <div v-if="!pid" class="field"><label>Slug</label><input v-model="form.slug" class="input" placeholder="nova-set"></div>
        <div v-else class="field"><label>Slug（不可改）</label><input :value="form.slug" class="input" disabled style="background:var(--rose-pale)"></div>
        <div class="field"><label>副标题</label><input v-model="form.subtitle" class="input"></div>
        <div class="field">
          <label>分类</label>
          <select v-model="form.category_id" class="input" :disabled="!cats.length">
            <option v-for="c in cats" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
          <p v-if="!cats.length" style="font-size:11.5px;color:var(--error);margin-top:4px">分类{{ catsFailed ? '加载失败' : '为空' }}，保存会报「category not found」，请刷新重试</p>
        </div>
        <div class="field"><label>描述（Markdown）</label><textarea v-model="form.description_md" class="input" rows="6"></textarea></div>
      </div>

      <div id="sec-pricing" class="card" style="padding:20px">
        <div class="dhead"><h3 class="dtitle">定价（分）</h3></div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
          <div class="field"><label>最低价</label><input v-model.number="form.price_min" class="input" type="number" min="0" step="1"><p class="phint">≈ {{ money(form.price_min) }}</p></div>
          <div class="field"><label>最高价</label><input v-model.number="form.price_max" class="input" type="number" min="0" step="1"><p class="phint">≈ {{ money(form.price_max) }}</p></div>
          <div class="field"><label>划线价</label><input v-model.number="form.compare_at_price" class="input" type="number" min="0" step="1"><p v-if="form.compare_at_price" class="phint">≈ {{ money(form.compare_at_price) }}</p></div>
        </div>
        <p style="font-size:12px;color:var(--gray)">当前展示：{{ money(form.price_min) }}<span v-if="form.compare_at_price">（划线 {{ money(form.compare_at_price) }}）</span></p>
      </div>

      <div id="sec-variants" class="card" style="padding:20px">
        <div class="dhead"><h3 class="dtitle">变体管理</h3></div>
        <div v-if="variants.length" style="display:grid;gap:8px;margin-bottom:14px">
          <div v-for="(v, i) in variants" :key="v.id || 'copy' + i" style="display:flex;gap:12px;align-items:center;font-size:13px;padding:8px 0;border-bottom:1px solid var(--gray-light)">
            <b>{{ v.option1_value }}</b>
            <span v-if="v.sku" style="color:var(--gray);font-size:12px">{{ v.sku }}</span>
            <span v-else class="tag tag-sched" style="font-size:10px" title="SKU 将依新 slug 自动生成">保存后创建</span>
            <template v-if="editing && editing.id === v.id">
              <div class="field" style="margin:0 0 0 auto">
                <label style="font-size:11px">价格（分）</label>
                <input v-model.number="editing.price" class="input" type="number" style="width:110px;padding:6px 8px">
              </div>
              <div class="field" style="margin:0">
                <label style="font-size:11px">安全库存</label>
                <input v-model.number="editing.safety" class="input" type="number" style="width:90px;padding:6px 8px">
              </div>
              <button class="btn btn-primary btn-sm" @click="saveEdit">保存</button>
              <button class="btn btn-ghost btn-sm" @click="editing = null">取消</button>
            </template>
            <template v-else>
              <b style="margin-left:auto">{{ money(v.price) }}</b>
              <span class="tag" :class="v.stock > v.safety_stock ? 'tag-done' : 'tag-error'" :title="`安全库存 ${v.safety_stock ?? 0}`">{{ v.stock }}</span>
              <!-- 复制预览行无 id（未落库），不提供操作 -->
              <template v-if="v.id">
                <button class="btn btn-ghost btn-sm" @click="startEdit(v)">编辑</button>
                <button class="btn btn-ghost btn-sm" @click="toggleVar(v)">{{ v.is_active ? '停用' : '启用' }}</button>
              </template>
            </template>
          </div>
        </div>
        <p v-else style="font-size:13px;color:var(--gray);margin-bottom:12px">暂无变体（新建商品请先保存再添加）</p>
        <div v-if="pid" style="display:grid;grid-template-columns:1.2fr 1fr .6fr .5fr .5fr auto;gap:8px;align-items:end">
          <div class="field"><label>规格（如 Short Almond）</label><input v-model="newVar.option1" class="input"></div>
          <div class="field"><label>副规格</label><input v-model="newVar.option2" class="input"></div>
          <div class="field"><label>价格（分）</label><input v-model.number="newVar.price" class="input" type="number" min="0" step="1"></div>
          <div class="field"><label>库存（件）</label><input v-model.number="newVar.stock" class="input" type="number" min="0" step="1"></div>
          <div class="field"><label>重量（克）</label><input v-model.number="newVar.weight_gram" class="input" type="number" min="0" step="1" placeholder="30"></div>
          <button class="btn btn-secondary" @click="addVariant">＋ 添加</button>
        </div>
      </div>
    </div>

    <div style="display:grid;gap:16px">
      <div id="sec-media" class="card" style="padding:20px">
        <div class="dhead"><h3 class="dtitle">媒体</h3></div>
        <div class="field">
          <label>主图 URL</label>
          <input v-model="form.hero_image" class="input" placeholder="https://…">
          <div style="margin-top:10px;border-radius:12px;overflow:hidden;aspect-ratio:1;background:var(--rose-pale);max-width:200px">
            <img v-if="form.hero_image && !brokenHero" :src="form.hero_image" alt="主图预览" style="width:100%;height:100%;object-fit:cover" @error="brokenHero = true">
            <div v-else-if="brokenHero" style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:var(--gray-light);color:var(--gray);font-size:12px">图片加载失败</div>
          </div>
        </div>
        <div class="field">
          <label>图集（每行一个 URL，最多 8 张）</label>
          <textarea :value="form.images.join('\n')" class="input" rows="4"
                    @input="form.images = $event.target.value.split(/\n+/).map(s => s.trim()).filter(Boolean).slice(0, 8)"></textarea>
          <p style="font-size:11.5px;color:var(--gray)">{{ form.images.length }}/8</p>
          <div v-if="form.images.length" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:4px">
            <div v-for="(img, i) in form.images" :key="i" style="position:relative;aspect-ratio:1;border-radius:8px;overflow:hidden;background:var(--rose-pale)">
              <img v-if="!brokenImgs[i]" :src="img" :alt="'图 ' + (i + 1)" style="width:100%;height:100%;object-fit:cover" @error="brokenImgs[i] = true">
              <div v-else style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:var(--gray-light);color:var(--gray);font-size:11px">图片加载失败</div>
              <button style="position:absolute;top:3px;right:3px;width:18px;height:18px;border:none;border-radius:50%;background:rgba(0,0,0,.55);color:#fff;font-size:11px;line-height:18px;padding:0;cursor:pointer" :title="'删除第 ' + (i + 1) + ' 张'" @click="form.images.splice(i, 1)">×</button>
            </div>
          </div>
        </div>
        <div class="field"><label>视频 URL（可选）</label><input v-model="form.video_url" class="input"></div>
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
          <button class="btn btn-secondary btn-sm" @click="newTr">＋ 添加语言</button>
        </div>
        <p v-if="!translations.length" style="font-size:12.5px;color:var(--gray)">暂无翻译，前台将展示上方主商品信息。</p>
        <div v-for="t in translations" :key="t.locale" style="display:flex;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--gray-light);font-size:13px">
          <span class="tag tag-cat" style="flex:none" :title="LOCALE_LABEL[t.locale] || t.locale">{{ t.locale }}</span>
          <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="t.title">{{ t.title }}</span>
          <button class="btn btn-ghost btn-sm" @click="editTr(t)">编辑</button>
          <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="delTr(t)">删除</button>
        </div>
      </div>

      <div class="card" style="padding:20px">
        <div class="dhead"><h3 class="dtitle">组织</h3></div>
        <div class="field"><label>标签（逗号分隔）</label>
          <input :value="form.tags.join(',')" class="input" @input="form.tags = $event.target.value.split(',').map((s) => s.trim()).filter(Boolean)">
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

  <div style="display:flex;justify-content:center;margin-top:8px">
    <button class="btn btn-primary" :class="{ loading: busy }" :disabled="busy" @click="save">保存</button>
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
      <button class="btn btn-primary btn-block" style="margin-top:14px" @click="saveTr">保存</button>
    </div>
  </div>

  <!-- 离开确认（SPA 内未保存拦截） -->
  <ConfirmDialog :open="leaveDlg" title="未保存的修改" body="有未保存的修改，确认离开？" danger confirm-text="离开" @confirm="confirmLeave" @close="cancelLeave" />
  <!-- 删除翻译确认 -->
  <ConfirmDialog :open="delDlgOpen" title="删除翻译" :body="delDlgBody" danger confirm-text="删除" @confirm="doDelTr" @close="delDlgOpen = false" />
</template>

<style scoped>
.achips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.achips button{padding:5px 12px;font-size:12.5px;border:1px solid var(--gray-light);background:#fff;border-radius:999px;color:var(--gray);cursor:pointer}
.achips button:hover{color:var(--plum);border-color:var(--plum)}
.phint{font-size:11.5px;color:var(--gray);margin-top:3px}
</style>
