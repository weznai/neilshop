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
    async register(email, password, name, refCode) {
      const body = { email, password, name }
      /* 推荐码：后端同步支持 ref_code 字段，多余字段会被忽略（安全） */
      if (refCode) body.ref_code = refCode
      const d = await req('POST', '/api/account/register', body)
      this._cache(d.user)
      return d.user
    },
    async logout() {
      this._cache(null)
      this.points = null
      /* 心愿单角标缓存随会话一起清，避免下个游客看到上个账号的数字 */
      try { localStorage.removeItem('gm_wl_count') } catch (_) { /* 隐私模式 */ }
      try { await req('POST', '/api/account/logout') } catch (_) { /* 幂等 */ }
    },
    async me() {
      try {
        const u = await req('GET', '/api/account/me')
        this._cache(u)
        return u
      } catch (e) {
        /* 会话过期/被禁用：清本地缓存，让账户守卫回落到登录提示 */
        if (e && e.status === 401) this._cache(null)
        throw e
      }
    },
    async fetchPoints() {
      this.points = await req('GET', '/api/points')
      return this.points
    },
  },
})
