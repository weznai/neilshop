import { createRouter, createWebHistory } from 'vue-router'
import { useSessionStore } from './stores/session'

const router = createRouter({
  history: createWebHistory('/admin/'),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { public: true } },
    {
      path: '/',
      component: () => import('./layouts/AdminLayout.vue'),
      children: [
        { path: '', name: 'dashboard', component: () => import('./views/DashboardView.vue') },
        { path: 'orders', name: 'orders', component: () => import('./views/OrdersView.vue') },
        { path: 'order-detail', name: 'order-detail', component: () => import('./views/OrderDetailView.vue') },
        { path: 'returns', name: 'returns', component: () => import('./views/ReturnsView.vue') },
        { path: 'tickets', name: 'tickets', component: () => import('./views/TicketsView.vue') },
        { path: 'products', name: 'products', component: () => import('./views/ProductsView.vue') },
        { path: 'product-edit', name: 'product-edit', component: () => import('./views/ProductEditView.vue') },
        { path: 'inventory', name: 'inventory', component: () => import('./views/InventoryView.vue') },
        { path: 'marketing', name: 'marketing', component: () => import('./views/MarketingView.vue') },
        { path: 'content', name: 'content', component: () => import('./views/ContentView.vue') },
        { path: 'members', name: 'members', component: () => import('./views/MembersView.vue') },
        { path: 'logs', name: 'logs', component: () => import('./views/LogsView.vue') },
        { path: 'settings', name: 'settings', component: () => import('./views/SettingsView.vue') },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

/* 旧静态页 URL → SPA 路由 */
const LEGACY = {
  '/admin.html': '/',
  '/admin-login.html': '/login',
  '/admin-orders.html': '/orders',
  '/admin-order-detail.html': '/order-detail',
  '/admin-returns.html': '/returns',
  '/admin-tickets.html': '/tickets',
  '/admin-products.html': '/products',
  '/admin-product-edit.html': '/product-edit',
  '/admin-inventory.html': '/inventory',
  '/admin-marketing.html': '/marketing',
  '/admin-content.html': '/content',
  '/admin-members.html': '/members',
  '/admin-settings.html': '/settings',
}

router.beforeEach((to) => {
  const legacy = LEGACY[to.path]
  if (legacy) return { path: legacy, query: to.query }
  const session = useSessionStore()
  if (!to.meta.public && !session.user) {
    return { path: '/login', query: { next: to.fullPath } }
  }
  return true
})

export default router
