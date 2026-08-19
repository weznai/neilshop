<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'

const route = useRoute()
const router = useRouter()
const pid = route.query.id ? parseInt(route.query.id, 10) : null

const form = reactive({
  slug: '', title: '', subtitle: '', price_min: 1599, price_max: 1599,
  compare_at_price: null, description_md: '', hero_image: '', images: [],
  category_id: 1, tags: [], is_new: false, is_best_seller: false,
})
const variants = ref([])
const cats = ref([])
const busy = ref(false)
const newVar = reactive({ option1: '', price: 1599, stock: 10, safety: 5 })

onMounted(async () => {
  try { cats.value = await req('GET', '/api/admin/catalog/categories') } catch (_) { /* */ }
  if (pid) {
    const p = await req('GET', '/api/admin/catalog/products/' + pid)
    Object.assign(form, {
      slug: p.slug, title: p.title, subtitle: p.subtitle || '', price_min: p.price_min,
      price_max: p.price_max, compare_at_price: p.compare_at_price,
      description_md: p.description_md || '', hero_image: p.hero_image || '',
      images: (p.images || []).slice(0, 20), category_id: p.category_id,
      tags: p.tags || [], is_new: !!p.is_new, is_best_seller: !!p.is_best_seller,
    })
    try {
      const v = await req('GET', '/api/admin/catalog/variants?product_id=' + pid)
      variants.value = v.items || []
    } catch (_) { variants.value = [] }
  }
})

async function save() {
  if (!form.slug || !form.title) { window.$gmToast('slug 与标题必填', 'error'); return }
  busy.value = true
  const body = { ...form, price_max: Math.max(form.price_max, form.price_min) }
  try {
    if (pid) {
      await req('PUT', '/api/admin/catalog/products/' + pid, body)
      window.$gmToast('保存成功 ✓', 'success')
    } else {
      const p = await req('POST', '/api/admin/catalog/products', body)
      window.$gmToast('创建成功 ✓ 转编辑态', 'success')
      router.replace({ path: '/product-edit', query: { id: p.id } })
    }
  } catch (e) { window.$gmToast('保存失败：' + (e.message || ''), 'error') }
  finally { busy.value = false }
}

async function addVariant() {
  if (!newVar.option1) { window.$gmToast('变体名必填（如 Short Almond）', 'error'); return }
  try {
    await req('POST', `/api/admin/catalog/products/${pid}/variants`, {
      option1_value: newVar.option1, price: newVar.price, stock: newVar.stock, safety_stock: newVar.safety,
      sku: (form.slug + '-' + newVar.option1).toUpperCase().slice(0, 24).replace(/\s+/g, '-'),
    })
    newVar.option1 = ''
    variants.value = (await req('GET', '/api/admin/catalog/variants?product_id=' + pid)).items || []
    window.$gmToast('变体已添加 ✓', 'success')
  } catch (e) { window.$gmToast('添加失败：' + (e.message || ''), 'error') }
}
async function toggleVar(v) {
  await req('PUT', '/api/admin/catalog/variants/' + v.id, { is_active: v.is_active ? 0 : 1 })
  v.is_active = v.is_active ? 0 : 1
}
const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">{{ pid ? '编辑商品 #' + pid : '新建商品' }}</h1>
      <span style="font-size:12.5px;color:var(--gray)">两栏编辑 · 保存即生效</span>
    </div>
    <div style="display:flex;gap:10px">
      <router-link v-if="pid" class="btn btn-secondary" :to="`/product?id=${pid}`" target="_blank">前台预览 ↗</router-link>
      <router-link to="/products" class="btn btn-ghost">← 列表</router-link>
      <button class="btn btn-primary" :class="{ loading: busy }" :disabled="busy" @click="save">保存</button>
    </div>
  </div>

  <div class="grid-2" style="align-items:start">
    <div style="display:grid;gap:16px">
      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">基本信息</h3>
        <div class="field"><label>标题</label><input v-model="form.title" class="input"></div>
        <div class="field"><label>Slug</label><input v-model="form.slug" class="input" placeholder="nova-set"></div>
        <div class="field"><label>副标题</label><input v-model="form.subtitle" class="input"></div>
        <div class="field">
          <label>分类</label>
          <select v-model="form.category_id" class="input">
            <option v-for="c in cats" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
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
        <p style="font-size:12px;color:var(--gray)">当前展示：{{ money(form.price_min) }} <span v-if="form.compare_at_price">（划线 {{ money(form.compare_at_price) }}）</span></p>
      </div>

      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">变体管理</h3>
        <div v-if="variants.length" style="display:grid;gap:8px;margin-bottom:14px">
          <div v-for="v in variants" :key="v.id" style="display:flex;gap:12px;align-items:center;font-size:13px;padding:8px 0;border-bottom:1px solid var(--gray-light)">
            <b>{{ v.option1_value }}</b>
            <span style="color:var(--gray)">{{ v.sku }}</span>
            <b style="margin-left:auto">{{ money(v.price) }}</b>
            <span class="tag" :class="v.stock > v.safety_stock ? 'tag-done' : 'tag-error'">{{ v.stock }}</span>
            <button class="btn btn-ghost btn-sm" @click="toggleVar(v)">{{ v.is_active ? '停用' : '启用' }}</button>
          </div>
        </div>
        <p v-else style="font-size:13px;color:var(--gray);margin-bottom:12px">暂无变体（新建商品请先保存再添加）</p>
        <div v-if="pid" style="display:grid;grid-template-columns:1.4fr .8fr .6fr .6fr auto;gap:8px;align-items:end">
          <div class="field"><label>变体名</label><input v-model="newVar.option1" class="input" placeholder="Short Almond"></div>
          <div class="field"><label>价格</label><input v-model.number="newVar.price" class="input" type="number"></div>
          <div class="field"><label>库存</label><input v-model.number="newVar.stock" class="input" type="number"></div>
          <div class="field"><label>安全</label><input v-model.number="newVar.safety" class="input" type="number"></div>
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
          <div style="margin-top:10px;border-radius:12px;overflow:hidden;aspect-ratio:1;background:var(--rose-pale);max-width:220px">
            <img v-if="form.hero_image" :src="form.hero_image" alt="主图预览" style="width:100%;height:100%;object-fit:cover">
          </div>
        </div>
        <div class="field"><label>图集（每行一个 URL，≤20）</label><textarea v-model="imgs" v-if="false" class="input"></textarea>
          <textarea :value="form.images.join('\n')" class="input" rows="4" @input="form.images = $event.target.value.split(/\n+/).filter(Boolean).slice(0, 20)"></textarea>
        </div>
      </div>

      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">组织</h3>
        <div class="field"><label>标签（逗号分隔）</label><input :value="form.tags.join(',')" class="input" @input="form.tags = $event.target.value.split(',').map((s) => s.trim()).filter(Boolean)"></div>
        <label style="display:flex;gap:10px;align-items:center;font-size:13.5px;margin:8px 0;cursor:pointer">
          <input v-model="form.is_new" type="checkbox" style="width:16px;height:16px"> NEW 徽标
        </label>
        <label style="display:flex;gap:10px;align-items:center;font-size:13.5px;cursor:pointer">
          <input v-model="form.is_best_seller" type="checkbox" style="width:16px;height:16px"> 热销徽标
        </label>
      </div>
    </div>
  </div>
</template>
