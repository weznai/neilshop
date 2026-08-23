<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { req } from '../api/client'
import { fmtDate, zulu } from '../composables/datetime'
import { i18n, tt } from '../i18n'
import { useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'

const auth = useAuthStore()
const ui = useUiStore()
const subs = ref([])
const plans = ref(null)
const loaded = ref(false)
const failed = ref(false)
const busy = ref(false)

/* 计划套餐（后端 /api/subscriptions/me.plans：1=每4周$12.99 2=每6周$13.99 3=每8周$14.99） */
const FALLBACK_PLANS = [
  { id: 1, weeks: 4, price_cents: 1299 },
  { id: 2, weeks: 6, price_cents: 1399 },
  { id: 3, weeks: 8, price_cents: 1499 },
]
/* style_mode：1 自选款式 2 盲盒惊喜（models/promo.py） */
const styleModes = computed(() => [
  [1, tt('🎨 Pick your own', '🎨 自选款式'), tt('Choose your favorite style every box', '每期自己挑喜欢的花色')],
  [2, tt('🎁 Blind box', '🎁 盲盒惊喜'), tt("Editor's surprise curation every box", '编辑部精选搭配，惊喜开箱')],
])
const picked = ref(2)
const styleMode = ref(1)

const money = (c) => (c == null ? '—' : '$' + (c / 100).toFixed(2))

/* 生效/暂停中订阅视为“已有订阅”；仅剩已取消(5)等历史记录时允许重新订阅 */
const hasLive = computed(() => subs.value.some((s) => s.status === 1 || s.status === 2))
const planList = computed(() => plans.value || FALLBACK_PLANS)
const planInfo = (id) => planList.value.find((p) => p.id === id) || {}
const planPrice = (id) => {
  const p = planInfo(id)
  return p.price_cents != null ? money(p.price_cents) : '—'
}
const planName = (s) => {
  const w = planInfo(s.plan).weeks
  return w ? tt(`every ${w} weeks`, `每 ${w} 周`) : s.plan_text
}
function statusLabel(s) {
  const map = { 1: [() => tt('Active', '生效中')], 2: [() => tt('Paused', '已暂停')], 5: [() => tt('Cancelled', '已取消')] }
  return (map[s.status] && map[s.status][0]()) || s.status_text || String(s.status)
}

async function load() {
  failed.value = false
  try {
    const d = await req('GET', '/api/subscriptions/me')
    subs.value = d.items || []
    if (d.plans) plans.value = d.plans
  } catch (e) {
    if (e && e.status === 401) return /* 未登录 */
    failed.value = true
  } finally { loaded.value = true }
}
onMounted(() => { if (auth.isLoggedIn) load(); else loaded.value = true })

/* 创建订阅：POST /api/subscriptions {plan:1-3, style_mode:1-2} */
async function subscribe() {
  busy.value = true
  try {
    await req('POST', '/api/subscriptions', { plan: picked.value, style_mode: styleMode.value })
    ui.toast(tt('Welcome to the Nail Club 💅', '欢迎加入 Nail Club 💅'), 'success')
    await load()
  } catch (e) {
    ui.toast(
      e && e.status === 422
        ? tt('Please pick a plan and style preference', '请选择套餐与款式偏好')
        : tt('Could not subscribe, please try again', '订阅失败，请稍后再试'),
      'error',
    )
  } finally { busy.value = false }
}

async function act(sub, action, body) {
  busy.value = true
  try {
    await req('POST', `/api/subscriptions/${sub.id}/${action}`, body || {})
    ui.toast(tt('Done', '操作成功'), 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail
    ui.toast(
      d === 'not active' ? tt('This subscription is not active', '订阅当前不是生效状态')
        : d === 'not paused' ? tt('This subscription is not paused', '订阅当前未暂停')
        : d === 'not cancellable' ? tt('Already cancelled — no need to repeat', '订阅已取消，无需重复操作')
        : tt('Action failed, please try again', '操作失败，请稍后再试'),
      'error',
    )
  } finally { busy.value = false }
}
function pause(sub) { act(sub, 'pause', {}) }
function resume(sub) { act(sub, 'resume') }
/* 取消订阅：两段式站内确认（替代 window.confirm，对齐 UnsubscribeView 模式）——首次点击进入 arm 态，5 秒未确认自动复位；
 * arm 态展示取消原因 chips（后端 cancel_reason 1-4），默认选 1，请求携带所选值 */
const cancelArm = ref(0)
const cancelReason = ref(1)
const cancelReasons = computed(() => [
  [1, tt('Got what I needed', '已收到不再需要')],
  [2, tt('Too pricey', '价格太贵')],
  [3, tt('Prefer buying another way', '想换其他方式购买')],
  [4, tt('Other reason', '其他')],
])
let cancelTimer = null
onUnmounted(() => clearTimeout(cancelTimer))
function armCancel(sub) {
  if (cancelArm.value !== sub.id) {
    cancelArm.value = sub.id
    cancelReason.value = 1
  }
  clearTimeout(cancelTimer)
  cancelTimer = setTimeout(() => { cancelArm.value = 0 }, 5000)
}
function pickCancelReason(sub, v) {
  cancelReason.value = v
  armCancel(sub)
}
function cancelSub(sub) {
  if (cancelArm.value !== sub.id) { armCancel(sub); return }
  cancelArm.value = 0
  clearTimeout(cancelTimer)
  act(sub, 'cancel', { cancel_reason: cancelReason.value })
}
function skipNext(sub) {
  /* 跳过下一盒：skip_until = 下次账单日 + 一个周期 */
  const p = planInfo(sub.plan)
  const base = sub.next_billing_at ? new Date(sub.next_billing_at) : new Date()
  base.setDate(base.getDate() + (p.weeks || 4))
  act(sub, 'skip', { skip_until: base.toISOString().replace('Z', '') })
}

const styleText = (m) => (m === 2 ? tt('Blind box', '盲盒惊喜') : tt('My choice', '自选款式'))
</script>

<template>
  <section class="section">
    <div class="container">
      <div style="text-align:center;margin-bottom:30px">
        <div style="font-size:46px">📦</div>
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">{{ tt('Nail Club Monthly Box', 'Nail Club 订阅月盒') }}</h1>
        <p style="color:var(--gray)">{{ tt('Fresh press-on nails auto-delivered · pause / skip / cancel anytime', '新款美甲自动到家 · 可暂停 / 跳过 / 随时取消') }}</p>
      </div>

      <div v-if="!loaded" class="skeleton" style="height:140px;border-radius:14px;max-width:560px;margin:0 auto 26px" />

      <template v-else>
        <!-- 未登录 -->
        <div v-if="!auth.isLoggedIn" class="card" style="max-width:520px;margin:0 auto 26px;padding:20px;text-align:center">
          <p style="font-size:13.5px;color:var(--gray)">
            <router-link :to="{ path: '/login', query: { next: '/subscribe' } }" style="color:var(--plum);font-weight:600">{{ tt('Log in', '登录') }}</router-link>
            {{ tt('to subscribe and manage your boxes.', '后即可订阅与管理系统。') }}
          </p>
        </div>

        <div v-else-if="failed" class="card" style="max-width:520px;margin:0 auto 26px;padding:20px;text-align:center;color:var(--gray)">
          {{ tt('Failed to load —', '加载失败，') }}<a href="javascript:void(0)" style="color:var(--plum)" @click="load">{{ tt('retry', '重试') }}</a>
        </div>

        <!-- 我的订阅（含已取消的历史订阅，供查看） -->
        <template v-else-if="subs.length">
          <div v-for="s in subs" :key="s.id" class="card" style="max-width:560px;margin:0 auto 26px;padding:20px">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
              <b>{{ planName(s) }} {{ tt('per box', '一盒') }} · {{ styleText(s.style_mode) }}</b>
              <span class="tag" :class="s.status === 1 ? 'tag-paid' : s.status === 2 ? 'tag-pending' : 'tag-done'">{{ statusLabel(s) }}</span>
            </div>
            <div style="font-size:13px;color:var(--gray);margin:6px 0 12px">
              {{ planPrice(s.plan) }} {{ tt('/ box', '/ 盒') }} · {{ tt('next billing', '下次出账') }} {{ fmtDate(s.next_billing_at) }}
            </div>
            <div v-if="s.status === 1" style="display:flex;gap:8px;flex-wrap:wrap">
              <button class="btn btn-secondary btn-sm" :disabled="busy" @click="skipNext(s)">{{ tt('⏭ Skip next box', '⏭ 跳过下一盒') }}</button>
              <button class="btn btn-secondary btn-sm" :disabled="busy" @click="pause(s)">{{ tt('⏸ Pause', '⏸ 暂停') }}</button>
              <button
                class="btn btn-ghost btn-sm" :disabled="busy" @click="cancelSub(s)"
                :style="cancelArm === s.id ? 'color:#fff;background:var(--error)' : 'color:var(--error)'"
              >{{ cancelArm === s.id ? tt('Tap again to confirm', '再点一次确认取消') : tt('Cancel', '取消订阅') }}</button>
            </div>
            <div v-else-if="s.status === 2" style="display:flex;gap:8px;flex-wrap:wrap">
              <button class="btn btn-primary btn-sm" :disabled="busy" @click="resume(s)">{{ tt('▶ Resume', '▶️ 恢复订阅') }}</button>
              <button
                class="btn btn-ghost btn-sm" :disabled="busy" @click="cancelSub(s)"
                :style="cancelArm === s.id ? 'color:#fff;background:var(--error)' : 'color:var(--error)'"
              >{{ cancelArm === s.id ? tt('Tap again to confirm', '再点一次确认取消') : tt('Cancel', '取消订阅') }}</button>
            </div>
            <div v-if="cancelArm === s.id">
              <div style="font-size:12px;color:var(--gray);margin:10px 0 0">{{ tt('Why are you cancelling?', '取消原因') }}</div>
              <div style="display:flex;gap:6px;flex-wrap:wrap">
                <button
                  v-for="[v, label] in cancelReasons" :key="v" type="button"
                  class="trend-chip" :class="{ on: cancelReason === v }" :aria-pressed="cancelReason === v"
                  @click="pickCancelReason(s, v)"
                >{{ label }}</button>
              </div>
            </div>
          </div>
        </template>

        <!-- 套餐选择（没有生效/暂停中的订阅时展示：含仅有已取消订阅的老用户） -->
        <template v-if="!auth.isLoggedIn || failed || !hasLive">
          <div class="grid grid-3">
            <div
              v-for="p in planList" :key="p.id" class="card" style="padding:22px;cursor:pointer;position:relative"
              :style="{ outline: picked === p.id ? '2px solid var(--plum)' : '' }" @click="picked = p.id"
            >
              <span v-if="p.id === 2" class="badge badge-best" style="position:absolute;top:-10px;right:14px">{{ tt('MOST LOVED', '最受欢迎') }}</span>
              <b style="font-family:var(--font-title);font-size:20px">{{ tt(`Every ${p.weeks} weeks`, `每 ${p.weeks} 周一盒`) }}</b>
              <div style="margin:10px 0 4px"><b style="font-size:28px">{{ money(p.price_cents) }}</b> <span style="color:var(--gray);font-size:13px">{{ tt('/ box', '/ 盒') }}</span></div>
              <div style="font-size:13.5px;color:var(--gray)">{{ tt('Handpicked seasonal press-on sets', '精选当季新款穿戴甲') }}</div>
            </div>
          </div>

          <div class="card" style="max-width:560px;margin:18px auto 0;padding:18px">
            <div style="font-size:14px;font-weight:700;margin-bottom:10px">{{ tt('Style preference', '选择款式偏好') }}</div>
            <div class="grid grid-2">
              <label v-for="[m, name, desc] in styleModes" :key="m" style="padding:12px;border:1.5px solid var(--gray-light);border-radius:12px;cursor:pointer;font-size:13.5px"
                :style="{ borderColor: styleMode === m ? 'var(--plum)' : '', background: styleMode === m ? 'var(--rose-pale)' : '' }">
                <span style="display:flex;gap:8px;align-items:center;font-weight:700">
                  <input v-model="styleMode" :value="m" type="radio" style="accent-color:var(--plum)"> {{ name }}
                </span>
                <span style="display:block;color:var(--gray);font-size:12.5px;margin-top:4px;padding-left:24px">{{ desc }}</span>
              </label>
            </div>
          </div>

          <div style="text-align:center;margin-top:22px">
            <button v-if="auth.isLoggedIn" class="btn btn-primary btn-lg" :class="{ loading: busy }" :disabled="busy" @click="subscribe">
              {{ tt(`Subscribe · every ${planInfo(picked).weeks} weeks ${money(planInfo(picked).price_cents)}`, `立即订阅 · 每 ${planInfo(picked).weeks} 周 ${money(planInfo(picked).price_cents)}`) }}
            </button>
            <router-link v-else class="btn btn-primary btn-lg" :to="{ path: '/login', query: { next: '/subscribe' } }">{{ tt('Log in to subscribe', '登录后订阅') }}</router-link>
          </div>
        </template>
      </template>
    </div>
  </section>
</template>
