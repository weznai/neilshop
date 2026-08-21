<script setup>
/* 通用空态：44px emoji + 主/次文案 + action 插槽（重试 / 新建入口） */
defineProps({
  icon: { type: String, default: '📭' },
  title: { type: String, default: '暂无数据' },
  sub: { type: String, default: '' },
})
</script>

<template>
  <div class="empty-state">
    <div class="empty-icon">{{ icon }}</div>
    <div class="empty-title">{{ title }}</div>
    <div v-if="sub" class="empty-sub">{{ sub }}</div>
    <div v-if="$slots.action" class="empty-action"><slot name="action" /></div>
  </div>
</template>

<style scoped>
.empty-state{text-align:center;color:var(--gray);padding:30px 16px}
.empty-icon{font-size:44px;line-height:1;margin-bottom:10px}
.empty-title{font-size:13.5px;color:var(--ink);font-weight:600}
.empty-sub{font-size:12.5px;color:var(--gray);margin-top:4px;line-height:1.6}
.empty-action{margin-top:12px;display:flex;justify-content:center;gap:8px;flex-wrap:wrap}
</style>
