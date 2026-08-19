/* 购物车 store：服务端权威 —— add/setQty/remove 全部先写服务端再以视图刷新本地渲染缓存
 * （localStorage gm_cart 仅作渲染缓存快照，供下次进入前先画一帧） */
import { defineStore } from 'pinia'
import { req } from '../api/client'

function viewToItems(view) {
  return (view && view.items ? view.items : []).map((i) => ({
    id: i.variant_id,
    vid: i.variant_id,
    pid: i.product_id,
    slug: i.product_slug,
    title: (i.title || '').split(' · ')[0],
    variant: i.variant_label || (i.title || '').split(' · ')[1] || '',
    price: i.price / 100,
    qty: i.qty,
    img: i.image,
    stock: i.stock,
  }))
}

export const useCartStore = defineStore('cart', {
  state: () => ({
    items: JSON.parse(localStorage.getItem('gm_cart') || '[]'),
    loaded: false,
    error: null,
  }),
  getters: {
    count: (s) => s.items.reduce((n, i) => n + i.qty, 0),
    subtotal: (s) => s.items.reduce((n, i) => n + i.price * i.qty, 0),
  },
  actions: {
    _apply(view) {
      this.items = viewToItems(view)
      this.loaded = true
      localStorage.setItem('gm_cart', JSON.stringify(this.items))
    },
    _err(e, ui) {
      this.error = e
      if (ui) {
        if (e && e.status === 409) ui.toast('Insufficient stock on server', 'error')
        else if (e && e.status === 404) ui.toast('Item no longer available', 'error')
      }
      return this.refresh().catch(() => {})
    },
    async refresh() {
      this._apply(await req('GET', '/api/cart'))
    },
    async add(variantId, qty, ui) {
      try {
        this._apply(await req('POST', '/api/cart/items', { variant_id: variantId, qty: qty || 1 }))
        if (ui) { ui.toast('Added to cart ✓', 'success'); ui.openCart() }
        return true
      } catch (e) { this._err(e, ui); return false }
    },
    async addByProductId(pid, qty, ui) {
      /* 按 product id 加购：动态解析首选变体（替代 SLUGS 映射表） */
      try {
        const d = await req('GET', '/api/catalog/products-by-id/' + pid)
        const v = d.variants && d.variants[0]
        if (!v) throw new Error('no variant')
        return this.add(v.id, qty || 1, ui)
      } catch (e) { this._err(e, ui); return false }
    },
    async setQty(variantId, qty, ui) {
      try {
        if (qty < 1) return this.remove(variantId, ui)
        this._apply(await req('PUT', '/api/cart/items/' + variantId, { qty }))
      } catch (e) { this._err(e, ui) }
    },
    async remove(variantId, ui) {
      try {
        this._apply(await req('DELETE', '/api/cart/items/' + variantId))
      } catch (e) { this._err(e, ui) }
    },
    /* 登录后合并游客车（登录流程调用） */
    async mergeAfterLogin() {
      try { await req('POST', '/api/cart/merge', { token: localStorage.getItem('gm_cart_token') || '' }) } catch (_) { /* token 无车 */ }
      await this.refresh().catch(() => {})
    },
  },
})
