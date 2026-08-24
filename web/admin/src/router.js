import { createRouter, createWebHistory } from 'vue-router'
import { useSessionStore } from './stores/session'
import { firstAllowedPath } from './constants/nav'

const router = createRouter({
  history: createWebHistory('/admin/'),
  scrollBehavior: (to, from, savedPosition) => {
    if (to.path === from.path) return false
    return savedPosition || { top: 0 }
  },
  routes: [
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { public: true, title: '登录' } },
    {
      path: '/',
      component: () => import('./layouts/AdminLayout.vue'),
      children: [
        { path: '', name: 'dashboard', component: () => import('./views/DashboardView.vue'), meta: { title: '数据看板', perm: 'dashboard:read' } },
        { path: 'orders', name: 'orders', component: () => import('./views/OrdersView.vue'), meta: { title: '订单管理', perm: 'trade:read' } },
        { path: 'order-detail', name: 'order-detail', component: () => import('./views/OrderDetailView.vue'), meta: { title: '订单详情', crumbs: ['订单管理', '订单详情'], perm: 'trade:read' } },
        { path: 'returns', name: 'returns', component: () => import('./views/ReturnsView.vue'), meta: { title: '退换货', perm: 'rma:read' } },
        { path: 'tickets', name: 'tickets', component: () => import('./views/TicketsView.vue'), meta: { title: '工单', perm: 'ticket:manage' } },
        { path: 'chat', name: 'chat', component: () => import('./views/ChatView.vue'), meta: { title: '在线客服', perm: 'chat:manage' } },
        { path: 'products', name: 'products', component: () => import('./views/ProductsView.vue'), meta: { title: '商品管理', perm: 'catalog:read' } },
        { path: 'product-edit', name: 'product-edit', component: () => import('./views/ProductEditView.vue'), meta: { title: '商品编辑', crumbs: ['商品管理', '商品编辑'], perm: 'catalog:read' } },
        { path: 'inventory', name: 'inventory', component: () => import('./views/InventoryView.vue'), meta: { title: '库存中心', perm: 'stock:read' } },
        { path: 'marketing', name: 'marketing', component: () => import('./views/MarketingView.vue'), meta: { title: '营销工具', perm: 'promo:manage' } },
        { path: 'content', name: 'content', component: () => import('./views/ContentView.vue'), meta: { title: '内容管理', perm: 'content:manage' } },
        { path: 'members', name: 'members', component: () => import('./views/MembersView.vue'), meta: { title: '会员', perm: 'member:read' } },
        { path: 'subscriptions', name: 'subscriptions', component: () => import('./views/SubscriptionsView.vue'), meta: { title: '订阅管理', perm: 'member:read' } },
        { path: 'queues', name: 'queues', component: () => import('./views/OpsQueuesView.vue'), meta: { title: '运营队列', perm: 'ops:queue' } },
        { path: 'logs', name: 'logs', component: () => import('./views/LogsView.vue'), meta: { title: '操作日志', perm: 'log:read' } },
        { path: 'settings', name: 'settings', component: () => import('./views/SettingsView.vue'), meta: { title: '系统设置', perm: 'settings:manage' } },
        { path: '403', name: 'forbidden', component: () => import('./views/ForbiddenView.vue'), meta: { title: '无权访问' } },
      ],
    },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('./views/NotFoundView.vue'), meta: { public: true, title: '页面不存在' } },
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
  '/admin-logs.html': '/logs',
  '/admin-settings.html': '/settings',
}

router.beforeEach((to) => {
  const legacy = LEGACY[to.path]
  if (legacy) return { path: legacy, query: to.query }
  const session = useSessionStore()
  if (!to.meta.public && !session.user) {
    return { path: '/login', query: { next: to.fullPath } }
  }
  /* 声明式权限：meta.perm 未命中 → 无权面。目标为首页（登录默认落地）时
   * 重定向到第一个有权限的菜单（客服→工单 / 美甲师→在线客服），
   * 其余直输 URL 落 403 页说明（后端 require_perm 同规则兜底） */
  if (to.meta.perm && session.user && !session.hasPerm(to.meta.perm)) {
    if (to.path === '/') return { path: firstAllowedPath(session.hasPerm) }
    return { path: '/403' }
  }
  return true
})

/* 浏览器标签标题 */
router.afterEach((to) => {
  document.title = to.meta.title ? 'GLOWMAG 后台 · ' + to.meta.title : 'GLOWMAG 后台'
})

export default router
