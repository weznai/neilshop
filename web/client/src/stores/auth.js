/* 会话 store：HttpOnly Cookie 承载鉴权，本地仅缓存认证后的用户概要 */
import { defineStore } from 'pinia'
import { req } from '../api/client'
import { useCartStore } from './cart'

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
    /* 会话过期本地收口（App.vue 401 广播调用）：清用户缓存与积分，降级游客 */
    expireLocal() {
      this._cache(null)
      this.points = null
    },
    async login(email, password) {
      const d = await req('POST', '/api/account/login', { email, password })
      this._cache(d.user)
      await this.fetchPoints().catch(() => {})
      /* 登录后同步心愿单角标（沿用 gm_wl_count + gm:wl-changed 机制） */
      this.syncWishlist().catch(() => {})
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
      /* 丢弃上个账号的游客车 token，让服务端建全新游客车 */
      try { localStorage.removeItem('gm_cart_token') } catch (_) { /* 隐私模式 */ }
      try { await req('POST', '/api/account/logout') } catch (_) { /* 幂等 */ }
      /* 会话 Cookie 已清：拉平为游客购物车（覆盖本地渲染缓存，响应头回写新 token） */
      await useCartStore().refresh().catch(() => {})
    },
    async me(silent) {
      try {
        const u = await req('GET', '/api/account/me', undefined, silent ? { silent401: true } : undefined)
        this._cache(u)
        return u
      } catch (e) {
        /* 会话过期/被禁用：清本地缓存，让账户守卫回落到登录提示 */
        if (e && e.status === 401) this._cache(null)
        throw e
      }
    },
    async syncWishlist() {
      const items = await req('GET', '/api/account/wishlist')
      try { localStorage.setItem('gm_wl_count', String((items || []).length)) } catch (_) { /* 隐私模式 */ }
      window.dispatchEvent(new Event('gm:wl-changed'))
    },
    async fetchPoints() {
      this.points = await req('GET', '/api/points')
      return this.points
    },
  },
})
