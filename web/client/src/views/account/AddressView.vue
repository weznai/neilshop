<script setup>
import { onMounted, reactive, ref } from 'vue'
import { req } from '../../api/client'
import { useUiStore } from '../../stores/ui'

const ui = useUiStore()
const list = ref([])
const editing = ref(-1) /* -1 新建 · >=0 编辑索引 */
const form = reactive({ full_name: '', line1: '', line2: '', city: '', state: '', zip: '', country: 'US', phone: '', is_default: false })
const busy = ref(false)

async function load() {
  try { list.value = await req('GET', '/api/account/addresses') } catch (_) { /* */ }
}
onMounted(load)

function reset() {
  Object.assign(form, { full_name: '', line1: '', line2: '', city: '', state: '', zip: '', country: 'US', phone: '', is_default: false })
  editing.value = -1
}
function edit(i) {
  const a = list.value[i]
  Object.assign(form, a)
  editing.value = i
}
async function save() {
  if (!form.full_name || !form.line1 || !form.city || !form.zip) {
    ui.toast('Name, address, city and ZIP are required', 'error')
    return
  }
  busy.value = true
  try {
    if (editing.value === -1) {
      await req('POST', '/api/account/addresses', { ...form })
      ui.toast('Address added ✓', 'success')
    } else {
      await req('PUT', '/api/account/addresses/' + list.value[editing.value].id, { ...form })
      ui.toast('Address updated ✓', 'success')
    }
    reset()
    await load()
  } catch (e) {
    ui.toast('Save failed', 'error')
  } finally { busy.value = false }
}
async function remove(i) {
  try {
    await req('DELETE', '/api/account/addresses/' + list.value[i].id)
    ui.toast('Address removed', 'success')
    await load()
  } catch (_) { ui.toast('Remove failed', 'error') }
}
</script>

<template>
  <div style="display:grid;gap:16px">
    <div class="grid grid-2">
      <div v-for="(a, i) in list" :key="a.id" class="card" style="padding:18px">
        <div style="display:flex;justify-content:space-between;margin-bottom:8px">
          <span v-if="a.is_default" class="tag tag-paid">DEFAULT</span>
          <span v-else class="tag tag-pending">SAVED</span>
          <div style="display:flex;gap:6px">
            <button class="btn btn-ghost btn-sm" @click="edit(i)">Edit</button>
            <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="remove(i)">Delete</button>
          </div>
        </div>
        <div style="font-size:13.5px;line-height:1.7">
          <b>{{ a.full_name }}</b><br>
          {{ a.line1 }} {{ a.line2 || '' }}<br>
          {{ a.city }}, {{ a.state }} {{ a.zip }} · {{ a.country }}
          <span v-if="a.phone"><br>{{ a.phone }}</span>
        </div>
      </div>
    </div>

    <div class="card" style="padding:20px">
      <h3 style="font-size:15px;margin-bottom:14px">{{ editing === -1 ? '➕ Add address' : '✏️ Edit address' }}</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="field" style="grid-column:1/-1"><label>Full name</label><input v-model="form.full_name" class="input"></div>
        <div class="field" style="grid-column:1/-1"><label>Address</label><input v-model="form.line1" class="input"></div>
        <div class="field" style="grid-column:1/-1"><label>Apt / Suite</label><input v-model="form.line2" class="input"></div>
        <div class="field"><label>City</label><input v-model="form.city" class="input"></div>
        <div class="field"><label>State</label><input v-model="form.state" class="input"></div>
        <div class="field"><label>ZIP</label><input v-model="form.zip" class="input"></div>
        <div class="field"><label>Country</label><input v-model="form.country" class="input"></div>
        <div class="field" style="grid-column:1/-1"><label>Phone</label><input v-model="form.phone" class="input"></div>
      </div>
      <label style="display:flex;gap:8px;align-items:center;margin:12px 0;font-size:13.5px">
        <input v-model="form.is_default" type="checkbox" style="width:16px;height:16px"> Set as default
      </label>
      <div style="display:flex;gap:10px">
        <button class="btn btn-primary" :class="{ loading: busy }" :disabled="busy" @click="save">
          {{ editing === -1 ? 'Add address' : 'Save changes' }}
        </button>
        <button v-if="editing !== -1" class="btn btn-ghost" @click="reset">Cancel</button>
      </div>
    </div>
  </div>
</template>
