/* 后台会话：HttpOnly Cookie gm_admin_token（/api/account/admin/login 下发，仅 role>=2） */
import { defineStore } from 'pinia'
import { req } from '../api/client'

export const useSessionStore = defineStore('session', {
  state: () => ({
    user: JSON.parse(localStorage.getItem('gm_admin_user') || 'null'),
  }),
  getters: {
    role: (s) => (s.user && s.user.role) | 0,
    name: (s) => (s.user && s.user.name) || (s.user && s.user.email) || '管理员',
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
    /* 路由守卫 & 页面校验：会话无效时清缓存抛错 */
    async verify() {
      const u = await req('GET', '/api/account/me')
      this._cache(u)
      return u
    },
  },
})
