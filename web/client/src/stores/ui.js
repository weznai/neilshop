/* UI 全局态：toast 队列 / 模态框 / 购物车抽屉 / 移动导航（对齐旧 app.js 行为） */
import { defineStore } from 'pinia'

let _toastSeq = 0

export const useUiStore = defineStore('ui', {
  state: () => ({
    toasts: [],
    openModalId: null,
    cartDrawer: false,
    mnavOpen: false,
    searchOpen: false,
    chatOpen: false,      /* ChatWidget 面板（组件自上报，body 滚动锁统一走 anyOverlay） */
    popupsOpen: false,    /* MarketingPopups welcome/exit（同上） */
  }),
  getters: {
    anyOverlay: (s) => s.openModalId || s.cartDrawer || s.mnavOpen || s.searchOpen || s.chatOpen || s.popupsOpen,
  },
  actions: {
    toast(msg, type = '', opts) {
      const id = ++_toastSeq
      this.toasts.push({ id, msg, type })
      /* 同屏最多 3 条：超出丢弃最旧 */
      while (this.toasts.length > 3) this.toasts.shift()
      /* loading 态默认常驻（手动 dismiss 收口）；其余 2.5s 自动消失；opts.duration 可覆盖 */
      const ms = opts && opts.duration !== undefined ? opts.duration : (type === 'loading' ? 0 : 2500)
      if (ms > 0) setTimeout(() => { this.dismiss(id) }, ms)
      return id
    },
    dismiss(id) {
      this.toasts = this.toasts.filter((t) => t.id !== id)
    },
    openModal(id) { this.openModalId = id },
    closeModal() { this.openModalId = null },
    openCart() { this.cartDrawer = true },
    closeCart() { this.cartDrawer = false },
    openMnav() { this.mnavOpen = true },
    closeMnav() { this.mnavOpen = false },
    openSearch() { this.searchOpen = true },
    closeSearch() { this.searchOpen = false },
    /* ESC 委托（App 根挂 keydown）：仅关抽屉/搜索/移动导航/模态；
       chatOpen/popupsOpen 由各组件自管（ESC 优先关上面的浮层，见 ChatWidget） */
    closeAll() {
      this.openModalId = null
      this.cartDrawer = false
      this.mnavOpen = false
      this.searchOpen = false
    },
    /* ESC 委托（App 根挂 keydown） */
    onEsc() { this.closeAll() },
  },
})
