<script setup>
import { onMounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import { req } from '../api/client'
import { i18n, tt } from '../i18n'

const auth = useAuthStore()
const pts = ref(null)
const failed = ref(false)
async function load() {
  failed.value = false
  try { pts.value = await req('GET', '/api/points') } catch (_) { failed.value = true }
}
onMounted(() => {
  if (auth.isLoggedIn) {
    load()
    /* 静默刷新用户概要（tier 以服务端为准，模板响应式跟随 auth.user 更新高亮） */
    auth.me(true).catch(() => {})
  }
})

/* User.tier：0普通(Glow) 1银(Shimmer, 累计$100+) 2金(Diva, 累计$300+)；[en, zh] 双语 */
const TIERS = [
  ['Glow', '$0+', ['All-member base perks', '全体会员基础礼遇']],
  ['Shimmer', '$100+', ['Silver badge · priority support', '银卡会员标识 · 优先客服']],
  ['Diva', '$300+', ['Gold badge · dedicated support', '金卡会员标识 · 专属客服']],
]

/* 规则口径与后端一致（services/points.py）：$1=10 分；100 分=$1；评价 +10；推荐 +1000 */
const EARN_RULES = [
  [['Order spend', '下单消费'], ['+10 pts per $1', '每 $1 +10 分']],
  [['Write a review', '写商品评价'], ['+10 pts', '+10 分']],
  [['Refer a friend (signup + first order)', '推荐好友（注册并首单）'], ['+1000 pts', '+1000 分']],
  [['Birthday month', '生日月'], ['points gift', '积分小礼物']],
]
const SPEND_RULES = [
  [['Checkout discount', '结账抵扣'], ['100 pts = $1', '100 分 = $1']],
  [['Grant & unfreeze', '发放与解冻'], ['Points from orders stay frozen until the order completes / the return window passes', '下单所得积分冻结中，订单完成/过退货期后解冻']],
  [['Validity', '有效期'], ['Some points expire — see expiry reminders on the Points page', '部分积分有有效期，账户积分页可见到期提醒']],
]
</script>

<template>
  <section class="section">
    <div class="container">
      <div style="text-align:center;margin-bottom:30px">
        <div style="font-size:46px">⭐</div>
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">Glow Rewards</h1>
        <p style="color:var(--gray)">{{ tt('100 pts = $1 · spend more, level up', '100 积分 = $1 · 消费越多，等级越高') }}</p>
      </div>

      <!-- 未登录：登录引导卡 -->
      <div v-if="!auth.isLoggedIn" class="card" style="max-width:460px;margin:0 auto 26px;padding:22px;text-align:center">
        <div style="font-size:34px;margin-bottom:8px">🔐</div>
        <b style="font-family:var(--font-title);font-size:19px">{{ tt('Sign in to view your points', '登录查看积分') }}</b>
        <p style="font-size:13px;color:var(--gray);margin:8px 0 14px">
          {{ tt('Your balance, frozen points and expiry reminders are waiting.', '你的积分余额、冻结明细与过期提醒都在账户里。') }}
        </p>
        <router-link class="btn btn-primary" :to="{ path: '/login', query: { next: '/rewards' } }">{{ tt('Sign in / Sign up', '登录 / 注册') }}</router-link>
      </div>

      <div v-if="pts" class="card" style="max-width:460px;margin:0 auto 26px;padding:18px;text-align:center">
        <div style="font-size:12.5px;color:var(--gray)">{{ tt('Your usable points', '你的可用积分') }}</div>
        <b style="font-family:var(--font-title);font-size:36px;color:var(--plum)">{{ tt(`${(pts.usable || 0).toLocaleString()} pts`, `${(pts.usable || 0).toLocaleString()} 分`) }}</b>
        <div style="font-size:13px;color:var(--gray)">{{ tt(`≈ $${((pts.usable || 0) / 100).toFixed(2)} off at checkout`, `≈ 结账可抵 $${((pts.usable || 0) / 100).toFixed(2)}`) }}</div>
        <div v-if="pts.frozen > 0" style="font-size:12.5px;color:var(--warn);margin-top:4px">{{ tt(`+ ${pts.frozen.toLocaleString()} pts frozen`, `另有 ${pts.frozen.toLocaleString()} 分冻结中`) }}</div>
        <router-link v-if="auth.isLoggedIn" class="btn btn-secondary btn-sm" style="margin-top:10px" to="/account/points">{{ tt('View details →', '查看明细 →') }}</router-link>
      </div>

      <div v-else-if="auth.isLoggedIn && failed" class="card" style="max-width:460px;margin:0 auto 26px;padding:18px;text-align:center;color:var(--gray)">
        {{ tt('Could not load your points —', '积分加载失败 ——') }} <a href="javascript:void(0)" style="color:var(--plum)" @click="load">{{ tt('retry', '重试') }}</a>
      </div>

      <div class="grid grid-3">
        <div v-for="(t, i) in TIERS" :key="t[0]" class="card" style="padding:20px;text-align:center" :style="{ background: i === (auth.user?.tier || 0) ? 'var(--rose-pale)' : '' }">
          <b style="font-family:var(--font-title);font-size:19px">{{ t[0] }}</b>
          <div style="font-size:12.5px;color:var(--plum);margin:4px 0 8px">{{ tt('lifetime spend', '累计消费') }} {{ t[1] }}</div>
          <div style="font-size:12.5px;color:var(--gray)">{{ tt(t[2][0], t[2][1]) }}</div>
          <div v-if="i === (auth.user?.tier || 0)" class="tag tag-paid" style="margin-top:8px">{{ tt('Current tier', '当前等级') }}</div>
        </div>
      </div>

      <div class="grid grid-2" style="margin-top:22px">
        <div class="card" style="padding:20px">
          <h3 style="font-size:15px;margin-bottom:10px">{{ tt('How to earn', '如何赚取') }}</h3>
          <div style="display:grid;gap:8px;font-size:13.5px">
            <div v-for="[a, b] in EARN_RULES" :key="a[1]" style="display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid var(--gray-light);padding-bottom:8px">
              <span>{{ tt(a[0], a[1]) }}</span><b style="color:var(--plum);text-align:right">{{ tt(b[0], b[1]) }}</b>
            </div>
          </div>
        </div>
        <div class="card" style="padding:20px">
          <h3 style="font-size:15px;margin-bottom:10px">{{ tt('How to spend', '如何使用') }}</h3>
          <div style="display:grid;gap:8px;font-size:13.5px">
            <div v-for="[a, b] in SPEND_RULES" :key="a[1]" style="display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid var(--gray-light);padding-bottom:8px">
              <span style="flex:none">{{ tt(a[0], a[1]) }}</span><b style="color:var(--plum);text-align:right;font-weight:600">{{ tt(b[0], b[1]) }}</b>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
