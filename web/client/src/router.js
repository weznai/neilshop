import { createRouter, createWebHistory } from 'vue-router'
import StoreLayout from './layouts/StoreLayout.vue'
import { applyRouteSeo } from './composables/seo'
import { useAuthStore } from './stores/auth'

/* 旧静态站 URL（*.html）→ SPA 路由重定向（外链/收藏夹兼容） */
const LEGACY = {
  '/index.html': '/',
  '/store.html': '/store',
  '/product.html': '/product',
  '/cart.html': '/cart',
  '/checkout.html': '/checkout',
  '/success.html': '/success',
  '/login.html': '/login',
  '/register.html': '/register',
  '/account.html': '/account',
  '/account-orders.html': '/account/orders',
  '/account-order-detail.html': '/account/orders/detail',
  '/account-returns.html': '/account/returns',
  '/account-points.html': '/account/points',
  '/account-address.html': '/account/address',
  '/account-wishlist.html': '/account/wishlist',
  '/account-settings.html': '/account/settings',
  '/search.html': '/search',
  '/track.html': '/track',
  '/blog.html': '/blog',
  '/blog-post.html': '/blog/post',
  '/gallery.html': '/gallery',
  '/refer.html': '/refer',
  '/rewards.html': '/rewards',
  '/subscribe.html': '/subscribe',
  '/gift-cards.html': '/gift-cards',
  '/bundles.html': '/bundles',
  '/sale.html': '/sale',
  '/collabs.html': '/collabs',
  '/about.html': '/about',
  '/contact.html': '/contact',
  '/faq.html': '/faq',
  '/how-it-works.html': '/how-it-works',
  '/size-guide.html': '/size-guide',
  '/privacy.html': '/privacy',
  '/terms.html': '/terms',
  '/shipping-policy.html': '/shipping-policy',
  '/returns-policy.html': '/returns-policy',
  '/unsubscribe.html': '/unsubscribe',
}

const BASE_TITLE = 'GLOWMAG · Press-On Nails & Magnetic Lashes'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, from, saved) {
    /* 返回（含详情↔列表）优先恢复滚动位置；锚点定位留出吸顶高度 */
    if (saved) return saved
    if (to.hash) return { el: to.hash, top: 84 }
    /* 同页仅 query 变化（筛选/排序/分页）：保持当前滚动位置，不跳顶；
       例外：商品/文章详情切换（同 path 换 id/slug）需回顶（视图内亦有切换逻辑，此处仅保证不冲突） */
    if (to.path === from.path) {
      const detailSwap = (to.name === 'product' || to.name === 'blog-post')
        && (to.query.id !== from.query.id || to.query.slug !== from.query.slug)
      return detailSwap ? { top: 0 } : false
    }
    return { top: 0 }
  },
  routes: [
    {
      path: '/',
      component: StoreLayout,
      children: [
        { path: '', name: 'home', component: () => import('./views/HomeView.vue'), meta: { title: '' } },
        { path: 'store', name: 'store', component: () => import('./views/StoreView.vue'), meta: { title: 'Shop All' } },
        { path: 'collections', name: 'collections', component: () => import('./views/CollectionsView.vue'), meta: { title: 'Collections' } },
        { path: 'collection/:slug', name: 'collection', component: () => import('./views/CollectionView.vue'), meta: { title: 'Collection' } },
        { path: 'product', name: 'product', component: () => import('./views/ProductView.vue'), meta: { title: 'Product Details' } },
        { path: 'cart', name: 'cart', component: () => import('./views/CartView.vue'), meta: { title: 'Your Cart', noindex: true } },
        { path: 'checkout', name: 'checkout', component: () => import('./views/CheckoutView.vue'), meta: { title: 'Checkout', noindex: true } },
        { path: 'success', name: 'success', component: () => import('./views/SuccessView.vue'), meta: { title: 'Order Confirmed', noindex: true } },
        { path: 'login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { title: 'Sign In', noindex: true } },
        { path: 'register', name: 'register', component: () => import('./views/RegisterView.vue'), meta: { title: 'Create Account', noindex: true } },
        { path: 'reset-password', name: 'reset-password', component: () => import('./views/ResetPasswordView.vue'), meta: { title: 'Reset Password', noindex: true } },
        { path: 'account', component: () => import('./views/account/AccountShell.vue'), meta: { requiresAuth: true, title: 'My Account', noindex: true }, children: [
          { path: '', name: 'account', component: () => import('./views/account/AccountView.vue') },
          { path: 'orders', name: 'account-orders', component: () => import('./views/account/OrdersView.vue'), meta: { title: 'My Orders' } },
          { path: 'orders/detail', name: 'account-order-detail', component: () => import('./views/account/OrderDetailView.vue'), meta: { title: 'Order Details' } },
          { path: 'returns', name: 'account-returns', component: () => import('./views/account/ReturnsView.vue'), meta: { title: 'Returns & Exchanges' } },
          { path: 'points', name: 'account-points', component: () => import('./views/account/PointsView.vue'), meta: { title: 'Glow Points' } },
          { path: 'address', name: 'account-address', component: () => import('./views/account/AddressView.vue'), meta: { title: 'Address Book' } },
          { path: 'wishlist', name: 'account-wishlist', component: () => import('./views/account/WishlistView.vue'), meta: { title: 'Wishlist' } },
          { path: 'settings', name: 'account-settings', component: () => import('./views/account/SettingsView.vue'), meta: { title: 'Settings' } },
        ] },
        { path: 'search', name: 'search', component: () => import('./views/SearchView.vue'), meta: { title: 'Search', noindex: true } },
        { path: 'track', name: 'track', component: () => import('./views/TrackView.vue'), meta: { title: 'Track Order', noindex: true } },
        { path: 'blog', name: 'blog', component: () => import('./views/BlogView.vue'), meta: { title: 'Blog' } },
        { path: 'blog/post', name: 'blog-post', component: () => import('./views/BlogPostView.vue'), meta: { title: 'Blog' } },
        { path: 'gallery', name: 'gallery', component: () => import('./views/GalleryView.vue'), meta: { title: '#GLOWMAGGlam Gallery' } },
        { path: 'refer', name: 'refer', component: () => import('./views/ReferView.vue'), meta: { title: 'Refer a Friend' } },
        { path: 'rewards', name: 'rewards', component: () => import('./views/RewardsView.vue'), meta: { title: 'Glow Rewards' } },
        { path: 'subscribe', name: 'subscribe', component: () => import('./views/SubscribeView.vue'), meta: { title: 'Nail Club' } },
        { path: 'gift-cards', name: 'gift-cards', component: () => import('./views/GiftCardsView.vue'), meta: { title: 'Gift Cards' } },
        { path: 'bundles', name: 'bundles', component: () => import('./views/BundlesView.vue'), meta: { title: 'Bundles & Save' } },
        { path: 'sale', name: 'sale', component: () => import('./views/SaleView.vue'), meta: { title: 'Sale' } },
        { path: 'collabs', name: 'collabs', component: () => import('./views/CollabsView.vue'), meta: { title: 'Collabs' } },
        { path: 'about', name: 'about', component: () => import('./views/AboutView.vue'), meta: { title: 'Our Story' } },
        { path: 'contact', name: 'contact', component: () => import('./views/ContactView.vue'), meta: { title: 'Contact Us' } },
        { path: 'faq', name: 'faq', component: () => import('./views/FaqView.vue'), meta: { title: 'FAQ' } },
        { path: 'how-it-works', name: 'how-it-works', component: () => import('./views/HowItWorksView.vue'), meta: { title: 'How It Works' } },
        { path: 'size-guide', name: 'size-guide', component: () => import('./views/SizeGuideView.vue'), meta: { title: 'Size Guide' } },
        { path: 'privacy', name: 'privacy', component: () => import('./views/PrivacyView.vue'), meta: { title: 'Privacy Policy' } },
        { path: 'terms', name: 'terms', component: () => import('./views/TermsView.vue'), meta: { title: 'Terms of Service' } },
        { path: 'shipping-policy', name: 'shipping-policy', component: () => import('./views/ShippingPolicyView.vue'), meta: { title: 'Shipping Policy' } },
        { path: 'returns-policy', name: 'returns-policy', component: () => import('./views/ReturnsPolicyView.vue'), meta: { title: 'Returns & Exchange Policy' } },
        { path: 'unsubscribe', name: 'unsubscribe', component: () => import('./views/UnsubscribeView.vue'), meta: { title: 'Email Preferences', noindex: true } },
        { path: ':pathMatch(.*)*', name: 'not-found', component: () => import('./views/NotFoundView.vue'), meta: { title: 'Page Not Found', noindex: true } },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const legacy = LEGACY[to.path]
  if (legacy) return { path: legacy, query: to.query, hash: to.hash }
  /* 需登录路由集中守卫（meta 沿父路由继承）：优先 pinia auth store（router 在 pinia 之后安装），
     gm_user 本地缓存仅作 store 异常时的回退 */
  if (to.meta.requiresAuth) {
    let logged = false
    try { logged = !!useAuthStore().isLoggedIn } catch (_) {
      try { logged = !!localStorage.getItem('gm_user') } catch (__) { logged = false }
    }
    if (!logged) return { path: '/login', query: { next: to.fullPath } }
  }
  return true
})

/* 页面 title 动态化（view 文件禁改，标题统一收口在路由表）
   + SEO 路由级兜底（og/twitter/canonical/首页 JSON-LD）；页面级动态数据经 gm:seo 事件覆盖，见 composables/seo.js */
router.afterEach((to) => {
  document.title = to.meta.title ? to.meta.title + ' · GLOWMAG' : BASE_TITLE
  applyRouteSeo(to)
  /* UTM 归因捕获：任意路由 query 带 utm_*（非空）即写入 gm_utm（7 天有效，新值覆盖旧值）；
     CheckoutView utmOf 优先读路由 query，为空回落此存储 */
  const utm = {}
  for (const k of ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']) {
    const v = to.query[k]
    if (v) utm[k] = String(v)
  }
  if (Object.keys(utm).length) {
    try { localStorage.setItem('gm_utm', JSON.stringify({ values: utm, ts: Date.now() })) } catch (_) { /* 隐私模式 */ }
  }
})

export default router
