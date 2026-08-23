/* 购物车 store：服务端权威 —— add/setQty/remove 全部先写服务端再以视图刷新本地渲染缓存
 * （localStorage gm_cart 仅作渲染缓存快照，供下次进入前先画一帧） */
import { defineStore } from 'pinia'
import { productDetail, req } from '../api/client'
import { i18n } from '../i18n'
import { useUiStore } from './ui'

const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)

/* setQty 请求序列守卫：并发改量响应乱序时，只应用最新一次的视图（对齐 preview 的 pvSeq） */
let _qtySeq = 0

function readCartCache() {
  try { return JSON.parse(localStorage.getItem('gm_cart') || '[]') || [] } catch (_) { return [] }
}
function writeCartCache(items) {
  try { localStorage.setItem('gm_cart', JSON.stringify(items)) } catch (_) { /* 隐私模式等写入失败即弃 */ }
}

function viewToItems(view) {
  return (view && view.items ? view.items : []).map((i) => ({
    id: i.variant_id,
    vid: i.variant_id,
    pid: i.product_id,
    slug: i.product_slug,
    title: (i.title || '').split(' · ')[0],
    variant: i.variant_label || (i.title || '').split(' · ')[1] || '',
    price: i.price / 100,
    priceC: i.price,
    qty: i.qty,
    img: i.image,
    stock: i.stock,
    stockStatus: i.stock_status || '',
    /* 失效行（变体停用/删除或商品下架，服务端带 inactive 标记返回）：只允许删除 */
    inactive: !!i.inactive,
  }))
}

export const useCartStore = defineStore('cart', {
  state: () => ({
    items: readCartCache(),
    loaded: false,
    error: null,
    removed: null, /* {vid,qty,title,at} 最近删除快照，供 UI 撤销 */
  }),
  getters: {
    count: (s) => s.items.reduce((n, i) => n + i.qty, 0),
    subtotal: (s) => s.items.reduce((n, i) => n + i.price * i.qty, 0),
    /* 美分整数小计（避免浮点误差，与后端一致） */
    subtotalC: (s) => s.items.reduce((n, i) => n + (i.priceC || Math.round(i.price * 100)) * i.qty, 0),
  },
  actions: {
    _apply(view) {
      this.items = viewToItems(view)
      this.loaded = true
      writeCartCache(this.items)
    },
    _err(e, ui) {
      this.error = e
      if (ui) {
        if (e && e.status === 409) ui.toast(tt('Insufficient stock — cart refreshed', '库存不足，购物车已刷新'), 'error')
        else if (e && e.status === 404) ui.toast(tt('Item no longer available', '商品已下架'), 'error')
      }
      return this.refresh().catch(() => {})
    },
    async refresh() {
      this._apply(await req('GET', '/api/cart'))
    },
    async add(variantId, qty, ui) {
      try {
        this._apply(await req('POST', '/api/cart/items', { variant_id: variantId, qty: qty || 1 }))
        this.removed = null
        if (ui) { ui.toast(tt('Added to cart', '已加入购物车'), 'success'); ui.openCart() }
        return true
      } catch (e) { this._err(e, ui); return false }
    },
    async addByProductId(pid, qty, ui) {
      /* 按 product id 加购：动态解析变体（优先选有货变体，避免首选变体售罄即失败）；
         走 productDetail 内存缓存——同商品快速加购/推荐位重复点击不重复请求 */
      try {
        const d = await productDetail(pid)
        const vs = d.variants || []
        const v = vs.find((x) => (x.stock ?? 0) > 0 && x.stock_status !== 'out') || vs[0]
        if (!v) throw new Error('no variant')
        return this.add(v.id, qty || 1, ui)
      } catch (e) { this._err(e, ui); return false }
    },
    async setQty(variantId, qty, ui) {
      try {
        if (qty < 1) return this.remove(variantId, ui)
        const seq = ++_qtySeq
        /* 前端按库存上限先夹紧（后端 /api/cart/items/{id} 也会 409 拒绝）；
            OOS 行不允许增量（stock<=0 时上限冻结在当前数量，防止 +1 死循环 409） */
        const it = this.items.find((x) => x.vid === variantId)
        if (it && it.stock <= 0 && qty > it.qty) {
          if (ui) ui.toast(tt('Out of stock', '库存不足'), 'error')
          return
        }
        const max = it && it.stock > 0 ? it.stock : 99
        if (qty > max) {
          if (ui) ui.toast(tt(`Only ${max} left in stock`, `库存仅剩 ${max} 件`), 'error')
          qty = max
          if (it && it.qty === qty) return
        }
        const view = await req('PUT', '/api/cart/items/' + variantId, { qty })
        if (seq !== _qtySeq) return /* 已有更新的改量在途，丢弃过期响应 */
        this._apply(view)
        this.removed = null
      } catch (e) {
        if (e && e.status === 404) { /* 行已被服务端剔除（如变体删除）→ 刷新对齐 */ }
        this._err(e, ui)
      }
    },
    async remove(variantId, ui) {
      const snap = this.items.find((x) => x.vid === variantId) || null
      try {
        this._apply(await req('DELETE', '/api/cart/items/' + variantId))
        if (snap) this.removed = { vid: snap.vid, qty: snap.qty, title: snap.title, variant: snap.variant, at: Date.now() }
      } catch (e) { this._err(e, ui) }
    },
    /* 撤销最近一次删除（UI 撤销条调用） */
    async undoRemove(ui) {
      const r = this.removed
      if (!r) return
      this.removed = null
      try {
        this._apply(await req('POST', '/api/cart/items', { variant_id: r.vid, qty: r.qty }))
        if (ui) ui.toast(tt('Item restored', '已恢复商品'), 'success')
      } catch (e) { this._err(e, ui) }
    },
    dismissRemoved() { this.removed = null },
    /* 登录后合并游客车（登录流程调用）：无游客 token 时不发请求（空串会被 422 拒绝） */
    async mergeAfterLogin() {
      let token = ''
      try { token = localStorage.getItem('gm_cart_token') || '' } catch (_) { /* 隐私模式 */ }
      if (token) {
        try {
          await req('POST', '/api/cart/merge', { token })
        } catch (e) {
          if (!e || e.status !== 404) {
            useUiStore().toast(tt('Failed to merge your cart, some items may be missing', '购物车合并失败，部分商品可能未带入'), 'error')
          }
        }
      }
      await this.refresh().catch(() => {})
    },
  },
})
