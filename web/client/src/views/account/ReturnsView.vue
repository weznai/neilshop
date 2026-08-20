<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../../api/client'

const returns = ref([])
const exchanges = ref([])
const loaded = ref(false)
const failed = ref(false)

/* RmaStatus：0申请 1批准 2标签已发 3在途 4已收货 5已退款 6拒绝 7部分退款 */
const RSTATUS = {
  0: ['申请中', 'tag-pending'], 1: ['已批准', 'tag-paid'], 2: ['标签已发送', 'tag-ship'],
  3: ['退货在途', 'tag-ship'], 4: ['仓库已收货', 'tag-paid'], 5: ['已退款', 'tag-done'],
  6: ['已拒绝', 'tag-error'], 7: ['部分退款', 'tag-pending'],
}
/* 换货状态 0-5（后端 status_label 直接给中文，此处仅做 tag 配色） */
const XCLASS = { 0: 'tag-pending', 1: 'tag-paid', 2: 'tag-pending', 3: 'tag-ship', 4: 'tag-done', 5: 'tag-error' }
/* RmaReason */
const RREASON = { 1: '尺码不合', 2: '质量问题', 3: '不喜欢', 4: '收到损坏', 5: '发错货', 6: '其他' }
/* RMA 正向流程节点（6/7 为终态例外） */
const RSTEPS = ['申请', '批准', '标签', '在途', '收货', '退款']
const RSTEP_IDX = { 0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5 }

const money = (c) => (c === null || c === undefined) ? '待定' : '$' + (c / 100).toFixed(2)
function fmt(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d)) return '—'
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

onMounted(async () => {
  const [r, x] = await Promise.allSettled([
    req('GET', '/api/returns'),
    req('GET', '/api/exchanges'),
  ])
  if (r.status === 'fulfilled') returns.value = r.value.items || []
  if (x.status === 'fulfilled') exchanges.value = x.value.items || []
  failed.value = r.status === 'rejected' && x.status === 'rejected'
  loaded.value = true
})
</script>

<template>
  <div>
    <div class="card" style="padding:18px;margin-bottom:16px;font-size:13.5px;color:var(--gray);line-height:1.7">
      ↩️ <b>30 天免费退货</b> · <b>换货永久免费</b>（新款立即补发，旧款无需寄回）。
      入口：<router-link to="/account/orders" style="color:var(--plum)">订单</router-link> → 详情 → 商品行「申请退货 / 换货」。
    </div>

    <div v-if="!loaded" style="display:grid;gap:12px">
      <div v-for="i in 2" :key="i" class="skeleton" style="height:120px;border-radius:14px" />
    </div>
    <div v-else-if="failed" class="card" style="padding:30px;text-align:center;color:var(--gray)">加载失败，请刷新重试</div>

    <template v-else>
      <!-- 退货 RMA -->
      <h3 v-if="returns.length" style="font-size:16px;margin-bottom:12px">退货记录</h3>
      <div v-if="returns.length" style="display:grid;gap:12px">
        <div v-for="r in returns" :key="r.rma_no" class="card" style="padding:18px">
          <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:flex-start">
            <div>
              <b>{{ r.rma_no }}</b>
              <div style="font-size:12px;color:var(--gray)">订单 {{ r.order_no }} · {{ fmt(r.created_at) }}</div>
            </div>
            <span class="tag" :class="RSTATUS[r.status]?.[1]">{{ RSTATUS[r.status]?.[0] || '未知' }}</span>
            <div style="text-align:right">
              <b style="color:var(--plum)">{{ money(r.refund_amount) }}</b>
              <div style="font-size:12px;color:var(--gray)">预计退款</div>
            </div>
          </div>

          <div v-if="r.item" style="display:flex;gap:10px;align-items:center;margin:10px 0;padding:8px 0;border-top:1px dashed var(--gray-light)">
            <img v-if="r.item.image" :src="r.item.image" :alt="r.item.title" style="width:40px;height:40px;border-radius:8px;object-fit:cover">
            <div style="flex:1;font-size:13px">
              <b>{{ r.item.title }}</b>
              <div style="color:var(--gray);font-size:12px">× {{ r.qty }} · {{ RREASON[r.reason] || r.reason }}<span v-if="r.reason_detail">（{{ r.reason_detail }}）</span></div>
            </div>
            <a v-if="r.label_url" class="btn btn-secondary btn-sm" :href="r.label_url" target="_blank" rel="noopener">🖨 打印退货标签</a>
          </div>

          <!-- 进度条（拒绝/部分退款单独提示） -->
          <div v-if="RSTEP_IDX[r.status] !== undefined" style="display:flex;gap:0;margin-top:8px">
            <div v-for="(s, i) in RSTEPS" :key="s" style="flex:1;text-align:center">
              <div :style="{ background: i <= RSTEP_IDX[r.status] ? 'var(--plum)' : 'var(--gray-light)' }" style="height:5px;border-radius:3px;margin:0 3px"></div>
              <div style="font-size:11px;margin-top:4px" :style="{ color: i <= RSTEP_IDX[r.status] ? 'var(--ink)' : 'var(--gray)', fontWeight: i === RSTEP_IDX[r.status] ? '700' : '' }">{{ s }}</div>
            </div>
          </div>
          <div v-else-if="r.status === 7" style="font-size:12.5px;color:var(--warn);margin-top:8px">⚠️ 部分退款已完成{{ r.refunded_at ? ' · ' + fmt(r.refunded_at) : '' }}</div>
          <div v-else style="font-size:12.5px;color:var(--error);margin-top:8px">✖ 申请已被拒绝，如有疑问请<router-link to="/contact" style="color:var(--plum)">联系客服</router-link></div>
        </div>
      </div>

      <!-- 换货 -->
      <h3 v-if="exchanges.length" style="font-size:16px;margin:22px 0 12px">换货记录</h3>
      <div v-if="exchanges.length" style="display:grid;gap:12px">
        <div v-for="x in exchanges" :key="x.exchange_no" class="card" style="padding:18px">
          <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:flex-start">
            <div>
              <b>{{ x.exchange_no }}</b>
              <div style="font-size:12px;color:var(--gray)">订单 {{ x.order_no }} · {{ fmt(x.created_at) }}</div>
            </div>
            <span class="tag" :class="XCLASS[x.status]">{{ x.status_label || x.status }}</span>
            <span v-if="x.price_diff > 0" class="tag tag-pending">需补差价 ${{ (x.price_diff / 100).toFixed(2) }}</span>
            <span v-else-if="x.price_diff < 0" class="tag tag-paid">退差价 ${{ (-x.price_diff / 100).toFixed(2) }}</span>
          </div>
          <div style="display:flex;gap:10px;align-items:center;margin-top:10px;padding-top:10px;border-top:1px dashed var(--gray-light);font-size:13px;flex-wrap:wrap">
            <span v-if="x.old_variant" style="color:var(--gray)">{{ x.old_variant.title }}</span>
            <span v-if="x.old_variant && x.new_variant">→</span>
            <b v-if="x.new_variant">{{ x.new_variant.title }}</b>
            <span v-if="x.new_variant" style="color:var(--gray)">（{{ '$' + (x.new_variant.price / 100).toFixed(2) }}）</span>
          </div>
        </div>
      </div>

      <div v-if="!returns.length && !exchanges.length" class="card" style="padding:30px;text-align:center;color:var(--gray)">
        暂无退换货记录 💅
      </div>
    </template>
  </div>
</template>
