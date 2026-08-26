<script setup>
/* 我的券包（账户子页）：GET /api/promo/coupons/mine，按 status 0可用/1已用/2过期 分组 tab；
   券码点击复制，已用可跳关联订单详情 */
import { computed, onMounted, ref } from 'vue'
import { req } from '../../api/client'
import { useUiStore } from '../../stores/ui'
import { fmtDate } from '../../composables/datetime'
import { tt } from '../../i18n'

const ui = useUiStore()

const items = ref([])
const loaded = ref(false)
const failed = ref(false)

async function load() {
  loaded.value = false
  failed.value = false
  try { items.value = (await req('GET', '/api/promo/coupons/mine')).items || [] }
  catch (_) { items.value = []; failed.value = true }
  loaded.value = true
}
onMounted(load)

/* 分组 tab：[status, [en, zh]]（对齐 OrdersView tab 交互，本地过滤无需分页请求） */
const TABS = [
  [0, ['Usable', '可使用']],
  [1, ['Used', '已使用']],
  [2, ['Expired', '已过期']],
]
const tab = ref(0)
const counts = computed(() => {
  const m = { 0: 0, 1: 0, 2: 0 }
  items.value.forEach((c) => { if (m[c.status] != null) m[c.status]++ })
  return m
})
const shown = computed(() => items.value.filter((c) => c.status === tab.value))

/* 权益/门槛：口径与领券中心一致（type 1 百分比 / 2 固定金额（value 美分）/ 3 免邮） */
function benefit(c) {
  if (c.type === 1) return c.value + '% OFF'
  if (c.type === 2) return '$' + ((c.value || 0) / 100).toFixed(2) + ' OFF'
  return tt('FREE SHIPPING', '免邮')
}
function minText(c) {
  return c.min_subtotal
    ? tt('Min. spend ', '满 ') + '$' + (c.min_subtotal / 100).toFixed(2) + tt(' usable', ' 可用')
    : tt('No min. spend', '无门槛')
}
function expireText(c) {
  return c.expires_at ? tt('Expires ', '有效期至 ') + fmtDate(c.expires_at) : tt('No expiry', '长期有效')
}

/* 复制券码：clipboard API 优先，execCommand 兜底（非 https/旧浏览器），双双失败 toast 展示原码 */
async function copyCode(c) {
  const code = String(c.code || '')
  if (!code) return
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(code)
    } else {
      const ta = document.createElement('textarea')
      ta.value = code
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    ui.toast(tt('Code copied — apply it at checkout', '券码已复制，结算时粘贴使用'), 'success')
  } catch (_) {
    ui.toast(tt('Copy failed — your code: ', '复制失败，券码：') + code, 'info')
  }
}
</script>

<template>
  <div>
    <div class="mc-tabs" role="tablist">
      <button
        v-for="[sv, label] in TABS" :key="sv" class="mc-tab" :class="{ on: tab === sv }"
        role="tab" :aria-selected="tab === sv" @click="tab = sv"
      >{{ tt(label[0], label[1]) }}<span v-if="counts[sv]" class="mc-cnt">{{ counts[sv] }}</span></button>
    </div>

    <div v-if="!loaded" style="display:grid;gap:12px">
      <div v-for="i in 2" :key="i" class="skeleton" style="height:118px;border-radius:14px" />
    </div>

    <div v-else-if="failed" class="card" style="padding:30px;text-align:center;color:var(--gray)">
      {{ tt('Coupons failed to load —', '优惠券加载失败，') }}<a href="javascript:void(0)" style="color:var(--plum)" @click="load">{{ tt('retry', '重试') }}</a>
    </div>

    <div v-else-if="shown.length" style="display:grid;gap:12px">
      <div v-for="c in shown" :key="c.id + '-' + c.code" class="card mc-card" :class="{ dead: c.status !== 0 }">
        <div class="mc-benefit">
          <b>{{ benefit(c) }}</b>
          <small v-if="c.type === 1 && c.max_discount">{{ tt('up to ', '最高省 ') }}${{ (c.max_discount / 100).toFixed(2) }}</small>
        </div>
        <div class="mc-body">
          <div class="mc-top">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;min-width:0">
              <b class="mc-name">{{ c.name }}</b>
              <span v-if="c.first_order_only" class="tag tag-hot">{{ tt('First order', '首单') }}</span>
            </div>
            <span class="tag" :class="c.status === 0 ? 'tag-paid' : (c.status === 1 ? 'tag-done' : 'tag-error')">
              {{ c.status === 0 ? tt('Usable', '可使用') : (c.status === 1 ? tt('Used', '已使用') : tt('Expired', '已过期')) }}
            </span>
          </div>
          <div class="mc-meta">{{ minText(c) }} · {{ expireText(c) }}</div>
          <div class="mc-foot">
            <button class="mc-code" type="button" :title="tt('Copy code', '复制券码')" @click="copyCode(c)">
              <b>{{ c.code }}</b><span>{{ tt('Copy', '复制') }}</span>
            </button>
            <div class="mc-actions">
              <!-- 已用：关联订单可跳详情 -->
              <template v-if="c.status === 1">
                <span class="mc-used">{{ tt('Used', '已使用') }}<template v-if="c.used_at"> · {{ fmtDate(c.used_at) }}</template></span>
                <router-link v-if="c.order_no" class="mc-order" :to="{ path: '/account/orders/detail', query: { no: c.order_no } }">
                  {{ c.order_no }} →
                </router-link>
              </template>
              <router-link v-else-if="c.status === 0" class="btn btn-primary btn-sm" to="/store">{{ tt('Use it →', '去使用 →') }}</router-link>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="card" style="padding:30px;text-align:center;color:var(--gray)">
      <div style="font-size:38px;margin-bottom:8px">🎟️</div>
      {{ tt('No coupons in this tab yet', '该分组暂无优惠券') }}
      <div v-if="tab === 0" style="margin-top:12px">
        <router-link class="btn btn-primary btn-sm" to="/coupons">{{ tt('Go to Coupon Center →', '去领券中心逛逛 →') }}</router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* tab 条：对齐 OrdersView .o-tabs 视觉（scoped 无法跨组件复用，规则同源） */
.mc-tabs { display: flex; gap: 4px; margin-bottom: 16px; overflow-x: auto; scrollbar-width: none; -ms-overflow-style: none; }
.mc-tabs::-webkit-scrollbar { display: none; }
.mc-tab { flex: none; display: inline-flex; align-items: center; gap: 5px; padding: 10px 12px; font-size: 13.5px; font-weight: 600; color: var(--gray); background: none; border: none; border-bottom: 2px solid transparent; white-space: nowrap; cursor: pointer; transition: color .15s, border-color .15s; }
.mc-tab:hover { color: var(--plum); }
.mc-tab.on { color: var(--plum); border-bottom-color: var(--plum); }
.mc-cnt { background: var(--rose-pale); color: var(--plum); font-size: 11px; font-weight: 700; border-radius: 999px; padding: 0 7px; line-height: 17px; }
/* 券卡：左侧权益竖栏 + 右侧信息体；非可用态整体压灰 */
.mc-card { display: flex; padding: 0; overflow: hidden; }
.mc-card.dead .mc-benefit { background: linear-gradient(150deg, var(--gray), var(--gray-light)); }
.mc-benefit { flex: none; width: 112px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; padding: 14px 8px; text-align: center; color: #fff; background: linear-gradient(150deg, var(--plum-dark), var(--plum)); }
.mc-benefit b { font-family: var(--font-title); font-size: 17px; line-height: 1.15; }
.mc-benefit small { font-size: 10px; opacity: .85; }
.mc-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 7px; padding: 13px 15px; border-left: 2px dashed rgba(138, 74, 99, .28); }
.mc-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
.mc-name { font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mc-meta { font-size: 12.5px; color: var(--gray); }
.mc-foot { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 2px; }
/* 券码 chip：虚线框 + 等宽字体，点击复制 */
.mc-code { display: inline-flex; align-items: center; gap: 8px; border: 1.5px dashed rgba(138, 74, 99, .45); background: var(--rose-pale); border-radius: 8px; padding: 5px 10px; cursor: pointer; font-family: inherit; }
.mc-code b { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 13px; letter-spacing: .5px; color: var(--plum); }
.mc-code span { font-size: 11px; color: var(--gray); }
.mc-code:hover { border-color: var(--plum); }
.mc-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-left: auto; }
.mc-used { font-size: 12px; color: var(--gray); }
.mc-order { font-size: 12.5px; color: var(--plum); font-weight: 600; }
.mc-order:hover { text-decoration: underline; }
@media (max-width: 480px) {
  .mc-benefit { width: 92px; }
  .mc-benefit b { font-size: 15px; }
  .mc-actions { margin-left: 0; }
}
</style>
