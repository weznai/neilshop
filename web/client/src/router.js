import { createRouter, createWebHistory } from 'vue-router'
import StoreLayout from './layouts/StoreLayout.vue'

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
  '/404.html': '/404',
}

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, from, saved) {
    return saved || { top: 0 }
  },
  routes: [
    {
      path: '/',
      component: StoreLayout,
      children: [
        { path: '', name: 'home', component: () => import('./views/HomeView.vue') },
        { path: 'store', name: 'store', component: () => import('./views/StoreView.vue') },
        { path: 'product', name: 'product', component: () => import('./views/ProductView.vue') },
        { path: 'cart', name: 'cart', component: () => import('./views/CartView.vue') },
        { path: 'checkout', name: 'checkout', component: () => import('./views/CheckoutView.vue') },
        { path: 'success', name: 'success', component: () => import('./views/SuccessView.vue') },
        { path: 'login', name: 'login', component: () => import('./views/LoginView.vue') },
        { path: 'register', name: 'register', component: () => import('./views/RegisterView.vue') },
        { path: 'account', component: () => import('./views/account/AccountShell.vue'), children: [
          { path: '', name: 'account', component: () => import('./views/account/AccountView.vue') },
          { path: 'orders', name: 'account-orders', component: () => import('./views/account/OrdersView.vue') },
          { path: 'orders/detail', name: 'account-order-detail', component: () => import('./views/account/OrderDetailView.vue') },
          { path: 'returns', name: 'account-returns', component: () => import('./views/account/ReturnsView.vue') },
          { path: 'points', name: 'account-points', component: () => import('./views/account/PointsView.vue') },
          { path: 'address', name: 'account-address', component: () => import('./views/account/AddressView.vue') },
          { path: 'wishlist', name: 'account-wishlist', component: () => import('./views/account/WishlistView.vue') },
          { path: 'settings', name: 'account-settings', component: () => import('./views/account/SettingsView.vue') },
        ] },
        { path: 'search', name: 'search', component: () => import('./views/SearchView.vue') },
        { path: 'track', name: 'track', component: () => import('./views/TrackView.vue') },
        { path: 'blog', name: 'blog', component: () => import('./views/BlogView.vue') },
        { path: 'blog/post', name: 'blog-post', component: () => import('./views/BlogPostView.vue') },
        { path: 'gallery', name: 'gallery', component: () => import('./views/GalleryView.vue') },
        { path: 'refer', name: 'refer', component: () => import('./views/ReferView.vue') },
        { path: 'rewards', name: 'rewards', component: () => import('./views/RewardsView.vue') },
        { path: 'subscribe', name: 'subscribe', component: () => import('./views/SubscribeView.vue') },
        { path: 'gift-cards', name: 'gift-cards', component: () => import('./views/GiftCardsView.vue') },
        { path: 'bundles', name: 'bundles', component: () => import('./views/BundlesView.vue') },
        { path: 'sale', name: 'sale', component: () => import('./views/SaleView.vue') },
        { path: 'collabs', name: 'collabs', component: () => import('./views/CollabsView.vue') },
        { path: 'about', name: 'about', component: () => import('./views/AboutView.vue') },
        { path: 'contact', name: 'contact', component: () => import('./views/ContactView.vue') },
        { path: 'faq', name: 'faq', component: () => import('./views/FaqView.vue') },
        { path: 'how-it-works', name: 'how-it-works', component: () => import('./views/HowItWorksView.vue') },
        { path: 'size-guide', name: 'size-guide', component: () => import('./views/SizeGuideView.vue') },
        { path: 'privacy', name: 'privacy', component: () => import('./views/PrivacyView.vue') },
        { path: 'terms', name: 'terms', component: () => import('./views/TermsView.vue') },
        { path: 'shipping-policy', name: 'shipping-policy', component: () => import('./views/ShippingPolicyView.vue') },
        { path: 'returns-policy', name: 'returns-policy', component: () => import('./views/ReturnsPolicyView.vue') },
        { path: 'unsubscribe', name: 'unsubscribe', component: () => import('./views/UnsubscribeView.vue') },
        { path: '404', name: 'not-found', component: () => import('./views/NotFoundView.vue') },
        { path: ':pathMatch(.*)*', redirect: '/404' },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const legacy = LEGACY[to.path]
  if (legacy) return { path: legacy, query: to.query }
  return true
})

export default router
