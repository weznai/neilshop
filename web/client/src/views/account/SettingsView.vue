<script setup>
import { onMounted, reactive, ref } from 'vue'
import { req } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import { useUiStore } from '../../stores/ui'
import { i18n } from '../../i18n'

const auth = useAuthStore()
const ui = useUiStore()
const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)
const form = reactive({ name: '', birthday: '' })
const saving = ref(false)
const exporting = ref(false)
const deleting = ref(false)
const sendingReset = ref(false)

/* 邮件偏好（GET/PUT /api/account/email-preferences，登录态） */
const PREF_LABELS = [
  ['sub_promo', 'Promos & offers', '促销与优惠活动'],
  ['sub_new_arrival', 'New arrivals', '新品上架通知'],
  ['sub_cart_abandon', 'Cart reminders', '购物车提醒'],
]
const prefs = ref(null)
const prefsBusy = ref(false)

/* 删除请求：POST → {request_id, effective_at}；DELETE 撤销 */
const deletePending = ref(null) /* { effective_at } */

onMounted(async () => {
  if (auth.user) {
    form.name = auth.user.name || ''
    form.birthday = auth.user.birthday || ''
  }
  try { prefs.value = await req('GET', '/api/account/email-preferences') } catch (_) { /* */ }
})

async function save() {
  if (!form.name.trim()) { ui.toast(tt('Name cannot be empty', '昵称不能为空'), 'error'); return }
  saving.value = true
  try {
    await req('PUT', '/api/account/me', { name: form.name.trim(), birthday: form.birthday || null })
    await auth.me()
    ui.toast(tt('Profile saved ✓', '资料已保存 ✓'), 'success')
  } catch (_) { ui.toast(tt('Save failed — please retry later', '保存失败，请稍后再试'), 'error') }
  finally { saving.value = false }
}

/* 部分更新：仅传改动的开关（后端语义：任一开 → 复订；全关 → 等价全退） */
async function togglePref(key) {
  prefsBusy.value = true
  try {
    prefs.value = await req('PUT', '/api/account/email-preferences', { [key]: !!prefs.value[key] })
    ui.toast(tt('Email preferences saved ✓', '邮件偏好已保存 ✓'), 'success')
  } catch (_) {
    ui.toast(tt('Save failed — please retry later', '保存失败，请稍后再试'), 'error')
    try { prefs.value = await req('GET', '/api/account/email-preferences') } catch (_) { /* */ }
  } finally { prefsBusy.value = false }
}

/* 无直接改密端点：走邮件重置流（POST /password-reset/request，恒 200 防枚举） */
async function sendReset() {
  if (!window.confirm(tt(`Send a password reset email to ${auth.user?.email}?`, `将向 ${auth.user?.email} 发送密码重置邮件？`))) return
  sendingReset.value = true
  try {
    await req('POST', '/api/account/password-reset/request', { email: auth.user.email })
    ui.toast(tt('Reset email sent (valid for 15 minutes)', '重置邮件已发送（15 分钟内有效）'), 'success')
  } catch (_) { ui.toast(tt('Could not send — please retry later', '发送失败，请稍后再试'), 'error') }
  finally { sendingReset.value = false }
}

async function exportData() {
  exporting.value = true
  try {
    const d = await req('GET', '/api/account/export')
    const blob = new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `glowmag-my-data-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    ui.toast(tt('Data exported ✓', '数据导出成功 ✓'), 'success')
  } catch (_) { ui.toast(tt('Export failed — please retry later', '导出失败，请稍后再试'), 'error') }
  finally { exporting.value = false }
}

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d)) return ''
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

async function deleteAccount() {
  if (!window.confirm(tt('Request account deletion? After the cooling-off period all your data will be anonymized (GDPR).', '确认申请注销账户？冷静期结束后我们将匿名化你的全部数据（GDPR）。'))) return
  deleting.value = true
  try {
    const d = await req('POST', '/api/account/delete-request')
    deletePending.value = { effective_at: d.effective_at }
    ui.toast(tt('Deletion request submitted — you can cancel during the cooling-off period', '注销申请已提交，冷静期内可撤销'), 'success')
  } catch (e) {
    const det = e && e.data && e.data.detail
    if (det === 'delete request already pending') {
      deletePending.value = { effective_at: null }
      ui.toast(tt('A deletion request is already pending', '已有待处理的注销申请'), 'error')
    } else ui.toast(tt('Request failed — please retry later', '申请失败，请稍后再试'), 'error')
  } finally { deleting.value = false }
}
async function cancelDelete() {
  deleting.value = true
  try {
    await req('DELETE', '/api/account/delete-request')
    deletePending.value = null
    ui.toast(tt('Deletion request cancelled ✓', '已撤销注销申请 ✓'), 'success')
  } catch (_) { ui.toast(tt('Could not cancel — please retry later', '撤销失败，请稍后再试'), 'error') }
  finally { deleting.value = false }
}
</script>

<template>
  <div style="display:grid;gap:16px">
    <div class="card" style="padding:20px">
      <h3 style="font-size:15px;margin-bottom:14px">{{ tt('Profile', '个人资料') }}</h3>
      <div class="field"><label>{{ tt('Name', '昵称') }}</label><input v-model="form.name" class="input" maxlength="100"></div>
      <div class="field"><label>{{ tt('Birthday (birthday-month points gift)', '生日（生日月有积分礼）') }}</label><input v-model="form.birthday" class="input" type="date"></div>
      <div class="field"><label>{{ tt('Email (registered, self-service change not supported yet)', '邮箱（注册邮箱，暂不支持自助修改）') }}</label><input :value="auth.user?.email" class="input" disabled style="background:var(--rose-pale)"></div>
      <button class="btn btn-primary" :class="{ loading: saving }" :disabled="saving" @click="save">{{ tt('Save profile', '保存资料') }}</button>
    </div>

    <div class="card" style="padding:20px">
      <h3 style="font-size:15px;margin-bottom:8px">{{ tt('Email preferences', '邮件偏好') }}</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:6px">{{ tt('Toggle any category anytime; turning everything off equals unsubscribing — turning any one back on resubscribes you.', '随时开关各类邮件；全部关闭等价于退订，开启任一项即恢复订阅。') }}</p>
      <div v-if="prefs">
        <label v-for="[k, en, zh] in PREF_LABELS" :key="k" style="display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid var(--gray-light);font-size:14px">
          <span>{{ tt(en, zh) }}</span>
          <input
            v-model="prefs[k]"
            type="checkbox" style="width:18px;height:18px;accent-color:var(--plum)"
            :disabled="prefsBusy" @change="togglePref(k)"
          >
        </label>
        <div v-if="prefs.unsubscribed_at" style="font-size:12.5px;color:var(--warn);margin-top:8px">
          ⚠️ {{ tt(`Fully unsubscribed since ${fmtDate(prefs.unsubscribed_at)} — turn on any toggle to resubscribe.`, `当前处于全退订状态（${fmtDate(prefs.unsubscribed_at)}），开启任一开关即可恢复订阅。`) }}
        </div>
      </div>
      <div v-else class="skeleton" style="min-height:90px;border-radius:10px" />
    </div>

    <div class="card" style="padding:20px">
      <h3 style="font-size:15px;margin-bottom:8px">{{ tt('Account security', '账号安全') }}</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:12px">{{ tt('Reset your password via your registered email (link valid for 15 minutes).', '通过注册邮箱重置密码（重置链接 15 分钟内有效）。') }}</p>
      <button class="btn btn-secondary btn-sm" :class="{ loading: sendingReset }" :disabled="sendingReset" @click="sendReset">📧 {{ tt('Send password reset email', '发送密码重置邮件') }}</button>
    </div>

    <div class="card" style="padding:20px">
      <h3 style="font-size:15px;margin-bottom:8px">{{ tt('Privacy (GDPR / CCPA)', '隐私（GDPR / CCPA）') }}</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:12px">{{ tt('Download all the data we store about you, or request account deletion (anonymized after the cooling-off period).', '下载我们存储的你的全部数据，或申请注销（冷静期后匿名化）。') }}</p>
      <div v-if="deletePending" style="margin-bottom:12px;padding:12px 14px;border-radius:10px;background:#FDE9EA;font-size:13px;color:var(--error)">
        <b>{{ tt('Deletion request pending', '注销申请处理中') }}</b><span v-if="deletePending.effective_at"> · {{ tt('effective from', '将于') }} {{ fmtDate(deletePending.effective_at) }} {{ tt('生效', 'takes effect') }}</span>
        <div style="margin-top:8px">
          <button class="btn btn-secondary btn-sm" :class="{ loading: deleting }" :disabled="deleting" @click="cancelDelete">{{ tt('Cancel deletion request', '撤销注销申请') }}</button>
        </div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="btn btn-secondary btn-sm" :class="{ loading: exporting }" :disabled="exporting" @click="exportData">⬇ {{ tt('Export my data', '导出我的数据') }}</button>
        <button v-if="!deletePending" class="btn btn-ghost btn-sm" style="color:var(--error)" :class="{ loading: deleting }" :disabled="deleting" @click="deleteAccount">🗑 {{ tt('Request account deletion', '申请注销账户') }}</button>
      </div>
    </div>
  </div>
</template>
