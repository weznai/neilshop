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
  }),
  getters: {
    anyOverlay: (s) => s.openModalId || s.cartDrawer || s.mnavOpen || s.searchOpen,
  },
  actions: {
    toast(msg, type = '') {
      const id = ++_toastSeq
      this.toasts.push({ id, msg, type })
      setTimeout(() => {
        this.toasts = this.toasts.filter((t) => t.id !== id)
      }, 2500)
    },
    openModal(id) { this.openModalId = id },
    closeModal() { this.openModalId = null },
    openCart() { this.cartDrawer = true },
    closeCart() { this.cartDrawer = false },
    openMnav() { this.mnavOpen = true },
    closeMnav() { this.mnavOpen = false },
    openSearch() { this.searchOpen = true },
    closeSearch() { this.searchOpen = false },
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
