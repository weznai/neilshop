/* 会话 store：HttpOnly Cookie 承载鉴权，本地仅缓存认证后的用户概要 */
import { defineStore } from 'pinia'
import { req } from '../api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: JSON.parse(localStorage.getItem('gm_user') || 'null'),
    points: null,
  }),
  getters: {
    isLoggedIn: (s) => !!s.user,
    role: (s) => (s.user && s.user.role) | 0,
  },
  actions: {
    _cache(u) {
      this.user = u || null
      if (u) localStorage.setItem('gm_user', JSON.stringify(u))
      else localStorage.removeItem('gm_user')
    },
    async login(email, password) {
      const d = await req('POST', '/api/account/login', { email, password })
      this._cache(d.user)
      await this.fetchPoints().catch(() => {})
      return d.user
    },
    async register(email, password, name) {
      const d = await req('POST', '/api/account/register', { email, password, name })
      this._cache(d.user)
      return d.user
    },
    async logout() {
      this._cache(null)
      this.points = null
      try { await req('POST', '/api/account/logout') } catch (_) { /* 幂等 */ }
    },
    async me() {
      const u = await req('GET', '/api/account/me')
      this._cache(u)
      return u
    },
    async fetchPoints() {
      this.points = await req('GET', '/api/points')
      return this.points
    },
  },
})
