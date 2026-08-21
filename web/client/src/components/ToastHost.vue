<script setup>
import { i18n } from '../i18n'
import { useUiStore } from '../stores/ui'
const ui = useUiStore()
</script>

<template>
  <TransitionGroup name="toast" tag="div" class="toast-wrap">
    <div
      v-for="t in ui.toasts" :key="t.id" class="toast" :class="t.type"
      :role="t.type === 'loading' ? 'alert' : 'status'"
      :aria-live="t.type === 'loading' ? 'assertive' : 'polite'"
      :aria-label="t.msg || undefined"
    >
      <span v-if="t.type === 'loading'" class="toast-spin" aria-hidden="true"></span>
      <template v-else-if="t.type === 'success'"><span aria-hidden="true">✓</span><span>{{ t.msg }}</span></template>
      <template v-else-if="t.type === 'error'"><span aria-hidden="true">✗</span><span>{{ t.msg }}</span></template>
      <span v-else>{{ t.msg }}</span>
      <button
        type="button" class="toast-x"
        :aria-label="i18n.lang === 'zh' ? '关闭提示' : 'Dismiss notification'"
        @click="ui.dismiss(t.id)"
      >×</button>
    </div>
  </TransitionGroup>
</template>

<style scoped>
/* .toast-wrap 全局 pointer-events:none —— 开启本条可点，供关闭钮使用 */
.toast { pointer-events: auto; }
/* 进出场 + 位移补间 */
.toast-enter-active { transition: opacity .25s ease-out, transform .25s ease-out; }
.toast-leave-active { transition: opacity .2s ease-out, transform .2s ease-out; }
.toast-enter-from { opacity: 0; transform: translateY(-10px) scale(.96); }
.toast-leave-to { opacity: 0; transform: translateY(-6px); }
.toast-move { transition: transform .25s ease-out; }
.toast-x {
  border: none; background: none; color: #fff; opacity: .65;
  font-size: 16px; line-height: 1; padding: 2px 4px; margin: -2px -4px -2px 2px;
  cursor: pointer; border-radius: 6px; flex: none;
}
.toast-x:hover { opacity: 1; }
.toast-x:focus-visible { outline: 2px solid #fff; outline-offset: 1px; opacity: 1; }
/* 连续 toast 降级：尊重 prefers-reduced-motion（共享 CSS 已有全站兜底，此处按组件要求显式重复） */
@media (prefers-reduced-motion: reduce) {
  .toast { animation: none; }
  .toast-spin { animation: none; }
  .toast-enter-active, .toast-leave-active, .toast-move { transition: none; }
}
</style>
