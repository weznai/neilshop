<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { toast } from '../composables/toast'

const route = useRoute()
const router = useRouter()
/* 响应式 pid：新建保存成功后 router.replace 挂 id，此处随之变为编辑态
 * （此前一次性快照导致重复保存会重复建品、变体区不出现） */
const pid = computed(() => (route.query.id ? parseInt(route.query.id, 10) : null))

const form = reactive({
  slug: '', title: '', subtitle: '', price_min: 1599, price_max: 1599,
  compare_at_price: null, description_md: '', hero_image: '', images: [],
  video_url: '', category_id: 1, tags: [], is_new: false, is_best_seller: false,
})
const variants = ref([])
const cats = ref([])
const catsFailed = ref(false)
const busy = ref(false)
const newVar = reactive({ option1: '', option2: 'Default', price: 1599, stock: 10 })
const schedAt = ref('')
const loadedSchedISO = ref(null)
const prodSched = ref(false)
const editing = ref(null)

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
    loadTranslations(id)
  } catch (e) { toast('商品加载失败：' + (e.message || ''), 'error') }
}

onMounted(async () => {
  try {
    cats.value = await req('GET', '/api/admin/catalog/categories')
    if (!pid.value && cats.value.length && !cats.value.some((c) => c.id === form.category_id)) form.category_id = cats.value[0].id
  } catch (_) { catsFailed.value = true; toast('分类加载失败，保存前请刷新重试', 'error') }
  if (pid.value) loadProduct(pid.value)
})
/* 新建→编辑切换（同路由 query 变化）时重新拉取 */
watch(pid, (np, op) => { if (np && np !== op) loadProduct(np) })

async function save() {
  if (!form.slug || !form.title) { toast('slug 与标题必填', 'error'); return }
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
    } else {
      const p = await req('POST', '/api/admin/catalog/products', body)
      toast('创建成功 ✓ 转编辑态', 'success')
      router.replace({ path: '/product-edit', query: { id: p.id } })
    }
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
  finally { busy.value = false }
}

async function addVariant() {
  if (!newVar.option1 || !newVar.option2) { toast('变体规格必填（如 Short Almond / Default）', 'error'); return }
  if (!Number.isInteger(newVar.price) || newVar.price < 0) { toast('价格需为非负整数（单位：分）', 'error'); return }
  if (!Number.isInteger(newVar.stock) || newVar.stock < 0) { toast('库存需为非负整数（单位：件）', 'error'); return }
  const sku = (form.slug + '-' + newVar.option1).toUpperCase().replace(/\s+/g, '-').slice(0, 64)
  try {
    await req('POST', `/api/admin/catalog/products/${pid.value}/variants`, {
      sku, option1_value: newVar.option1, option2_value: newVar.option2,
      price: newVar.price, stock: newVar.stock,
    })
    newVar.option1 = ''
    variants.value = await loadVariants(pid.value)
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
async function delTr(t) {
  if (!confirm(`删除${LOCALE_LABEL[t.locale] || t.locale}（${t.locale}）翻译？前台该语言将回退默认内容。`)) return
  try {
    await req('DELETE', `/api/admin/catalog/products/${pid.value}/translations/${t.locale}`)
    toast('已删除', 'success')
    loadTranslations(pid.value)
  } catch (e) { toast('删除失败：' + (e.data?.detail || e.message), 'error') }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">{{ pid ? '编辑商品 #' + pid : '新建商品' }}</h1>
      <span style="font-size:12.5px;color:var(--gray)">保存即生效 · 上架/下架在列表页操作</span>
    </div>
    <div style="display:flex;gap:10px">
      <a v-if="pid" class="btn btn-secondary" :href="'/product?id=' + pid" target="_blank" rel="noopener">前台预览 ↗</a>
      <router-link to="/products" class="btn btn-ghost">← 列表</router-link>
      <button class="btn btn-primary" :class="{ loading: busy }" :disabled="busy" @click="save">保存</button>
    </div>
  </div>

  <div class="grid-2" style="align-items:start">
    <div style="display:grid;gap:16px">
      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">基本信息</h3>
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

      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">定价（分）</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
          <div class="field"><label>最低价</label><input v-model.number="form.price_min" class="input" type="number"></div>
          <div class="field"><label>最高价</label><input v-model.number="form.price_max" class="input" type="number"></div>
          <div class="field"><label>划线价</label><input v-model.number="form.compare_at_price" class="input" type="number"></div>
        </div>
        <p style="font-size:12px;color:var(--gray)">当前展示：{{ money(form.price_min) }}<span v-if="form.compare_at_price">（划线 {{ money(form.compare_at_price) }}）</span></p>
      </div>

      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">变体管理</h3>
        <div v-if="variants.length" style="display:grid;gap:8px;margin-bottom:14px">
          <div v-for="v in variants" :key="v.id" style="display:flex;gap:12px;align-items:center;font-size:13px;padding:8px 0;border-bottom:1px solid var(--gray-light)">
            <b>{{ v.option1_value }}</b>
            <span style="color:var(--gray);font-size:12px">{{ v.sku }}</span>
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
              <button class="btn btn-ghost btn-sm" @click="startEdit(v)">编辑</button>
              <button class="btn btn-ghost btn-sm" @click="toggleVar(v)">{{ v.is_active ? '停用' : '启用' }}</button>
            </template>
          </div>
        </div>
        <p v-else style="font-size:13px;color:var(--gray);margin-bottom:12px">暂无变体（新建商品请先保存再添加）</p>
        <div v-if="pid" style="display:grid;grid-template-columns:1.2fr 1fr .7fr .6fr auto;gap:8px;align-items:end">
          <div class="field"><label>规格（如 Short Almond）</label><input v-model="newVar.option1" class="input"></div>
          <div class="field"><label>副规格</label><input v-model="newVar.option2" class="input"></div>
          <div class="field"><label>价格（分）</label><input v-model.number="newVar.price" class="input" type="number" min="0" step="1"></div>
          <div class="field"><label>库存（件）</label><input v-model.number="newVar.stock" class="input" type="number" min="0" step="1"></div>
          <button class="btn btn-secondary" @click="addVariant">＋ 添加</button>
        </div>
      </div>
    </div>

    <div style="display:grid;gap:16px">
      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">媒体</h3>
        <div class="field">
          <label>主图 URL</label>
          <input v-model="form.hero_image" class="input" placeholder="https://…">
          <div style="margin-top:10px;border-radius:12px;overflow:hidden;aspect-ratio:1;background:var(--rose-pale);max-width:200px">
            <img v-if="form.hero_image" :src="form.hero_image" alt="主图预览" style="width:100%;height:100%;object-fit:cover">
          </div>
        </div>
        <div class="field">
          <label>图集（每行一个 URL，最多 8 张）</label>
          <textarea :value="form.images.join('\n')" class="input" rows="4"
                    @input="form.images = $event.target.value.split(/\n+/).map(s => s.trim()).filter(Boolean).slice(0, 8)"></textarea>
          <p style="font-size:11.5px;color:var(--gray)">{{ form.images.length }}/8</p>
          <div v-if="form.images.length" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:4px">
            <div v-for="(img, i) in form.images" :key="i" style="position:relative;aspect-ratio:1;border-radius:8px;overflow:hidden;background:var(--rose-pale)">
              <img :src="img" :alt="'图 ' + (i + 1)" style="width:100%;height:100%;object-fit:cover">
              <button style="position:absolute;top:3px;right:3px;width:18px;height:18px;border:none;border-radius:50%;background:rgba(0,0,0,.55);color:#fff;font-size:11px;line-height:18px;padding:0;cursor:pointer" :title="'删除第 ' + (i + 1) + ' 张'" @click="form.images.splice(i, 1)">×</button>
            </div>
          </div>
        </div>
        <div class="field"><label>视频 URL（可选）</label><input v-model="form.video_url" class="input"></div>
      </div>

      <div v-if="pid" class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">定时上架
          <span v-if="prodSched" class="tag tag-sched" style="margin-left:6px">已定时</span>
        </h3>
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
        <p style="font-size:11.5px;color:var(--gray);margin-top:8px">保存后生效：到点前台自动可见；清空并保存 = 取消定时（立即按当前状态可见）。需先在列表页「上架」。</p>
      </div>

      <!-- 多语言（仅编辑态；GET 返回裸数组，locale 徽标 + 标题 + 编辑/删除） -->
      <div v-if="pid" class="card" style="padding:20px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <h3 style="font-size:15px">多语言</h3>
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
        <h3 style="font-size:15px;margin-bottom:12px">组织</h3>
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

  <!-- 多语言添加/编辑弹层 -->
  <div v-if="trDlg" class="modal open" @click.self="trDlg = false">
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
</template>
