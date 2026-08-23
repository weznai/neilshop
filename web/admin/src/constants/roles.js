/* 后台角色共享常量（UserRole，以 models/user.py 真值为准）：
 * 1=客服（前台定位，后台登录守卫要求 role>=2 会被拒） 2=运营 3=仓库 4=美甲师 9=超管 */

/* 角色文案：AdminLayout 侧栏徽标与 SettingsView 管理员表格共用 */
export const ROLE_LABEL = { 1: '客服', 2: '运营', 3: '仓库', 4: '美甲师', 9: '超管' }

/* 角色徽标配色（tag 色系）：超管红 / 仓库蓝 / 运营·美甲师中性 / 客服灰 */
export const ROLE_BADGE = { 1: 'tag-done', 2: 'tag-pending', 3: 'tag-ship', 4: 'tag-done', 9: 'tag-error' }
