/* 后台角色与菜单权限常量（UserRole，以 server/app/core/enums.py 真值为准）：
 * 1=客服（工单/在线客服/订单只读） 2=运营（业务面） 3=仓库（发货/库存/商品只读）
 * 4=美甲师（仅在线客服） 9=超管（全部）。
 * 权限点与 server/app/core/permissions.py 一一对应，经 /api/admin/session/me 的
 * user.permissions 实时下发（改动角色能力只改后端矩阵，前端自动跟随）。 */

/* 角色文案：AdminLayout 侧栏徽标与 SettingsView 管理员表格共用 */
export const ROLE_LABEL = { 1: '客服', 2: '运营', 3: '仓库', 4: '美甲师', 9: '超管' }

/* 角色徽标配色（tag 色系）：超管红 / 仓库蓝 / 运营·美甲师中性 / 客服灰 */
export const ROLE_BADGE = { 1: 'tag-done', 2: 'tag-pending', 3: 'tag-ship', 4: 'tag-done', 9: 'tag-error' }

/* 角色权限口径一句话（SettingsView 建号表单提示，与后端矩阵同步维护） */
export const ROLE_SCOPE_DESC = {
  1: '工单与在线客服；订单/退货/会员只读',
  2: '订单/退款/商品/库存/营销/内容/会员/队列/设置（白名单项）',
  3: '发货与库存调整；退货收货；商品只读',
  9: '全部权限，含管理员账号、支付凭据与系统设置全量',
}
