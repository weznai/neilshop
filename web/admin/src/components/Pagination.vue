<script setup>
/* 统一分页条：page/pages/total + 页码窗口（« 1 … 4 5 6 … 20 »，当前页 plum 高亮，窗口 ±2）
 * 两种形态：embed=卡内式（贴表格下缘、带上分割线，Logs/Members/Tickets 等）；
 * 默认居中式（卡片下方独立行，Orders/Products/Inventory） */
import { computed } from 'vue'

const props = defineProps({
  page: { type: Number, required: true },
  pages: { type: Number, required: true },
  total: { type: Number, default: null },
  unit: { type: String, default: '条' },
  embed: { type: Boolean, default: false },
})
const emit = defineEmits(['go'])

/* 页码窗口：当前页 ±2；窗口远离首/尾页时以省略号衔接 */
const items = computed(() => {
  const out = []
  const start = Math.max(1, props.page - 2)
  const end = Math.min(props.pages, props.page + 2)
  if (start > 1) {
    out.push(1)
    if (start > 2) out.push('…')
  }
  for (let i = start; i <= end; i++) out.push(i)
  if (end < props.pages) {
    if (end < props.pages - 1) out.push('…')
    out.push(props.pages)
  }
  return out
})
</script>

<template>
  <div v-if="pages > 1" class="pg" :class="{ embed }">
    <span class="pg-info">
      第 {{ page }} / {{ pages }} 页<template v-if="total != null"> · 共 {{ total.toLocaleString() }} {{ unit }}</template>
    </span>
    <div class="pg-btns">
      <button class="pg-nav" :disabled="page <= 1" aria-label="上一页" @click="emit('go', page - 1)">«</button>
      <template v-for="(it, i) in items" :key="i">
        <span v-if="it === '…'" class="pg-dots">…</span>
        <button v-else class="pg-num" :class="{ on: it === page }" :disabled="it === page" @click="emit('go', it)">{{ it }}</button>
      </template>
      <button class="pg-nav" :disabled="page >= pages" aria-label="下一页" @click="emit('go', page + 1)">»</button>
    </div>
  </div>
</template>

<style scoped>
.pg{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;font-size:12.5px;color:var(--gray)}
.pg:not(.embed){justify-content:center;margin-top:16px}
.pg.embed{padding:12px 10px;border-top:1px solid var(--gray-light)}
.pg-btns{display:flex;gap:6px;align-items:center}
/* 页码/翻页按钮：30px 方形圆角 */
.pg-num,.pg-nav{width:30px;height:30px;border-radius:8px;border:1.5px solid var(--gray-light);background:#fff;color:var(--gray);
  font-size:12.5px;font-weight:600;display:inline-flex;align-items:center;justify-content:center;cursor:pointer;
  transition:border-color .15s,color .15s,background .15s,opacity .15s}
.pg-nav{font-size:14px;line-height:1}
.pg-nav:disabled{opacity:.4;cursor:not-allowed}
.pg-num:hover:not(.on):not(:disabled){border-color:var(--rose);color:var(--plum);background:var(--rose-pale)}
.pg-num.on{background:var(--plum);border-color:var(--plum);color:#fff;cursor:default}
.pg-dots{width:18px;text-align:center;color:var(--gray);user-select:none}
</style>
