import { createRouter, createWebHistory } from 'vue-router'
import { useSessionStore } from './stores/session'

const router = createRouter({
  history: createWebHistory('/admin/'),
  scrollBehavior: (to, from, savedPosition) => savedPosition || { top: 0 },
  routes: [
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { public: true, title: '登录' } },
    {
      path: '/',
      component: () => import('./layouts/AdminLayout.vue'),
      children: [
        { path: '', name: 'dashboard', component: () => import('./views/DashboardView.vue'), meta: { title: '数据看板' } },
        { path: 'orders', name: 'orders', component: () => import('./views/OrdersView.vue'), meta: { title: '订单管理' } },
        { path: 'order-detail', name: 'order-detail', component: () => import('./views/OrderDetailView.vue'), meta: { title: '订单详情' } },
        { path: 'returns', name: 'returns', component: () => import('./views/ReturnsView.vue'), meta: { title: '退换货' } },
        { path: 'tickets', name: 'tickets', component: () => import('./views/TicketsView.vue'), meta: { title: '工单' } },
        { path: 'products', name: 'products', component: () => import('./views/ProductsView.vue'), meta: { title: '商品管理' } },
        { path: 'product-edit', name: 'product-edit', component: () => import('./views/ProductEditView.vue'), meta: { title: '商品编辑' } },
        { path: 'inventory', name: 'inventory', component: () => import('./views/InventoryView.vue'), meta: { title: '库存中心' } },
        { path: 'marketing', name: 'marketing', component: () => import('./views/MarketingView.vue'), meta: { title: '营销工具' } },
        { path: 'content', name: 'content', component: () => import('./views/ContentView.vue'), meta: { title: '内容管理' } },
        { path: 'members', name: 'members', component: () => import('./views/MembersView.vue'), meta: { title: '会员' } },
        { path: 'logs', name: 'logs', component: () => import('./views/LogsView.vue'), meta: { title: '操作日志' } },
        { path: 'settings', name: 'settings', component: () => import('./views/SettingsView.vue'), meta: { title: '系统设置' } },
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

/* 浏览器标签标题 */
router.afterEach((to) => {
  document.title = to.meta.title ? 'GLOWMAG 后台 · ' + to.meta.title : 'GLOWMAG 后台'
})

export default router
