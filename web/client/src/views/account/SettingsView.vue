<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { req } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import { useUiStore } from '../../stores/ui'
import { useArmConfirm } from '../../composables/useArmConfirm'
import { fmtDate } from '../../composables/datetime'
import { i18n, tt } from '../../i18n'

const auth = useAuthStore()
const ui = useUiStore()
const form = reactive({ name: '', birthday: '' })
const saving = ref(false)
const exporting = ref(false)
const deleting = ref(false)
const sendingReset = ref(false)

/* 两段式确认（useArmConfirm：5s 复位；arm 态红字 + 二段文案） */
const arm = useArmConfirm()

/* 邮件偏好（GET/PUT /api/account/email-preferences，登录态） */
const PREF_LABELS = [
  ['sub_promo', 'Promos & offers', '促销与优惠活动'],
  ['sub_new_arrival', 'New arrivals', '新品上架通知'],
  ['sub_cart_abandon', 'Cart reminders', '购物车提醒'],
]
const prefs = ref(null)
const prefsBusy = ref(false)
const prefsErr = ref(false)

/* 删除请求：POST → {request_id, effective_at}；DELETE 撤销 */
const deletePending = ref(null) /* { effective_at } */
/* 注销冷静期回显消费 Shell 已有会话（/me 含 delete_request），不重复拉取 */
watch(
  () => auth.user && auth.user.delete_request,
  (d) => { if (d) deletePending.value = { effective_at: d.effective_at } },
  { immediate: true },
)

onMounted(() => {
  if (auth.user) {
    form.name = auth.user.name || ''
    form.birthday = auth.user.birthday || ''
  }
  loadPrefs()
})

async function loadPrefs() {
  prefsErr.value = false
  try { prefs.value = await req('GET', '/api/account/email-preferences') }
  catch (_) { prefsErr.value = true }
}

async function save() {
  if (!form.name.trim()) { ui.toast(tt('Name cannot be empty', '昵称不能为空'), 'error'); return }
  saving.value = true
  try {
    await req('PUT', '/api/account/me', { name: form.name.trim(), birthday: form.birthday || null })
    await auth.me()
    ui.toast(tt('Profile saved', '资料已保存'), 'success')
  } catch (_) { ui.toast(tt('Save failed — please retry later', '保存失败，请稍后再试'), 'error') }
  finally { saving.value = false }
}

/* 部分更新：仅传改动的开关（后端语义：任一开 → 复订；全关 → 等价全退） */
async function togglePref(key) {
  prefsBusy.value = true
  try {
    prefs.value = await req('PUT', '/api/account/email-preferences', { [key]: !!prefs.value[key] })
    ui.toast(tt('Email preferences saved', '邮件偏好已保存'), 'success')
  } catch (_) {
    ui.toast(tt('Save failed — please retry later', '保存失败，请稍后再试'), 'error')
    try { prefs.value = await req('GET', '/api/account/email-preferences') } catch (_) { /* */ }
  } finally { prefsBusy.value = false }
}

/* 改密（PUT /api/account/password）：旧密码校验 401 invalid credentials；新密码 8-128 位 */
const pwForm = reactive({ old_password: '', new_password: '', confirm: '' })
const pwBusy = ref(false)
const pwErr = ref('')
const pwDone = ref(false)
const showOldPw = ref(false)
const showNewPw = ref(false)
const showConfirmPw = ref(false)

function pwCheck() {
  if (!pwForm.old_password) return tt('Enter your current password', '请输入当前密码')
  if (pwForm.new_password.length < 8 || pwForm.new_password.length > 128) return tt('New password must be 8-128 characters', '新密码长度需为 8-128 位')
  if (pwForm.new_password === pwForm.old_password) return tt('New password must be different from your current password', '新密码不能与当前密码相同')
  if (pwForm.new_password !== pwForm.confirm) return tt('New passwords do not match', '两次输入的新密码不一致')
  return ''
}

async function changePassword() {
  pwDone.value = false
  pwErr.value = pwCheck()
  if (pwErr.value) return
  pwBusy.value = true
  try {
    await req('PUT', '/api/account/password', {
      old_password: pwForm.old_password,
      new_password: pwForm.new_password,
    })
    pwDone.value = true
    pwForm.old_password = ''
    pwForm.new_password = ''
    pwForm.confirm = ''
    ui.toast(tt('Password changed', '密码已修改'), 'success')
  } catch (e) {
    const d = e && e.data && e.data.detail
    if (e && e.status === 401 && d === 'invalid credentials') pwErr.value = tt('Current password is incorrect', '当前密码不正确')
    else if (e && e.status === 422) pwErr.value = tt('New password must be 8-128 characters', '新密码长度需为 8-128 位')
    else pwErr.value = tt('Change failed — please retry later', '修改失败，请稍后再试')
  } finally { pwBusy.value = false }
}

/* 无直接改密端点时的兜底仍保留：走邮件重置流（POST /password-reset/request，恒 200 防枚举）；两段式确认 */
async function sendReset() {
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
    ui.toast(tt('Data exported', '数据导出成功'), 'success')
  } catch (_) { ui.toast(tt('Export failed — please retry later', '导出失败，请稍后再试'), 'error') }
  finally { exporting.value = false }
}

async function deleteAccount() {
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
    ui.toast(tt('Deletion request cancelled', '已撤销注销申请'), 'success')
  } catch (_) { ui.toast(tt('Could not cancel — please retry later', '撤销失败，请稍后再试'), 'error') }
  finally { deleting.value = false }
}
</script>

<template>
  <div style="display:grid;gap:16px">
    <div class="card" style="padding:20px">
      <h3 style="font-size:15px;margin-bottom:14px">{{ tt('Profile', '个人资料') }}</h3>
      <div class="field"><label>{{ tt('Name', '昵称') }}</label><input v-model="form.name" class="input" maxlength="100" autocomplete="name"></div>
      <div class="field"><label>{{ tt('Birthday (birthday-month points gift)', '生日（生日月有积分礼）') }}</label><input v-model="form.birthday" class="input" type="date" autocomplete="bday"></div>
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
      <div v-else-if="prefsErr" style="font-size:13px;color:var(--error);padding:16px 0">
        {{ tt('Could not load email preferences —', '邮件偏好加载失败，') }}
        <a href="javascript:void(0)" style="color:var(--plum)" @click="loadPrefs">{{ tt('retry', '重试') }}</a>
      </div>
      <div v-else class="skeleton" style="min-height:90px;border-radius:10px" />
    </div>

    <div class="card" style="padding:20px">
      <h3 style="font-size:15px;margin-bottom:8px">{{ tt('Account security', '账号安全') }}</h3>
      <!-- 站内改密（PUT /api/account/password） -->
      <div class="field"><label>{{ tt('Current password', '当前密码') }}</label>
        <div class="pw-wrap">
          <input v-model="pwForm.old_password" class="input" :type="showOldPw ? 'text' : 'password'" autocomplete="current-password" placeholder="••••••••">
          <button type="button" class="pw-eye" :aria-label="tt('Toggle password visibility', '切换密码可见')" @click="showOldPw = !showOldPw">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></svg>
          </button>
        </div>
      </div>
      <div class="field"><label>{{ tt('New password (8-128 chars)', '新密码（8-128 位）') }}</label>
        <div class="pw-wrap">
          <input v-model="pwForm.new_password" class="input" :type="showNewPw ? 'text' : 'password'" autocomplete="new-password" placeholder="••••••••">
          <button type="button" class="pw-eye" :aria-label="tt('Toggle password visibility', '切换密码可见')" @click="showNewPw = !showNewPw">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></svg>
          </button>
        </div>
      </div>
      <div class="field"><label>{{ tt('Confirm new password', '确认新密码') }}</label>
        <div class="pw-wrap">
          <input v-model="pwForm.confirm" class="input" :type="showConfirmPw ? 'text' : 'password'" autocomplete="new-password" placeholder="••••••••">
          <button type="button" class="pw-eye" :aria-label="tt('Toggle password visibility', '切换密码可见')" @click="showConfirmPw = !showConfirmPw">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></svg>
          </button>
        </div>
      </div>
      <div v-if="pwErr" class="field-msg" style="display:block;margin-bottom:10px" role="alert">{{ pwErr }}</div>
      <div v-if="pwDone" class="field-msg" style="display:block;margin-bottom:10px;color:var(--success)">✓ {{ tt('Password updated', '密码已更新') }}</div>
      <button class="btn btn-primary btn-sm" :class="{ loading: pwBusy }" :disabled="pwBusy" @click="changePassword">{{ tt('Change password', '修改密码') }}</button>
      <p style="font-size:12.5px;color:var(--gray);margin:16px 0 12px">{{ tt('Prefer email? Send yourself a reset link (valid for 15 minutes).', '也可以通过注册邮箱重置（重置链接 15 分钟内有效）。') }}</p>
      <button
        class="btn btn-secondary btn-sm" :class="{ arm: arm.is('reset'), loading: sendingReset }"
        :disabled="sendingReset" @click="arm.hit('reset', sendReset)"
      >📧 {{ arm.is('reset') ? tt('Tap again to send', '再点一次发送') : tt('Send password reset email', '发送密码重置邮件') }}</button>
    </div>

    <div class="card" style="padding:20px">
      <h3 style="font-size:15px;margin-bottom:8px">{{ tt('Privacy (GDPR / CCPA)', '隐私（GDPR / CCPA）') }}</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:12px">{{ tt('Download all the data we store about you, or request account deletion (anonymized after the cooling-off period).', '下载我们存储的你的全部数据，或申请注销（冷静期后匿名化）。') }}</p>
      <div v-if="deletePending" style="margin-bottom:12px;padding:12px 14px;border-radius:10px;background:var(--pale-error);font-size:13px;color:var(--error)">
        <b>{{ tt('Deletion request pending', '注销申请处理中') }}</b><span v-if="deletePending.effective_at"> · {{ tt('effective from', '将于') }} {{ fmtDate(deletePending.effective_at) }} {{ tt('生效', 'takes effect') }}</span>
        <div style="margin-top:8px">
          <button class="btn btn-secondary btn-sm" :class="{ loading: deleting }" :disabled="deleting" @click="cancelDelete">{{ tt('Cancel deletion request', '撤销注销申请') }}</button>
        </div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="btn btn-secondary btn-sm" :class="{ loading: exporting }" :disabled="exporting" @click="exportData">⬇ {{ tt('Export my data', '导出我的数据') }}</button>
        <button
          v-if="!deletePending" class="btn btn-ghost btn-sm"
          :class="{ arm: arm.is('del'), loading: deleting }" :disabled="deleting"
          @click="arm.hit('del', deleteAccount)"
        >🗑 {{ arm.is('del') ? tt('Tap again to confirm', '再点一次确认') : tt('Request account deletion', '申请注销账户') }}</button>
      </div>
    </div>
  </div>
</template>
