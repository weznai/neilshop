<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { req } from '../../api/client'
import { useUiStore } from '../../stores/ui'
import { useArmConfirm } from '../../composables/useArmConfirm'
import { i18n, tt } from '../../i18n'
import { COUNTRIES, PHONE_RE } from '../../data/countries'

const ui = useUiStore()

/* 两段式确认（useArmConfirm：5s 复位；arm 态红字 + 二段文案） */
const arm = useArmConfirm()

const list = ref([])
const loaded = ref(false)
const failed = ref(false)
/* 表单滚动定位：新增/编辑展开后滚到可视区 */
const formCard = ref(null)
/* 表单默认收起：点「新增地址 / 编辑」才展开，保存/取消后收起 */
const showForm = ref(false)
/* 编辑态存地址 id（null 新建）——防删除后索引错位覆盖 */
const editing = ref(null)
const form = reactive({ full_name: '', line1: '', line2: '', city: '', state: '', zip: '', country: 'US', phone: '', is_default: false })
const busy = ref(false)
const settingDefault = ref(0)

/* 常用国家下拉（2 字母码，data/countries 共享）+ 其他自填 */
const OTHER = '__other__'
const countrySel = computed({
  get() {
    const c = (form.country || '').trim().toUpperCase()
    return COUNTRIES.some(([code]) => code === c) ? c : OTHER
  },
  set(v) { form.country = v === OTHER ? '' : v },
})
const countryIsOther = computed(() => countrySel.value === OTHER)

async function load() {
  failed.value = false
  try { list.value = await req('GET', '/api/account/addresses') } catch (_) { failed.value = true }
  loaded.value = true
}
onMounted(load)

function reset() {
  Object.assign(form, { full_name: '', line1: '', line2: '', city: '', state: '', zip: '', country: 'US', phone: '', is_default: false })
  editing.value = null
  showForm.value = false
}
function edit(a) {
  Object.assign(form, {
    full_name: a.full_name || '', line1: a.line1 || '', line2: a.line2 || '',
    city: a.city || '', state: a.state || '', zip: a.zip || '',
    country: a.country || 'US', phone: a.phone || '', is_default: !!a.is_default,
  })
  editing.value = a.id
  showForm.value = true
  scrollToForm()
}

const editingAddr = computed(() => (editing.value === null ? null : list.value.find((a) => a.id === editing.value) || null))
/* 唯一默认地址不可取消勾选（需保留至少一个默认地址；可先将其他地址设为默认） */
const defaultLocked = computed(() => !!editingAddr.value && editingAddr.value.is_default && !list.value.some((a) => a.is_default && a.id !== editing.value))

/* 后端 AddressIn：姓名/地址1/城市/ZIP 必填，国家 2 字母码（默认 US） */
function fieldCheck() {
  if (!form.full_name.trim()) return tt('Enter the recipient name', '请填写收件人姓名')
  if (!form.line1.trim()) return tt('Enter the street address', '请填写街道地址')
  if (!form.city.trim()) return tt('Enter the city', '请填写城市')
  if (!form.zip.trim()) return tt('Enter the ZIP / postal code', '请填写邮编')
  if (!/^[A-Za-z]{2}$/.test(form.country.trim())) return tt('Country must be a 2-letter code (e.g. US)', '国家代码需为 2 位字母（如 US）')
  if (form.phone.trim() && !PHONE_RE.test(form.phone.trim())) return tt('Enter a valid phone number', '电话格式不正确')
  return ''
}

async function save() {
  const msg = fieldCheck()
  if (msg) { ui.toast(msg, 'error'); return }
  if (defaultLocked.value && !form.is_default) {
    ui.toast(tt('Keep at least one default address — set another one as default first', '需保留至少一个默认地址，可先将其他地址设为默认'), 'error')
    return
  }
  if (editing.value !== null && !editingAddr.value) {
    ui.toast(tt('This address no longer exists — please refresh', '该地址不存在，请刷新'), 'error')
    reset()
    return
  }
  busy.value = true
  const body = {
    full_name: form.full_name.trim(),
    line1: form.line1.trim(),
    line2: form.line2.trim() || null,
    city: form.city.trim(),
    state: form.state.trim() || null,
    zip: form.zip.trim(),
    country: form.country.trim().toUpperCase(),
    phone: form.phone.trim() || null,
    is_default: !!form.is_default,
  }
  try {
    if (editing.value === null) {
      await req('POST', '/api/account/addresses', body)
      ui.toast(tt('Address added', '地址已添加'), 'success')
    } else {
      await req('PUT', '/api/account/addresses/' + editing.value, body)
      ui.toast(tt('Address updated', '地址已更新'), 'success')
    }
    reset()
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail
    if (e && e.status === 422 && d === 'last_default_required') ui.toast(tt('Keep at least one default address — set another one as default first', '需保留至少一个默认地址，可先将其他地址设为默认'), 'error')
    else if (e && e.status === 404) ui.toast(tt('This address no longer exists — please refresh', '该地址不存在，请刷新'), 'error')
    else ui.toast(tt('Save failed — please check the fields', '保存失败，请检查填写'), 'error')
  } finally { busy.value = false }
}

/* 打开新增表单：清空残留编辑态 */
function startAdd() {
  reset()
  showForm.value = true
  scrollToForm()
}

async function scrollToForm() {
  await nextTick()
  try { formCard.value?.scrollIntoView({ behavior: 'smooth', block: 'center' }) } catch (_) { /* 旧浏览器 */ }
}

/* 快捷设为默认：整份 AddressIn 体重放，仅翻转 is_default */
async function makeDefault(a) {
  if (settingDefault.value || a.is_default) return
  settingDefault.value = a.id
  try {
    await req('PUT', '/api/account/addresses/' + a.id, {
      full_name: a.full_name,
      line1: a.line1,
      line2: a.line2 || null,
      city: a.city,
      state: a.state || null,
      zip: a.zip,
      country: (a.country || 'US').toUpperCase(),
      phone: a.phone || null,
      is_default: true,
    })
    ui.toast(tt('Default address updated', '默认地址已更新'), 'success')
    await load()
  } catch (e) {
    if (e && e.status === 404) {
      ui.toast(tt('This address was deleted — list refreshed', '地址已被删除，已刷新'), 'error')
      await load()
    } else {
      ui.toast(tt('Could not set default — please retry', '设置失败，请稍后再试'), 'error')
    }
  } finally { settingDefault.value = 0 }
}

async function remove(a) {
  if (a.is_default && !list.value.some((x) => x.is_default && x.id !== a.id)) {
    ui.toast(tt('Please set another address as default before deleting this one', '请先将其他地址设为默认'), 'error')
    arm.reset()
    return
  }
  try {
    await req('DELETE', '/api/account/addresses/' + a.id)
    ui.toast(tt('Address removed', '地址已删除'), 'success')
    if (editing.value === a.id) reset()
    await load()
  } catch (_) { ui.toast(tt('Delete failed — please retry later', '删除失败，请稍后再试'), 'error') }
}
</script>

<template>
  <div style="display:grid;gap:16px">
    <div v-if="!loaded" class="grid grid-2">
      <div v-for="i in 2" :key="i" class="skeleton" style="height:150px;border-radius:14px" />
    </div>
    <template v-else>
      <div v-if="failed" class="card" style="padding:30px;text-align:center;color:var(--gray)">
        {{ tt('Could not load your addresses —', '地址加载失败 ——') }} <a href="javascript:void(0)" style="color:var(--plum)" @click="load">{{ tt('retry', '重试') }}</a>
      </div>
      <template v-else>
        <div v-if="list.length" class="grid grid-2">
        <div v-for="a in list" :key="a.id" class="card" style="padding:18px">
          <div style="display:flex;justify-content:space-between;margin-bottom:8px">
            <span v-if="a.is_default" class="tag tag-default">{{ tt('Default', '默认地址') }}</span>
            <span v-else class="tag tag-done">{{ tt('Saved', '已保存') }}</span>
            <div style="display:flex;gap:6px">
              <button v-if="!a.is_default" class="btn btn-ghost btn-sm" style="color:var(--plum)" :class="{ loading: settingDefault === a.id }" :disabled="!!settingDefault" @click="makeDefault(a)">{{ tt('Set as default', '设为默认') }}</button>
              <button class="btn btn-ghost btn-sm" @click="edit(a)">{{ tt('Edit', '编辑') }}</button>
              <button
                class="btn btn-ghost btn-sm" :class="{ arm: arm.is(a.id) }"
                @click="arm.hit(a.id, () => remove(a))"
              >{{ arm.is(a.id) ? tt('Tap again to confirm', '再点一次确认') : tt('Delete', '删除') }}</button>
            </div>
          </div>
          <div style="font-size:13.5px;line-height:1.7">
            <b>{{ a.full_name }}</b><br>
            {{ a.line1 }} {{ a.line2 || '' }}<br>
            {{ a.city }}{{ a.state ? ', ' + a.state : '' }} {{ a.zip }} · {{ a.country }}
            <span v-if="a.phone"><br>{{ a.phone }}</span>
          </div>
        </div>
      </div>
      <div v-else class="card" style="padding:26px;text-align:center;color:var(--gray);font-size:14px">
        📍 {{ tt('No saved addresses yet — add one here for faster checkout.', '还没有保存地址 —— 结账时填写或在此新增，下单更快。') }}
      </div>
      <div v-if="!showForm" style="display:flex;justify-content:center">
        <button class="btn btn-secondary" @click="startAdd">➕ {{ tt('Add address', '新增地址') }}</button>
      </div>
      </template>
    </template>

    <div v-if="showForm" ref="formCard" class="card addr-form" :class="{ 'addr-editing': editing !== null }" style="padding:20px">
      <h3 style="font-size:15px;margin-bottom:14px">
        <template v-if="editing === null">➕ {{ tt('Add address', '新增地址') }}</template>
        <template v-else>✏️ {{ tt('Edit address', '编辑地址') }}<span v-if="editingAddr" style="color:var(--plum)"> · {{ editingAddr.full_name }}</span></template>
      </h3>
      <form @submit.prevent="save">
        <div class="grid-m-1" style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div class="field" style="grid-column:1/-1"><label>{{ tt('Recipient name', '收件人姓名') }} *</label><input v-model="form.full_name" class="input" maxlength="100" autocomplete="name"></div>
          <div class="field" style="grid-column:1/-1"><label>{{ tt('Street address', '街道地址') }} *</label><input v-model="form.line1" class="input" maxlength="191" autocomplete="address-line1"></div>
          <div class="field" style="grid-column:1/-1"><label>{{ tt('Apt / Suite (optional)', '门牌 / 单元（可选）') }}</label><input v-model="form.line2" class="input" maxlength="191" autocomplete="address-line2"></div>
          <div class="field"><label>{{ tt('City', '城市') }} *</label><input v-model="form.city" class="input" maxlength="100" autocomplete="address-level2"></div>
          <div class="field"><label>{{ tt('State / Province', '州 / 省') }}</label><input v-model="form.state" class="input" maxlength="100" autocomplete="address-level1"></div>
          <div class="field"><label>{{ tt('ZIP / Postal code', '邮编') }} *</label><input v-model="form.zip" class="input" maxlength="20" autocomplete="postal-code"></div>
          <div class="field">
            <label>{{ tt('Country', '国家') }} *</label>
            <select v-model="countrySel" class="input" autocomplete="country">
              <option v-for="[code, label] in COUNTRIES" :key="code" :value="code">{{ label }}（{{ code }}）</option>
              <option :value="OTHER">{{ tt('Other (enter 2-letter code)', '其他（自填 2 位代码）') }}</option>
            </select>
          </div>
          <div v-if="countryIsOther" class="field">
            <label>{{ tt('Country code (2 letters)', '国家代码（2 位字母）') }} *</label>
            <input v-model="form.country" class="input" maxlength="2" placeholder="US" autocomplete="country-code" @input="form.country = form.country.toUpperCase()">
          </div>
          <div class="field" style="grid-column:1/-1"><label>{{ tt('Phone (optional)', '电话（可选）') }}</label><input v-model="form.phone" class="input" maxlength="32" type="tel" autocomplete="tel"></div>
        </div>
        <label style="display:flex;gap:8px;align-items:center;margin:12px 0;font-size:13.5px;opacity:.75" :class="{ 'addr-locked': defaultLocked }">
          <input v-model="form.is_default" type="checkbox" style="width:16px;height:16px" :disabled="defaultLocked">
          {{ tt('Set as default address', '设为默认地址') }}
          <span v-if="defaultLocked" style="font-size:12px;color:var(--gray)">（{{ tt('keep at least one default', '需保留至少一个默认地址') }}）</span>
        </label>
        <div style="display:flex;gap:10px">
          <button type="submit" class="btn btn-primary" :class="{ loading: busy }" :disabled="busy">
            {{ editing === null ? tt('Add address', '添加地址') : tt('Save changes', '保存修改') }}
          </button>
          <button type="button" class="btn btn-ghost" @click="reset">{{ tt('Cancel', '取消') }}</button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
/* 编辑态表单卡：左缘 3px plum 强调 */
.addr-editing { border-left: 3px solid var(--plum); }
/* 默认地址锁定态（原误用全局 gm-locked 滚动锁类名，改局部语义类） */
.addr-locked { cursor: not-allowed; }
/* 默认地址标签（plum 底白字，与 tag-paid 支付语义解耦） */
.tag-default { background: var(--plum); color: #fff; }
</style>
