<script setup>
import { onMounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import { req } from '../api/client'
import { i18n } from '../i18n'

const auth = useAuthStore()
const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)
const pts = ref(null)
onMounted(async () => {
  if (auth.isLoggedIn) {
    try { pts.value = await req('GET', '/api/points') } catch (_) { /* */ }
  }
})

/* User.tier：0普通(Glow) 1银(Shimmer, 累计$100+) 2金(Diva, 累计$300+) */
const TIERS = [
  ['Glow', '$0+', '全体会员基础礼遇'],
  ['Shimmer', '$100+', '银卡会员标识 · 优先客服'],
  ['Diva', '$300+', '金卡会员标识 · 专属客服'],
]

/* 规则口径与后端一致（services/points.py）：$1=10 分；100 分=$1；评价 +100；推荐 +1000 */
const EARN_RULES = [
  ['下单消费', '每 $1 +10 分'],
  ['写商品评价', '+100 分'],
  ['推荐好友（注册并首单）', '+1000 分'],
  ['生日月', '积分小礼物'],
]
const SPEND_RULES = [
  ['结账抵扣', '100 分 = $1'],
  ['发放与解冻', '下单所得积分冻结中，订单完成/过退货期后解冻'],
  ['有效期', '部分积分有有效期，账户积分页可见到期提醒'],
]
</script>

<template>
  <section class="section">
    <div class="container">
      <div style="text-align:center;margin-bottom:30px">
        <div style="font-size:46px">⭐</div>
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">Glow Rewards</h1>
        <p style="color:var(--gray)">100 积分 = $1 · 消费越多，等级越高</p>
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
        <div style="font-size:12.5px;color:var(--gray)">你的可用积分</div>
        <b style="font-family:var(--font-title);font-size:36px;color:var(--plum)">{{ (pts.usable || 0).toLocaleString() }} 分</b>
        <div style="font-size:13px;color:var(--gray)">≈ 结账可抵 ${{ ((pts.usable || 0) / 100).toFixed(2) }}</div>
        <div v-if="pts.frozen > 0" style="font-size:12.5px;color:var(--warn);margin-top:4px">另有 {{ pts.frozen.toLocaleString() }} 分冻结中</div>
        <router-link v-if="auth.isLoggedIn" class="btn btn-secondary btn-sm" style="margin-top:10px" to="/account/points">查看明细 →</router-link>
      </div>

      <div class="grid grid-3">
        <div v-for="(t, i) in TIERS" :key="t[0]" class="card" style="padding:20px;text-align:center" :style="{ background: i === (auth.user?.tier || 0) ? 'var(--rose-pale)' : '' }">
          <b style="font-family:var(--font-title);font-size:19px">{{ t[0] }}</b>
          <div style="font-size:12.5px;color:var(--plum);margin:4px 0 8px">累计消费 {{ t[1] }}</div>
          <div style="font-size:12.5px;color:var(--gray)">{{ t[2] }}</div>
          <div v-if="i === (auth.user?.tier || 0)" class="tag tag-paid" style="margin-top:8px">当前等级</div>
        </div>
      </div>

      <div class="grid grid-2" style="margin-top:22px">
        <div class="card" style="padding:20px">
          <h3 style="font-size:15px;margin-bottom:10px">如何赚取</h3>
          <div style="display:grid;gap:8px;font-size:13.5px">
            <div v-for="[a, b] in EARN_RULES" :key="a" style="display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid var(--gray-light);padding-bottom:8px">
              <span>{{ a }}</span><b style="color:var(--plum);text-align:right">{{ b }}</b>
            </div>
          </div>
        </div>
        <div class="card" style="padding:20px">
          <h3 style="font-size:15px;margin-bottom:10px">如何使用</h3>
          <div style="display:grid;gap:8px;font-size:13.5px">
            <div v-for="[a, b] in SPEND_RULES" :key="a" style="display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid var(--gray-light);padding-bottom:8px">
              <span>{{ a }}</span><b style="color:var(--plum);text-align:right;font-weight:600">{{ b }}</b>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
