<script setup>
/* 账户中心外壳：标题 + 侧栏导航 + 登录守卫 */
import { nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { useUiStore } from '../../stores/ui'
import { useArmConfirm } from '../../composables/useArmConfirm'
import { i18n, tt } from '../../i18n'

const auth = useAuthStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()
const ready = ref(false)
/* [href, [en, zh], icon]（订阅/推荐入口由页脚承载，不占侧栏）
   退换货并入「售后」入口（软化退货曝光：退货/换货/退款记录统一在售后页查看） */
const NAV = [
  ['/account', ['Overview', '总览'], '👤'],
  ['/account/orders', ['Orders', '订单'], '📦'],
  ['/account/returns', ['After-sales', '售后'], '🎧'],
  ['/account/points', ['Glow Points', '积分'], '⭐'],
  ['/account/coupons', ['My Coupons', '我的优惠券'], '🎟️'],
  ['/account/address', ['Address Book', '地址簿'], '📍'],
  ['/account/wishlist', ['Wishlist', '心愿单'], '💜'],
  ['/account/settings', ['Settings', '设置'], '⚙️'],
]
/* User.tier：0普通 1银 2金 → 等级色点（银级用可现银灰，避免 var(--gray-light) 隐身） */
const TIER_DOT = { 0: 'var(--plum)', 1: '#B9B9C8', 2: 'var(--gold)' }

/* 激活态：精确匹配，或子路径（如 /account/orders/detail 高亮 Orders） */
function isActive(href) {
  if (route.path === href) return true
  return href !== '/account' && route.path.startsWith(href + '/')
}

/* 移动端导航为横向滚动 tab 条：active 项自动滚入视野 */
const navEl = ref(null)
function scrollActiveNav() {
  const el = navEl.value && navEl.value.querySelector('a.on')
  if (el && el.scrollIntoView) { try { el.scrollIntoView({ inline: 'center', block: 'nearest' }) } catch (_) { /* 旧浏览器 */ } }
}
watch(() => route.path, () => nextTick(scrollActiveNav))

onMounted(async () => {
  nextTick(scrollActiveNav)
  if (auth.isLoggedIn) {
    /* 401（会话过期）时 store 已清缓存 → 显示登录引导 */
    try { await auth.me() } catch (_) { /* 网络错误保留缓存，视图内自行容错 */ }
  }
  ready.value = true
})

/* 登出两段式确认（useArmConfirm：5s 复位；arm 态红字 + 二段文案） */
const outArm = useArmConfirm()

async function signOut() {
  await auth.logout()
  ui.toast(tt('Signed out', '已退出登录'), 'success')
  router.push('/')
}
</script>

<template>
  <section class="section">
    <div class="container">
      <div v-if="ready && !auth.isLoggedIn" style="text-align:center;padding:60px 0;color:var(--gray)">
        <div style="font-size:44px;margin-bottom:10px">🔐</div>
        <p style="margin-bottom:16px">{{ tt('Sign in to view your account', '登录后查看你的账户') }}</p>
        <router-link class="btn btn-primary" :to="{ path: '/login', query: { next: route.fullPath } }">{{ tt('Sign In', '登录') }}</router-link>
      </div>

      <div v-else class="grid-m-1 acct-grid">
        <aside class="card acct-side">
          <div class="acct-user">
            <b class="acct-user-name">{{ auth.user?.name || auth.user?.email || tt('Account', '账户') }}</b>
            <div class="acct-user-meta">
              <span class="tier-dot" :style="{ background: TIER_DOT[auth.user?.tier || 0] || 'var(--plum)' }" :title="tt('Membership tier', '会员等级')" />
              <span class="acct-user-email">{{ auth.user?.email }}</span>
            </div>
          </div>
          <nav ref="navEl" class="acct-nav">
            <router-link
              v-for="[href, label, ico] in NAV" :key="href" :to="href" :class="{ on: isActive(href) }"
            >{{ ico }} {{ tt(label[0], label[1]) }}</router-link>
            <div class="sep" />
            <button class="acct-out" :class="{ arm: outArm.is('out') }" @click="outArm.hit('out', signOut)">🚪 {{ outArm.is('out') ? tt('Tap again to confirm', '再点一次确认') : tt('Sign out', '退出登录') }}</button>
          </nav>
        </aside>
        <div><router-view /></div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.acct-grid { display: grid; grid-template-columns: 220px 1fr; gap: 28px; align-items: start; }
.acct-side { padding: 16px; position: sticky; top: 84px; }
.acct-user { padding: 4px 8px 12px; border-bottom: 1px solid var(--gray-light); margin-bottom: 10px; }
.acct-user-name { font-size: 14px; }
.acct-user-meta { display: flex; gap: 6px; align-items: center; font-size: 12px; color: var(--gray); margin-top: 2px; }
.tier-dot { width: 8px; height: 8px; border-radius: 50%; flex: none; box-shadow: 0 0 0 2.5px var(--rose-pale); }
.acct-user-email { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.acct-nav { display: grid; gap: 2px; }
.acct-out { display: flex; gap: 10px; align-items: center; padding: 11px 14px; border-radius: 10px; font-size: 14px; font-weight: 500; color: var(--error); background: none; border: none; cursor: pointer; text-align: left; }
.acct-out:hover { background: var(--pale-error); }
@media (max-width: 768px) {
  .acct-grid { grid-template-columns: 1fr; }
  .acct-side { position: static; padding: 12px; }
  /* 用户卡折叠一行 + 导航改横向滚动 tab 条，避免导航堆满首屏 */
  .acct-user { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding: 2px 4px 10px; }
  .acct-user-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
  .acct-nav { display: flex; gap: 6px; overflow-x: auto; flex-wrap: nowrap; scrollbar-width: none; -ms-overflow-style: none; }
  .acct-nav::-webkit-scrollbar { display: none; }
  .acct-nav a { flex: none; white-space: nowrap; padding: 8px 12px; border-radius: 999px; font-size: 13px; }
  .acct-nav .sep { display: none; }
  .acct-out { flex: none; white-space: nowrap; padding: 8px 12px; border-radius: 999px; font-size: 13px; }
}
</style>
