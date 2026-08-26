/* 后台会话：HttpOnly Cookie gm_admin_token（/api/account/admin/login 下发，仅后台角色）。
 * user.permissions 为后端实时下发的权限点数组（core/permissions.py 矩阵），
 * 路由/菜单/按钮权限统一走 hasPerm，不再前端推断角色数字。 */
import { defineStore } from 'pinia'
import { req } from '../api/client'

function loadCachedUser() {
  try { return JSON.parse(localStorage.getItem('gm_admin_user') || 'null') }
  catch (_) { localStorage.removeItem('gm_admin_user'); return null }
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    user: loadCachedUser(),
  }),
  getters: {
    role: (s) => (s.user && s.user.role) | 0,
    name: (s) => (s.user && s.user.name) || (s.user && s.user.email) || '管理员',
    perms: (s) => (s.user && Array.isArray(s.user.permissions) ? s.user.permissions : []),
    /* 权限判定：空权限集 fail-closed（旧缓存会话由路由守卫先 verify() 刷新后再判） */
    hasPerm() {
      const set = new Set(this.perms)
      return (p) => (set.size ? set.has(p) : false)
    },
  },
  actions: {
    _cache(u) {
      this.user = u || null
      if (u) localStorage.setItem('gm_admin_user', JSON.stringify(u))
      else localStorage.removeItem('gm_admin_user')
    },
    async login(email, password) {
      const d = await req('POST', '/api/account/admin/login', { email, password })
      this._cache(d.user)
      return d.user
    },
    async logout() {
      this._cache(null)
      try { await req('POST', '/api/account/admin/logout') } catch (_) { /* 幂等 */ }
    },
    /* 路由守卫 & 页面校验：走后台专用端点（严格只认 gm_admin_token，与前台会话隔离） */
    async verify() {
      const u = await req('GET', '/api/account/admin/me')
      this._cache(u)
      return u
    },
  },
})
