<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { i18n } from '../i18n'
import { useUiStore } from '../stores/ui'
import { useCartStore } from '../stores/cart'
import { useAuthStore } from '../stores/auth'
import GmIcon from '../components/GmIcon.vue'
import CartDrawer from '../components/CartDrawer.vue'
import SearchModal from '../components/SearchModal.vue'
import ChatWidget from '../components/ChatWidget.vue'
import CookieConsent from '../components/CookieConsent.vue'
import MarketingPopups from '../components/MarketingPopups.vue'

const ui = useUiStore()
const cart = useCartStore()
const auth = useAuthStore()

const year = new Date().getFullYear()
const ANN = ['announce.a', 'announce.b', 'announce.c']
const annIdx = ref(0)
let annTimer = null
function startAnn() {
  annTimer = setInterval(() => { annIdx.value = (annIdx.value + 1) % ANN.length }, 4000)
}

const NAV = [
  ['/store?sort=new', 'nav.new'],
  ['/store?cat=nails', 'nav.nails'],
  ['/store?cat=lashes', 'nav.lashes'],
  ['/collabs', 'nav.collabs'],
  ['/bundles', 'nav.bundles'],
  ['/sale', 'nav.sale'],
]
const zh = computed(() => i18n.lang === 'zh')
const MEGA_SHAPE = [['almond', 'Short Almond', '短杏仁'], ['square', 'Square', '方形'], ['stiletto', 'Stiletto', '尖头'], ['coffin', 'Coffin', '棺形']]
const MEGA_STYLE = [['french', 'French', '法式'], ['glitter', 'Glitter', '亮片'], ['solid', 'Solid', '纯色'], ['art', 'Nail Art', '美甲艺术']]
const MEGA_PICKS = [
  { title: 'Bare Gems', titleZh: '裸钻', price: 15.99, img: 'https://placehold.co/120x120/F5D8DA/6D2E46?text=Bare+Gems' },
  { title: 'Cherry Bomb', titleZh: '樱桃炸弹', price: 13.99, img: 'https://placehold.co/120x120/E8C5D8/552338?text=Cherry' },
]

const showBackTop = ref(false)
function onScroll() { showBackTop.value = window.scrollY > 400 }
function backTop() { window.scrollTo({ top: 0, behavior: 'smooth' }) }
function openConsent() { window.dispatchEvent(new CustomEvent('gm:open-consent')) }

onMounted(() => {
  startAnn()
  window.addEventListener('scroll', onScroll, { passive: true })
})
onUnmounted(() => {
  clearInterval(annTimer)
  window.removeEventListener('scroll', onScroll)
})
</script>

<template>
  <div class="announce">
    <span>{{ i18n.t(ANN[annIdx]) }}</span>
  </div>

  <header class="header">
    <div class="container header-inner">
      <button class="icon-btn mobile-only" :aria-label="i18n.t('aria.menu')" style="margin-left:-8px" @click="ui.openMnav()">
        <GmIcon name="menu" />
      </button>
      <router-link class="logo" to="/">GLOW<span>MAG</span></router-link>
      <nav class="nav">
        <template v-for="[href, key] in NAV" :key="key">
          <span v-if="key === 'nav.nails'" class="nav-item">
            <router-link :to="href">{{ i18n.t(key) }}</router-link>
            <div class="mega">
              <div class="mega-col">
                <h5>{{ zh ? '按甲型选购' : 'Shop by Shape' }}</h5>
                <router-link v-for="[v, en, cn] in MEGA_SHAPE" :key="v" :to="`/store?cat=nails&shape=${v}`">{{ zh ? cn : en }}</router-link>
              </div>
              <div class="mega-col">
                <h5>{{ zh ? '按风格选购' : 'Shop by Style' }}</h5>
                <router-link v-for="[v, en, cn] in MEGA_STYLE" :key="v" :to="`/store?cat=nails&style=${v}`">{{ zh ? cn : en }}</router-link>
              </div>
              <div class="mega-col">
                <h5>{{ zh ? '编辑精选' : "Editors' Picks" }}</h5>
                <router-link v-for="p in MEGA_PICKS" :key="p.title" class="mega-card" to="/store">
                  <img :src="p.img" :alt="p.title">
                  <span><b>{{ zh ? p.titleZh : p.title }}</b><i>${{ p.price.toFixed(2) }}</i></span>
                </router-link>
              </div>
              <router-link class="mega-promo" to="/sale">{{ zh ? '季末特惠 · 最高 75 折 →' : 'END OF SEASON · Up to 25% off →' }}</router-link>
            </div>
          </span>
          <span v-else-if="key === 'nav.lashes'" class="nav-item">
            <router-link :to="href">{{ i18n.t(key) }}</router-link>
            <div class="mega mega-2">
              <div class="mega-col">
                <h5>{{ zh ? '选购睫毛' : 'Shop Lashes' }}</h5>
                <router-link to="/store?cat=lashes">{{ zh ? '全部磁吸睫毛' : 'All Magnetic Lashes' }}</router-link>
                <router-link to="/store?cat=lashes">{{ zh ? '维纳斯猫眼' : 'Venus Cat-Eye' }}</router-link>
                <router-link to="/how-it-works">{{ zh ? '5 秒佩戴教程' : 'How to apply in 5s' }}</router-link>
              </div>
              <router-link class="mega-promo mega-promo-card" to="/bundles">
                <b>{{ zh ? '组合优惠 · 最高省 20%' : 'Bundle & save up to 20%' }}</b>
                <span>{{ zh ? '去搭配 →' : 'Shop bundles →' }}</span>
              </router-link>
            </div>
          </span>
          <router-link v-else :to="href" :class="{ sale: key === 'nav.sale' }">{{ i18n.t(key) }}</router-link>
        </template>
      </nav>
      <div class="header-actions">
        <button class="lang-switch" :aria-label="i18n.t('aria.lang')" @click="i18n.toggle()">
          <span :class="{ on: i18n.lang === 'en' }">EN</span><i>/</i><span :class="{ on: i18n.lang === 'zh' }">中</span>
        </button>
        <button class="icon-btn" :aria-label="i18n.t('aria.search')" @click="ui.openSearch()"><GmIcon name="search" /></button>
        <router-link class="icon-btn" to="/account" :aria-label="i18n.t('aria.account')"><GmIcon name="user" /></router-link>
        <button class="icon-btn" :aria-label="i18n.t('aria.cart')" @click="ui.openCart()">
          <GmIcon name="cart" />
          <span class="cart-badge" :style="{ display: cart.count ? 'flex' : 'none' }">{{ cart.count }}</span>
        </button>
      </div>
    </div>
  </header>

  <main>
    <router-view />
  </main>

  <footer class="footer">
    <div class="container">
      <div class="footer-grid">
        <div>
          <div class="logo" style="color:#fff;font-size:24px;margin-bottom:14px">GLOW<span style="color:var(--rose)">MAG</span></div>
          <p style="font-size:13px;color:rgba(255,255,255,.7);max-width:280px">{{ i18n.t('footer.tag') }}</p>
          <div style="display:flex;gap:16px;margin-top:18px">
            <a v-for="s in ['tiktok', 'instagram', 'youtube', 'pinterest']" :key="s" href="javascript:void(0)"
               :aria-label="i18n.t('aria.' + s)" style="color:rgba(255,255,255,.75)" @click.prevent="ui.toast('Social link (demo) 💅')">
              <GmIcon :name="s" :size="22" />
            </a>
          </div>
        </div>
        <div>
          <h4>{{ i18n.t('footer.shop') }}</h4>
          <div class="footer-links">
            <router-link to="/store">{{ i18n.t('footer.all') }}</router-link>
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
            <router-link to="/rewards">{{ i18n.t('footer.rewards') }}</router-link>
            <router-link to="/subscribe">{{ i18n.t('footer.club') }}</router-link>
            <router-link to="/privacy">{{ i18n.t('footer.privacy') }}</router-link>
            <router-link to="/terms">{{ i18n.t('footer.terms') }}</router-link>
          </div>
        </div>
      </div>
      <div class="footer-bottom">
        <div>
          <span>© {{ year }} GLOWMAG. {{ i18n.t('footer.rights') }}</span>
          <div style="margin-top:6px;display:flex;gap:14px;font-size:12px">
            <router-link to="/privacy#ccpa" style="font-size:12px">{{ i18n.t('footer.dns') }}</router-link>
            <router-link to="/unsubscribe" style="font-size:12px">{{ i18n.t('footer.unsub') }}</router-link>
            <a href="javascript:void(0)" style="font-size:12px" @click.prevent="openConsent">{{ i18n.t('footer.cookie') }}</a>
          </div>
        </div>
        <div class="pay-icons"><span>VISA</span><span>MC</span><span>AMEX</span><span>PAYPAL</span><span>KLARNA</span><span>APPLE PAY</span></div>
      </div>
    </div>
  </footer>

  <nav class="tabbar" :aria-label="i18n.t('aria.mobile')">
    <router-link to="/store"><GmIcon name="bag" :size="22" /><span>{{ i18n.t('tab.shop') }}</span></router-link>
    <a href="javascript:void(0)" @click.prevent="ui.openSearch()"><GmIcon name="search" :size="22" /><span>{{ i18n.t('tab.search') }}</span></a>
    <router-link to="/account/wishlist"><GmIcon name="heart" :size="22" /><span>{{ i18n.t('tab.wishlist') }}</span></router-link>
    <a href="javascript:void(0)" @click.prevent="ui.openCart()">
      <GmIcon name="cart" :size="22" /><span class="cart-badge" :style="{ display: cart.count ? 'flex' : 'none' }">{{ cart.count }}</span>
      <span>{{ i18n.t('tab.cart') }}</span>
    </a>
    <router-link to="/account"><GmIcon name="user" :size="22" /><span>{{ i18n.t('tab.account') }}</span></router-link>
  </nav>

  <button class="back-top" :class="{ show: showBackTop }" aria-label="Back to top" @click="backTop">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg>
  </button>

  <div class="overlay" :class="{ open: ui.mnavOpen }" @click="ui.closeMnav()"></div>
  <aside class="mnav" :class="{ open: ui.mnavOpen }" :aria-label="i18n.t('aria.menuDrawer')">
    <div class="drawer-head">{{ i18n.t('nav.browse') }} <button style="font-size:22px" @click="ui.closeMnav()">×</button></div>
    <nav class="mnav-links">
      <router-link v-for="[href, key] in NAV" :key="key" :to="href" @click="ui.closeMnav()">{{ i18n.t(key) }}</router-link>
      <div class="sep"></div>
      <router-link to="/gallery" @click="ui.closeMnav()">{{ i18n.t('footer.gallery') }}</router-link>
      <router-link to="/size-guide" @click="ui.closeMnav()">📐 {{ i18n.t('footer.size') }}</router-link>
      <router-link to="/how-it-works" @click="ui.closeMnav()">💅 {{ i18n.t('footer.howto') }}</router-link>
      <router-link to="/track" @click="ui.closeMnav()">🚚 {{ i18n.t('footer.track') }}</router-link>
      <router-link to="/refer" @click="ui.closeMnav()">🎁 {{ i18n.t('footer.refer') }}</router-link>
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
</style>
