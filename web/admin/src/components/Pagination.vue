<script setup>
/* 统一分页条：page/pages/total + 上一页/下一页
 * 两种形态：embed=卡内式（贴表格下缘、带上分割线，Logs/Members/Tickets 等）；
 * 默认居中式（卡片下方独立行，Orders/Products/Inventory） */
defineProps({
  page: { type: Number, required: true },
  pages: { type: Number, required: true },
  total: { type: Number, default: null },
  unit: { type: String, default: '条' },
  embed: { type: Boolean, default: false },
})
const emit = defineEmits(['go'])
</script>

<template>
  <div v-if="pages > 1" class="pg" :class="{ embed }">
    <span class="pg-info">
      第 {{ page }} / {{ pages }} 页<template v-if="total != null"> · 共 {{ total.toLocaleString() }} {{ unit }}</template>
    </span>
    <div class="pg-btns">
      <button class="btn btn-secondary btn-sm" :disabled="page <= 1" @click="emit('go', page - 1)">上一页</button>
      <button class="btn btn-secondary btn-sm" :disabled="page >= pages" @click="emit('go', page + 1)">下一页</button>
    </div>
  </div>
</template>

<style scoped>
.pg{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;font-size:12.5px;color:var(--gray)}
.pg:not(.embed){justify-content:center;margin-top:16px}
.pg.embed{padding:12px 10px;border-top:1px solid var(--gray-light)}
.pg-btns{display:flex;gap:8px}
.pg-btns button:disabled{opacity:.45;cursor:not-allowed}
</style>
