<script>
/* 模块级：编辑精选卡商品详情内存缓存（布局重建不重复请求）；{ok:true,d}|{ok:false}，404 视为下架缓存命中 */
import { req } from '../api/client'
import { CAT_ALIAS } from '../data/catalog'
const _picksCache = {}
function pickDetail(slug, locale) {
  /* 缓存键含 locale：语言切换后重新 hydrate 不命中旧语言缓存 */
  const key = slug + ':' + (locale || 'en')
  if (!_picksCache[key]) {
    _picksCache[key] = req('GET', '/api/catalog/products/' + slug + (locale ? '?locale=' + locale : ''))
      .then((d) => ({ ok: true, d }))
      .catch((e) => {
        if (e && e.status === 404) return { ok: true, d: null }
        delete _picksCache[key]
        return { ok: false }
      })
  }
  return _picksCache[key]
}
</script>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { i18n } from '../i18n'
import { useUiStore } from '../stores/ui'
import { useCartStore } from '../stores/cart'
import { useAuthStore } from '../stores/auth'
import { req, errMessage } from '../api/client'
import GmIcon from '../components/GmIcon.vue'
import CartDrawer from '../components/CartDrawer.vue'
import SearchModal from '../components/SearchModal.vue'
import ChatWidget from '../components/ChatWidget.vue'
import CookieConsent from '../components/CookieConsent.vue'
import MarketingPopups from '../components/MarketingPopups.vue'

const ui = useUiStore()
const cart = useCartStore()
const auth = useAuthStore()
const route = useRoute()

const year = new Date().getFullYear()
const ANN = ['announce.a', 'announce.b', 'announce.c']
const annIdx = ref(0)
let annTimer = null
function startAnn() {
  if (annTimer) return
  annTimer = setInterval(() => { annIdx.value = (annIdx.value + 1) % ANN.length }, 4000)
}
function stopAnn() { clearInterval(annTimer); annTimer = null }
/* 公告栏可关闭：sessionStorage 记忆，本次会话不再显示；标签页隐藏暂停轮播、可见恢复 */
const annDismissed = ref(sessionStorage.getItem('gm_ann_dismissed') === '1')
function dismissAnn() {
  stopAnn()
  annDismissed.value = true
  sessionStorage.setItem('gm_ann_dismissed', '1')
}
function onAnnVis() {
  if (annDismissed.value) return
  if (document.visibilityState === 'hidden') stopAnn()
  else startAnn()
}

/* 导航高亮分类归一化：站内短别名（nails/lashes）与真实 slug（StoreView CAT_ALIAS）等价识别 */
const catSlug = (r) => CAT_ALIAS[r.query.cat] || r.query.cat
const NAV = [
  { href: '/store?sort=new', key: 'nav.new', match: (r) => r.path === '/store' && r.query.sort === 'new' },
  { href: '/store?cat=press-on-nails', key: 'nav.nails', match: (r) => r.path === '/store' && (catSlug(r) === 'press-on-nails' || (!r.query.cat && r.query.sort !== 'new')) },
  { href: '/store?cat=magnetic-lashes', key: 'nav.lashes', match: (r) => r.path === '/store' && catSlug(r) === 'magnetic-lashes' },
  { href: '/collabs', key: 'nav.collabs', match: (r) => r.path === '/collabs' },
  { href: '/bundles', key: 'nav.bundles', match: (r) => r.path === '/bundles' },
  { href: '/sale', key: 'nav.sale', match: (r) => r.path === '/sale' },
]
const zh = computed(() => i18n.lang === 'zh')
const MEGA_SHAPE = [['almond', 'Short Almond', '短杏仁'], ['square', 'Square', '方形'], ['stiletto', 'Stiletto', '尖头'], ['coffin', 'Coffin', '棺形']]
const MEGA_STYLE = [['french', 'French', '法式'], ['glitter', 'Glitter', '亮片'], ['solid', 'Solid', '纯色'], ['art', 'Nail Art', '美甲艺术']]
/* 编辑精选卡链到真实商品（slug 直达 PDP）：挂载时按 slug 拉详情回填标题/价格/图，
   404 或下架隐藏对应卡，请求失败保留硬编码兜底 */
const MEGA_PICKS = ref([
  { slug: 'bare-gems', title: 'Bare Gems', titleZh: '裸钻', price: 15.99, img: 'https://placehold.co/120x120/F5D8DA/6D2E46?text=Bare+Gems', show: true },
  { slug: 'french-kiss', title: 'French Kiss', titleZh: '法式之吻', price: 14.99, img: 'https://placehold.co/120x120/E8C5D8/552338?text=French+Kiss', show: true },
])
const picksShown = computed(() => MEGA_PICKS.value.filter((p) => p.show))
/* 编辑精选卡图加载失败兜底：placehold 占位（dataset 防循环，对齐 HomeView heroFallback） */
const PICK_FALLBACK = 'https://placehold.co/120x120/E8B4B8/552338?text=GLOWMAG'
function pickFallback(e) {
  const img = e.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = PICK_FALLBACK
}
async function hydratePicks() {
  /* zh 用 locale=zh-CN 拉取并同步 titleZh，防中文态精选卡回落英文硬编码译名 */
  const loc = i18n.lang === 'zh' ? 'zh-CN' : ''
  await Promise.all(MEGA_PICKS.value.map(async (p) => {
    const r = await pickDetail(p.slug, loc)
    if (!r.ok) return
    if (!r.d || (r.d.status != null && r.d.status !== 1)) { p.show = false; return }
    p.title = r.d.title
    if (loc === 'zh-CN') p.titleZh = r.d.title
    if (r.d.price_min != null) p.price = r.d.price_min / 100
    if (r.d.hero_image) p.img = r.d.hero_image
  }))
}
watch(() => i18n.lang, hydratePicks)

/* 滚动驱动：顶栏收缩 + 返回顶部（单监听器） */
const showBackTop = ref(false)
const headerScrolled = ref(false)
function onScroll() {
  const y = window.scrollY
  showBackTop.value = y > 400
  headerScrolled.value = y > 8
}
const reduceMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
function backTop() { window.scrollTo({ top: 0, behavior: reduceMotion() ? 'auto' : 'smooth' }) }
function openConsent() { window.dispatchEvent(new CustomEvent('gm:open-consent')) }

/* 全局面包屑：由路由 meta.title 链推导（Home / My Account / My Orders…），首页隐藏；
   product 页不渲染（ProductView 自绘更丰富面包屑，避免堆叠） */
const crumbs = computed(() =>
  route.matched
    .filter((r) => r.meta && r.meta.title && r.path !== '/')
    .map((r) => ({ path: r.path, title: r.meta.title })),
)
/* 自定义面包屑事件通道：CollectionView 等经 window gm:crumbs 上报（detail 为 {path,title}[]，结构同上），
   收到即覆盖默认推导；路由 path 变化自动清除恢复默认 */
const crumbOverride = ref(null)
function onCrumbs(e) { crumbOverride.value = e.detail || null }
watch(() => route.path, () => { crumbOverride.value = null })
const displayCrumbs = computed(() => crumbOverride.value || crumbs.value)

/* 心愿单角标：WishlistView 已把数量写入 gm_wl_count，此处路由切换时同步（登录后访问过心愿单页即有值）；
   ProductView 加入心愿单后广播 gm:wl-changed 即时刷新 */
const wlCount = ref(0)
function syncWl() { wlCount.value = parseInt(localStorage.getItem('gm_wl_count') || '0', 10) || 0 }
watch(() => route.fullPath, syncWl)
function onWlChanged() { syncWl() }

/* 页脚 newsletter（端点存在且游客可用：POST /api/account/newsletter） */
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const newsEmail = ref('')
const newsBusy = ref(false)
async function subscribeNews() {
  const em = newsEmail.value.trim()
  if (!EMAIL_RE.test(em)) { ui.toast(i18n.t('footer.news.err'), 'error'); return }
  newsBusy.value = true
  try {
    await req('POST', '/api/account/newsletter', { email: em, source: 'footer' })
    ui.toast(i18n.t('footer.news.ok'), 'success')
    newsEmail.value = ''
  } catch (e) {
    ui.toast(errMessage(e), 'error')
  } finally { newsBusy.value = false }
}

/* 弹层滚动穿透：任一浮层打开时锁 body 滚动（style.css .gm-locked） */
watch(() => ui.anyOverlay, (v) => document.body.classList.toggle('gm-locked', !!v))

/* tabbar 当前页高亮（.on 复用 style.css 既有规则；Cart 为角标脉冲） */
const tabShop = computed(() => route.path === '/' || route.path === '/store')
const tabSearch = computed(() => route.path === '/search')
const tabWish = computed(() => route.path === '/account/wishlist')
const tabMe = computed(() => route.path.startsWith('/account') && route.path !== '/account/wishlist')

/* 购物车角标一次性脉冲：仅 cart.count 数值变化时触发（瞬时类，对齐 CartView freePop）；静止有货不加持续动画 */
const tabPulse = ref(false)
let tabPulseT = null
watch(() => cart.count, () => {
  clearTimeout(tabPulseT)
  tabPulse.value = false
  tabPulseT = setTimeout(() => {
    tabPulse.value = true
    setTimeout(() => { tabPulse.value = false }, 1700)
  }, 30)
})

onMounted(() => {
  if (!annDismissed.value) startAnn()
  syncWl()
  hydratePicks()
  window.addEventListener('gm:wl-changed', onWlChanged)
  window.addEventListener('gm:crumbs', onCrumbs)
  document.addEventListener('visibilitychange', onAnnVis)
  window.addEventListener('scroll', onScroll, { passive: true })
})
onUnmounted(() => {
  stopAnn()
  clearTimeout(tabPulseT)
  window.removeEventListener('gm:wl-changed', onWlChanged)
  window.removeEventListener('gm:crumbs', onCrumbs)
  document.removeEventListener('visibilitychange', onAnnVis)
  window.removeEventListener('scroll', onScroll)
})
</script>

<template>
  <div v-if="!annDismissed" class="announce" aria-live="off">
    <!-- 文案含 <b> 强调（本地字典，无注入面）：v-html 渲染，修复 {{}} 转义出字面标签 -->
    <Transition name="ann" mode="out-in"><span :key="annIdx" v-html="i18n.t(ANN[annIdx])"></span></Transition>
    <button class="icon-btn ann-close" :aria-label="zh ? '关闭公告' : 'Dismiss announcement'" @click="dismissAnn">×</button>
  </div>

  <header class="header" :class="{ scrolled: headerScrolled }">
    <div class="container header-inner">
      <button class="icon-btn mobile-only" :aria-label="i18n.t('aria.menu')" style="margin-left:-8px" @click="ui.openMnav()">
        <GmIcon name="menu" />
      </button>
      <router-link class="logo" to="/">GLOW<span>MAG</span></router-link>
      <nav class="nav">
        <template v-for="item in NAV" :key="item.key">
          <span v-if="item.key === 'nav.nails'" class="nav-item">
            <router-link :to="item.href" :class="{ on: item.match(route) }" :aria-current="item.match(route) ? 'page' : null">{{ i18n.t(item.key) }}</router-link>
            <div class="mega">
              <div class="mega-col">
                <h5>{{ zh ? '按甲型选购' : 'Shop by Shape' }}</h5>
                <router-link v-for="[v, en, cn] in MEGA_SHAPE" :key="v" :to="`/store?cat=press-on-nails&shape=${v}`">{{ zh ? cn : en }}</router-link>
              </div>
              <div class="mega-col">
                <h5>{{ zh ? '按风格选购' : 'Shop by Style' }}</h5>
                <router-link v-for="[v, en, cn] in MEGA_STYLE" :key="v" :to="`/store?cat=press-on-nails&style=${v}`">{{ zh ? cn : en }}</router-link>
              </div>
              <div class="mega-col">
                <h5>{{ zh ? '编辑精选' : "Editors' Picks" }}</h5>
                <router-link v-for="p in picksShown" :key="p.slug" class="mega-card" :to="`/product?slug=${p.slug}`">
                  <img :src="p.img" :alt="p.title" @error="pickFallback">
                  <span><b>{{ zh ? p.titleZh : p.title }}</b><i>${{ p.price.toFixed(2) }}</i></span>
                </router-link>
              </div>
              <router-link class="mega-promo" to="/sale">{{ i18n.t('nav.megaPromo') }}</router-link>
            </div>
          </span>
          <span v-else-if="item.key === 'nav.lashes'" class="nav-item">
            <router-link :to="item.href" :class="{ on: item.match(route) }" :aria-current="item.match(route) ? 'page' : null">{{ i18n.t(item.key) }}</router-link>
            <div class="mega mega-2">
              <div class="mega-col">
                <h5>{{ zh ? '选购睫毛' : 'Shop Lashes' }}</h5>
                <router-link to="/store?cat=magnetic-lashes">{{ zh ? '全部磁吸睫毛' : 'All Magnetic Lashes' }}</router-link>
                <router-link to="/store?cat=magnetic-lashes&tag=cat-eye">{{ zh ? '猫眼宝石系列' : 'Cat-Eye Edit' }}</router-link>
                <router-link to="/how-it-works">{{ zh ? '5 秒佩戴教程' : 'How to apply in 5s' }}</router-link>
              </div>
              <router-link class="mega-promo mega-promo-card" to="/bundles">
                <b>{{ zh ? '组合优惠 · 最高省 20%' : 'Bundle & save up to 20%' }}</b>
                <span>{{ zh ? '去搭配 →' : 'Shop bundles →' }}</span>
              </router-link>
            </div>
          </span>
          <router-link v-else :to="item.href" :class="{ sale: item.key === 'nav.sale', on: item.match(route) }" :aria-current="item.match(route) ? 'page' : null">{{ i18n.t(item.key) }}</router-link>
        </template>
      </nav>
      <div class="header-actions">
        <button class="lang-switch" :aria-label="i18n.t('aria.lang')" @click="i18n.toggle()">
          <span :class="{ on: i18n.lang === 'en' }">EN</span><i>/</i><span :class="{ on: i18n.lang === 'zh' }">中</span>
        </button>
        <button class="icon-btn" :aria-label="i18n.t('aria.search')" @click="ui.openSearch()"><GmIcon name="search" /></button>
        <router-link class="icon-btn hd-extra" to="/account/wishlist" :aria-label="i18n.t('aria.wishlist')">
          <GmIcon name="heart" />
          <span v-show="auth.isLoggedIn && wlCount" class="cart-badge">{{ wlCount }}</span>
        </router-link>
        <router-link class="icon-btn hd-extra" to="/account" :aria-label="i18n.t('aria.account')"><GmIcon name="user" /></router-link>
        <button class="icon-btn" :aria-label="i18n.t('aria.cart')" @click="ui.openCart()">
          <GmIcon name="cart" />
          <span v-show="cart.count" class="cart-badge">{{ cart.count > 99 ? '99+' : cart.count }}</span>
        </button>
      </div>
    </div>
  </header>

  <main>
    <nav v-if="route.name !== 'product' && displayCrumbs.length" class="container crumbs" aria-label="Breadcrumb">
      <router-link to="/">{{ i18n.t('crumb.home') }}</router-link>
      <template v-for="(c, ci) in displayCrumbs" :key="c.path">
        <GmIcon class="crumb-sep" name="chevron-right" :size="13" />
        <span v-if="ci === displayCrumbs.length - 1" aria-current="page">{{ c.title }}</span>
        <router-link v-else :to="c.path">{{ c.title }}</router-link>
      </template>
    </nav>
    <router-view v-slot="{ Component }">
      <Transition name="page" mode="out-in">
        <div :key="route.path" class="page-wrap">
          <component :is="Component" />
        </div>
      </Transition>
    </router-view>
  </main>

  <section class="newsletter-band">
    <div class="footer-inner">
      <div class="news-text">
        <span class="news-ico"><GmIcon name="mail" :size="18" /></span>
        <div>
          <h5>{{ i18n.t('footer.news.t') }}</h5>
          <p>{{ i18n.t('footer.news.d') }}</p>
        </div>
      </div>
      <form class="news-form" @submit.prevent="subscribeNews">
        <input v-model="newsEmail" type="email" :placeholder="i18n.t('welcome.ph')" aria-label="Email">
        <button class="btn btn-sm news-btn" type="submit" :disabled="newsBusy">{{ i18n.t('welcome.btn') }}</button>
      </form>
    </div>
  </section>

  <footer class="footer">
    <div class="footer-inner">
      <div class="trust-row">
        <div class="trust-item"><span class="trust-ico"><GmIcon name="truck" :size="16" /></span><b>{{ i18n.t('trust.ship') }}</b></div>
        <div class="trust-item"><span class="trust-ico"><GmIcon name="refresh" :size="16" /></span><b>{{ i18n.t('trust.ret') }}</b></div>
        <div class="trust-item"><span class="trust-ico"><GmIcon name="lock" :size="16" /></span><b>{{ i18n.t('trust.pay') }}</b></div>
        <div class="trust-item"><span class="trust-ico"><GmIcon name="star" :size="16" /></span><b>{{ i18n.t('trust.love') }}</b></div>
      </div>

      <div class="footer-main">
        <div class="footer-brand">
          <div class="logo footer-logo">GLOW<span>MAG</span></div>
          <p class="footer-tagline">{{ i18n.t('footer.tag') }}</p>
          <div class="social-row">
            <button
              v-for="s in ['tiktok', 'instagram', 'youtube', 'pinterest']" :key="s"
              type="button" class="social-btn" :aria-label="i18n.t('aria.' + s)"
              @click="ui.toast('Social link (demo) 💅')"
            >
              <GmIcon :name="s" :size="18" />
            </button>
          </div>
        </div>
        <div class="footer-links-group">
          <div>
            <h4>{{ i18n.t('footer.shop') }}</h4>
            <div class="footer-links">
              <router-link to="/store">{{ i18n.t('footer.all') }}</router-link>
              <router-link to="/collections">{{ i18n.t('footer.collections') }}</router-link>
              <router-link to="/store?sort=new">{{ i18n.t('footer.new') }}</router-link>
              <router-link to="/sale">{{ i18n.t('footer.sale') }}</router-link>
              <router-link to="/gift-cards">{{ i18n.t('footer.gift') }}</router-link>
            </div>
          </div>
          <div>
            <h4>{{ i18n.t('footer.help') }}</h4>
            <div class="footer-links">
              <router-link to="/faq">{{ i18n.t('footer.faq') }}</router-link>
              <router-link to="/size-guide">{{ i18n.t('footer.size') }}</router-link>
              <router-link to="/track">{{ i18n.t('footer.track') }}</router-link>
              <router-link to="/contact">{{ i18n.t('footer.contact') }}</router-link>
              <router-link to="/returns-policy">{{ i18n.t('footer.returns') }}</router-link>
              <router-link to="/shipping-policy">{{ i18n.t('footer.shipping') }}</router-link>
            </div>
          </div>
          <div>
            <h4>{{ i18n.t('footer.company') }}</h4>
            <div class="footer-links">
              <router-link to="/about">{{ i18n.t('footer.story') }}</router-link>
              <router-link to="/blog">{{ i18n.t('footer.blog') }}</router-link>
              <router-link to="/gallery">{{ i18n.t('footer.gallery') }}</router-link>
              <router-link to="/rewards">{{ i18n.t('footer.rewards') }}</router-link>
              <router-link to="/subscribe">{{ i18n.t('footer.club') }}</router-link>
              <router-link to="/privacy">{{ i18n.t('footer.privacy') }}</router-link>
              <router-link to="/terms">{{ i18n.t('footer.terms') }}</router-link>
            </div>
          </div>
        </div>
      </div>

      <div class="footer-bottom">
        <div class="footer-bottom-left">
          <span>© {{ year }} GLOWMAG. {{ i18n.t('footer.rights') }}</span>
          <div class="footer-legal">
            <router-link to="/privacy#ccpa">{{ i18n.t('footer.dns') }}</router-link>
            <router-link to="/unsubscribe">{{ i18n.t('footer.unsub') }}</router-link>
            <button type="button" class="foot-link-mini" @click="openConsent">{{ i18n.t('footer.cookie') }}</button>
          </div>
        </div>
        <div class="pay-icons"><span>VISA</span><span>MC</span><span>AMEX</span><span>PAYPAL</span><span>KLARNA</span><span>APPLE PAY</span></div>
      </div>
    </div>
  </footer>

  <nav class="tabbar" :aria-label="i18n.t('aria.mobile')">
    <router-link to="/store" :class="{ on: tabShop }"><GmIcon name="bag" :size="22" /><span>{{ i18n.t('tab.shop') }}</span></router-link>
    <button type="button" :class="{ on: tabSearch }" @click="ui.openSearch()"><GmIcon name="search" :size="22" /><span>{{ i18n.t('tab.search') }}</span></button>
    <router-link to="/account/wishlist" :class="{ on: tabWish }"><GmIcon name="heart" :size="22" /><span>{{ i18n.t('tab.wishlist') }}</span></router-link>
    <button type="button" :class="{ 'tab-pulse': tabPulse }" @click="ui.openCart()">
      <GmIcon name="cart" :size="22" /><span v-show="cart.count" class="cart-badge">{{ cart.count > 99 ? '99+' : cart.count }}</span>
      <span>{{ i18n.t('tab.cart') }}</span>
    </button>
    <router-link to="/account" :class="{ on: tabMe }"><GmIcon name="user" :size="22" /><span>{{ i18n.t('tab.account') }}</span></router-link>
  </nav>

  <button class="back-top" :class="{ show: showBackTop }" :aria-label="i18n.t('aria.backTop')" @click="backTop">
    <GmIcon name="arrow-up" :size="18" />
  </button>

  <div class="overlay" :class="{ open: ui.mnavOpen }" @click="ui.closeMnav()"></div>
  <aside class="mnav" :class="{ open: ui.mnavOpen }" :aria-label="i18n.t('aria.menuDrawer')">
    <div class="drawer-head">{{ i18n.t('nav.browse') }} <button style="font-size:22px" @click="ui.closeMnav()">×</button></div>
    <nav class="mnav-links">
      <router-link v-for="item in NAV" :key="item.key" :to="item.href" @click="ui.closeMnav()">{{ i18n.t(item.key) }}</router-link>
      <div class="sep"></div>
      <router-link to="/gallery" @click="ui.closeMnav()">{{ i18n.t('footer.gallery') }}</router-link>
      <router-link to="/size-guide" @click="ui.closeMnav()">📐 {{ i18n.t('footer.size') }}</router-link>
      <router-link to="/how-it-works" @click="ui.closeMnav()">💅 {{ i18n.t('footer.howto') }}</router-link>
      <router-link to="/track" @click="ui.closeMnav()">🚚 {{ i18n.t('footer.track') }}</router-link>
      <router-link to="/refer" @click="ui.closeMnav()">🎁 {{ i18n.t('footer.refer') }}</router-link>
      <div class="sep"></div>
      <router-link to="/account/wishlist" @click="ui.closeMnav()">💜 {{ i18n.t('tab.wishlist') }}</router-link>
      <router-link to="/account" @click="ui.closeMnav()">👤 {{ i18n.t('tab.account') }}</router-link>
    </nav>
  </aside>

  <CartDrawer />
  <SearchModal />
  <ChatWidget />
  <CookieConsent />
  <MarketingPopups />
</template>

<style scoped>
.lang-switch{display:inline-flex;align-items:center;gap:2px;height:34px;padding:0 10px;border:1.5px solid var(--gray-light);border-radius:999px;font-size:12px;font-weight:700;color:var(--gray);flex:none}
.lang-switch:hover{border-color:var(--rose)}
.lang-switch .on{color:var(--plum)}
.lang-switch i{opacity:.4;font-style:normal;margin:0 1px}

/* 公告栏轮播淡入淡出（key 切换 Transition；reduced-motion 下全站兜底禁过渡，仅瞬切） */
.ann-enter-active,.ann-leave-active{transition:opacity .2s ease,transform .2s ease}
.ann-enter-from{opacity:0;transform:translateY(6px)}
.ann-leave-to{opacity:0;transform:translateY(-6px)}

/* 公告栏关闭钮：icon-btn 基型 + 深底反白缩小（.announce 已 position:relative，右侧留位防文案压钮） */
.announce{padding-right:44px}
.ann-close{position:absolute;right:8px;top:50%;transform:translateY(-50%);width:26px;height:26px;font-size:16px;line-height:1;color:rgba(255,255,255,.8)}
.ann-close:hover{background:rgba(255,255,255,.18);color:#fff}

/* 页脚社交按钮（原 javascript:void(0) 伪链接 button 化；保留 demo toast） */
.social-btn{display:inline-flex;align-items:center;justify-content:center;background:none;border:none;padding:0;cursor:pointer;color:var(--plum);transition:color .15s,transform .15s ease-out}
.social-btn:hover{color:var(--plum);transform:translateY(-2px)}
.foot-link-mini{background:none;border:none;padding:0;cursor:pointer;font-size:12px;color:inherit;font-family:inherit}
.foot-link-mini:hover{color:var(--plum)}

/* v15 顶栏滚动收缩 + 毛玻璃（sticky 下内容自底部透过半透明底色） */
.header-inner{transition:height .25s ease-out}
.header.scrolled{background:rgba(255,255,255,.86);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);box-shadow:0 6px 24px rgba(31,27,30,.08)}
.header.scrolled .header-inner{height:56px}

/* 移动端顶栏收纳：心愿单/账户由底部 tabbar 承载（功能重复），顶栏只留 语言+搜索+购物车，
   避免小屏 5 按钮+菜单+logo 挤压变形（~440px 需求 vs 375px 屏宽） */
@media (max-width:768px){
  .hd-extra{display:none}
  .header-actions{gap:4px}
}

/* v15 全局面包屑 */
.crumb-sep{stroke:var(--gray);opacity:.7;margin:-2px 2px 0}

/* ===== Footer 样式（浅色主题） ===== */

/* 信任徽章行：白卡片 + 梅紫图标圆 */
.trust-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;padding:20px 0 18px;border-bottom:1px solid rgba(138,74,99,.14)}
.trust-item{display:flex;align-items:center;gap:10px;min-width:0;background:rgba(255,255,255,.92);border:1px solid rgba(138,74,99,.08);border-radius:12px;padding:10px 14px;transition:transform .2s, box-shadow .2s}
.trust-item:hover{transform:translateY(-2px);box-shadow:0 8px 20px rgba(138,74,99,.12)}
.trust-item b{color:var(--plum);font-size:12px;font-weight:600;line-height:1.3}
.trust-ico{width:30px;height:30px;border-radius:50%;background:var(--rose-pale);display:flex;align-items:center;justify-content:center;flex:none;transition:transform .2s}
.trust-item:hover .trust-ico{transform:scale(1.1)}
.trust-ico svg{stroke:var(--plum)}
@media (max-width:768px){
  .trust-row{grid-template-columns:1fr 1fr;gap:8px;padding:14px 0 12px}
  .trust-item{padding:8px 10px;gap:8px;border-radius:10px}
  .trust-item b{font-size:11px}
  .trust-ico{width:26px;height:26px}
}

/* Footer 主内容区 */
.footer-main{display:grid;grid-template-columns:1.5fr 2fr;gap:32px;padding:30px 0 26px;border-bottom:1px solid rgba(138,74,99,.14)}
.footer-logo{color:var(--plum)!important;font-size:21px;margin-bottom:8px;letter-spacing:1px}
.footer-logo span{color:var(--rose)}
.footer-tagline{font-size:12.5px;color:#7D5A64;max-width:250px;line-height:1.55;margin-bottom:0}
.social-row{display:flex;gap:8px;margin-top:16px}
.social-btn{width:34px;height:34px;border-radius:50%;background:#fff;border:1px solid rgba(138,74,99,.12);color:var(--plum);display:flex;align-items:center;justify-content:center;transition:all .2s;cursor:pointer;box-shadow:0 2px 8px rgba(138,74,99,.08)}
.social-btn:hover{background:var(--plum);color:#fff;border-color:var(--plum);transform:translateY(-2px);box-shadow:0 6px 14px rgba(138,74,99,.25)}
.social-btn svg{stroke:currentColor}
.footer-links-group{display:grid;grid-template-columns:repeat(3,1fr);gap:24px}
.footer-links-group h4{font-size:11px;margin-bottom:12px}
.footer-links-group .footer-links{gap:7px}
@media (max-width:1024px){
  .footer-main{grid-template-columns:1fr;gap:24px}
  .footer-links-group{grid-template-columns:repeat(2,1fr);gap:20px}
}
@media (max-width:768px){
  .footer-main{grid-template-columns:1fr;gap:20px;padding:22px 0 18px}
  .footer-links-group{grid-template-columns:1fr;gap:16px}
  .social-row{gap:8px}
  .social-btn{width:36px;height:36px}
}
</style>
