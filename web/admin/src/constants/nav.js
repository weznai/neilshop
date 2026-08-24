/* 后台导航菜单单一事实源：AdminLayout 侧栏 / router 守卫落地页 / LoginView 登录跳转共用。
 * 每项 [图标key, 名称, 路径, 权限点]；字符串 = 分组小节标题。
 * 权限点与路由 meta.perm 保持一致；无权限菜单自动隐藏（router.beforeEach 同规则拦截直输 URL）。 */
export const MENU = [
  ['dash', '数据看板', '/', 'dashboard:read'],
  '交易',
  ['orders', '订单管理', '/orders', 'trade:read'],
  ['returns', '退货审核', '/returns', 'rma:read'],
  ['tickets', '客服工单', '/tickets', 'ticket:manage'],
  ['chat', '在线客服', '/chat', 'chat:manage'],
  '商品',
  ['products', '商品管理', '/products', 'catalog:read'],
  ['inventory', '库存中心', '/inventory', 'stock:read'],
  '运营',
  ['promo', '营销工具', '/marketing', 'promo:manage'],
  ['content', '内容管理', '/content', 'content:manage'],
  ['members', '会员管理', '/members', 'member:read'],
  ['subs', '订阅管理', '/subscriptions', 'member:read'],
  '系统',
  ['queue', '运营队列', '/queues', 'ops:queue'],
  ['logs', '审计日志', '/logs', 'log:read'],
  ['settings', '系统设置', '/settings', 'settings:manage'],
]

/* 第一个有权限的菜单路径（登录默认落地页 / 无权访问 '/' 时的重定向目标） */
export function firstAllowedPath(hasPerm) {
  for (const it of MENU) {
    if (Array.isArray(it) && hasPerm(it[3])) return it[2]
  }
  return '/403'
}
