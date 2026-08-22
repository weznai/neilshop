<script setup>
/* 通用空态：icon prop 传 emoji 字符时照旧渲染（旧调用兼容）；
 * 未传 icon 时按 kind 渲染内置线性 SVG（empty 空收件箱 / search 搜索 / error 警告），
 * 描边 var(--gray) + var(--plum) 点缀，与侧栏 SVG 图标同语言 */
import { computed } from 'vue'

const props = defineProps({
  icon: { type: String, default: '' },
  kind: { type: String, default: 'empty' },
  title: { type: String, default: '暂无数据' },
  sub: { type: String, default: '' },
})

const ICONS = {
  empty: '<path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/><path d="M22 12h-6l-2 3h-4l-2-3H2" stroke="var(--plum)"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5" stroke="var(--plum)"/>',
  error: '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13" stroke="var(--plum)"/><line x1="12" y1="17" x2="12.01" y2="17" stroke="var(--plum)"/>',
}
const svg = computed(() => ICONS[props.kind] || ICONS.empty)
</script>

<template>
  <div class="empty-state">
    <div v-if="icon" class="empty-icon">{{ icon }}</div>
    <div v-else class="empty-svg">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--gray)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" v-html="svg" />
    </div>
    <div class="empty-title">{{ title }}</div>
    <div v-if="sub" class="empty-sub">{{ sub }}</div>
    <div v-if="$slots.action" class="empty-action"><slot name="action" /></div>
  </div>
</template>

<style scoped>
.empty-state{text-align:center;color:var(--gray);padding:30px 16px}
.empty-icon{font-size:44px;line-height:1;margin-bottom:10px}
.empty-svg{margin-bottom:10px}
.empty-title{font-size:13.5px;color:var(--ink);font-weight:600}
.empty-sub{font-size:12.5px;color:var(--gray);margin-top:4px;line-height:1.6}
.empty-action{margin-top:12px;display:flex;justify-content:center;gap:8px;flex-wrap:wrap}
</style>
