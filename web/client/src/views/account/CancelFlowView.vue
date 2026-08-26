<script setup>
/* 取消/退款挽留向导（3 步：替代方案 → 原因 → 最终确认）
 * 设计口径：入口下沉（列表/详情不再直达），本页承载挽留分流 + 如实披露退款条款；
 * 最终一步仍清晰可完成（合规：不彻底藏死取消能力），reason 落库 user_wizard:<key> 供归因分析 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../../api/client'
import { useUiStore } from '../../stores/ui'
import { statusLabel, statusTag } from '../../composables/orderStatus'
import { useArmConfirm } from '../../composables/useArmConfirm'
import { fmtDateTime } from '../../composables/datetime'
import { money } from '../../composables/format'
import { tt } from '../../i18n'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()

const o = ref(null)
const loading = ref(true)
const failed = ref(false)
const step = ref(1) /* 1 挽留 2 原因 3 确认 */
const STEPS = computed(() => [
  { n: 1, en: 'How can we help', zh: '还能帮你什么' },
  { n: 2, en: 'Tell us why', zh: '取消原因' },
  { n: 3, en: 'Final review', zh: '最终确认' },
])

const fmt = fmtDateTime

async function load() {
  const no = route.query.no
  loading.value = true
  failed.value = false
  if (!no) { failed.value = true; loading.value = false; return }
  try {
    o.value = await req('GET', '/api/orders/' + encodeURIComponent(no))
  } catch (_) {
    failed.value = true
  } finally { loading.value = false }
}
onMounted(load)

/* 可取消口径（与服务端一致）：待付(0) / 已付未发货(1 且 shipping_status=0) */
const isUnpaid = computed(() => !!o.value && o.value.status === 0)
const canCancel = computed(() => !!o.value && (o.value.status === 0 || (o.value.status === 1 && (o.value.shipping_status || 0) === 0)))
/* 已支付且可退换（1-5）：换货替代方案才展示 */
const returnable = computed(() => !!o.value && [1, 2, 3, 4, 5].includes(o.value.status))

/* ---------- 第 1 步：替代方案 ---------- */
const ALT = computed(() => {
  const list = []
  if (o.value && [0, 1, 2].includes(o.value.status) && (o.value.shipping_status || 0) === 0) {
    list.push({
      ico: '✏️', en: 'Wrong address?', zh: '地址填错了？',
      dEn: 'Unshipped orders can update the shipping address anytime.', dZh: '未发货订单可随时修改收货地址，不用取消重下。',
      ctaEn: 'Edit address', ctaZh: '去改地址', act: goDetail,
    })
  }
  if (returnable.value) {
    list.push({
      ico: '🔁', en: 'Size not right?', zh: '尺码不合适？',
      dEn: 'Exchanges are always free — swap sizes or styles, no refund wait.', dZh: '换货永久免费，直接换尺码/换款式，不用等退款再重买。',
      ctaEn: 'Free exchange', ctaZh: '免费换货', act: goExchange,
    })
  }
  list.push({
    ico: '🚚', en: 'Where is my order?', zh: '想查发货进度？',
    dEn: 'See live packing & shipping progress in order details.', dZh: '订单详情可查看实时备货与物流进度。',
    ctaEn: 'Track order', ctaZh: '查进度', act: goDetail,
  })
  list.push({
    ico: '💬', en: 'Anything else?', zh: '其他问题？',
    dEn: 'Our glam team replies in ~2 min — most issues solve faster than a refund.', dZh: '客服约 2 分钟回复，大部分问题比退款解决得更快。',
    ctaEn: 'Contact support', ctaZh: '联系客服', act: () => router.push('/contact'),
  })
  return list
})

function goDetail() {
  router.push({ path: '/account/orders/detail', query: { no: o.value.order_no } })
}
function goExchange() {
  router.push({ path: '/account/orders/detail', query: { no: o.value.order_no, help: 'support' } })
}

/* ---------- 第 2 步：原因 ---------- */
const REASONS = [
  { k: 'mind', ico: '💭', en: 'Changed my mind', zh: '不想要了' },
  { k: 'price', ico: '💸', en: 'Found a better price', zh: '别处更便宜' },
  { k: 'size', ico: '📐', en: 'Size / fit issue', zh: '尺码不合适' },
  { k: 'speed', ico: '⏱️', en: 'Shipping too slow', zh: '发货/到货太慢' },
  { k: 'other', ico: '✍️', en: 'Other reason', zh: '其他原因' },
]
const picked = ref('')
const detail = ref('')
/* 每个原因一条针对性挽留提示（选中原由后展示） */
const HINT = {
  mind: ['Hot sets restock slowly — this one may be sold out when you want it back.', '热门款式补货慢，取消后想再买可能就断货了。'],
  price: ['Found it cheaper elsewhere? Message us — we price-match within 7 days.', '发现更低价格？联系客服，7 天内可申请保价。'],
  size: ['A free exchange keeps your order — no waiting for a refund, and shipping is on us.', '免费换货不用等退款、免运费，尺码问题换货更快。'],
  speed: ['Your order is being prepared with care — contact us and we will try to speed it up.', '订单正在加急备货中，联系客服可帮你催单提速。'],
  other: ['Tell us more below — we will do our best to fix it before you go.', '下方告诉我们具体情况，我们会尽力先帮你解决。'],
}

/* ---------- 第 3 步：确认 + 提交 ---------- */
const acked = ref(false)
const submitArm = useArmConfirm()
const submitting = ref(false)
const done = ref(null) /* { refundAmount } 提交成功态 */

async function submitCancel() {
  submitting.value = true
  try {
    const d = await req('POST', '/api/orders/' + encodeURIComponent(o.value.order_no) + '/cancel', {
      reason: 'user_wizard:' + picked.value,
    })
    ui.toast(tt('Order cancelled', '订单已取消'), 'success')
    done.value = { refund: d && d.refund }
  } catch (e) {
    const det = String((e && e.data && e.data.detail) || '')
    if (det.startsWith('not_cancellable')) {
      ui.toast(tt('Order status changed — please review', '订单状态已变化，请重新确认'), 'error')
      await load()
      step.value = 1
    } else if (det.startsWith('no_refundable_payment')) {
      ui.toast(tt('Auto refund unavailable — please contact support', '无法自动退款，请联系客服处理'), 'error')
    } else {
      ui.toast(tt('Cancel failed — please retry later', '取消失败，请稍后再试'), 'error')
    }
  } finally { submitting.value = false }
}

function confirmBtn() {
  /* 两段式：arm 态红字提示，二次点击才真正提交 */
  submitArm.hit('go', () => { if (acked.value && !submitting.value) submitCancel() })
}
</script>

<template>
  <div style="display:grid;gap:18px">
    <!-- 加载 / 失败 -->
    <template v-if="loading">
      <div class="skeleton" style="height:120px;border-radius:16px" />
      <div class="skeleton" style="height:300px;border-radius:16px" />
    </template>
    <div v-else-if="failed || !o" class="card" style="padding:36px;text-align:center;color:var(--gray)">
      {{ tt('Could not load this order.', '订单加载失败。') }}
      <div style="margin-top:12px"><router-link class="btn btn-secondary btn-sm" to="/account/orders">{{ tt('← Back to orders', '← 返回订单列表') }}</router-link></div>
    </div>

    <!-- 不可取消（状态已变化 / 已发货） -->
    <div v-else-if="!canCancel && !done" class="card" style="padding:36px;text-align:center">
      <div style="font-size:42px;margin-bottom:10px">🫶</div>
      <b style="display:block;font-size:17px;margin-bottom:6px">{{ tt('This order can no longer be cancelled', '该订单当前状态已无法取消') }}</b>
      <p style="font-size:13.5px;color:var(--gray);margin-bottom:14px">
        {{ tt('It has shipped or been fulfilled — returns & exchanges are still available.', '订单已发货或已履约，退货/换货通道仍然开放。') }}
      </p>
      <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap">
        <router-link class="btn btn-secondary btn-sm" :to="{ path: '/account/orders/detail', query: { no: o.order_no } }">{{ tt('View order →', '查看订单 →') }}</router-link>
        <router-link class="btn btn-primary btn-sm" to="/store">{{ tt('Keep shopping', '继续逛逛') }}</router-link>
      </div>
    </div>

    <!-- 提交成功：退款结果面板 -->
    <div v-else-if="done" class="card cf-done" style="padding:36px;text-align:center;position:relative;overflow:hidden">
      <div class="cf-done-ico">✓</div>
      <h2 style="font-family:var(--font-title);font-size:24px;margin-bottom:6px">{{ tt('Order cancelled', '订单已取消') }}</h2>
      <p v-if="done.refund && done.refund.amount" style="font-size:14px;color:var(--gray)">
        {{ tt(`${money(done.refund.amount)} will be returned to your original payment method within 5–10 business days.`, `退款 ${money(done.refund.amount)} 将在 5–10 个工作日内原路退回。`) }}
      </p>
      <p v-else-if="isUnpaid" style="font-size:14px;color:var(--gray)">
        {{ tt('No payment was charged for this order.', '该订单尚未支付，未产生扣款。') }}
      </p>
      <p v-else style="font-size:14px;color:var(--gray)">
        {{ tt('The refund is on its way back to your payment method.', '退款将原路退回你的支付账户。') }}
      </p>
      <div style="display:flex;gap:10px;justify-content:center;margin-top:18px;flex-wrap:wrap">
        <router-link class="btn btn-secondary btn-sm" to="/account/orders">{{ tt('← Back to orders', '← 返回订单列表') }}</router-link>
        <router-link class="btn btn-primary btn-sm" to="/store">{{ tt('Find your next set 💅', '再去逛逛 💅') }}</router-link>
      </div>
    </div>

    <!-- 三步向导主体 -->
    <template v-else>
      <!-- 头部：订单信息 + 步骤条 -->
      <div class="card cf-hero">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
          <div>
            <h2 style="font-family:var(--font-title);font-size:24px">{{ tt('Before you go…', '取消之前，先看看…') }} 💔</h2>
            <div style="font-size:12.5px;color:var(--gray);margin-top:4px">
              <b>{{ o.order_no }}</b> · {{ money(o.grand_total) }} · {{ fmt(o.placed_at) }}
            </div>
          </div>
          <span class="tag" :class="statusTag(o.status)">{{ statusLabel(o.status) }}</span>
        </div>
        <!-- 步骤指示 -->
        <div class="cf-steps">
          <template v-for="(s, i) in STEPS" :key="s.n">
            <div class="cf-step" :class="{ on: step === s.n, past: step > s.n }">
              <div class="cf-step-dot">{{ step > s.n ? '✓' : s.n }}</div>
              <span>{{ tt(s.en, s.zh) }}</span>
            </div>
            <div v-if="i < STEPS.length - 1" class="cf-step-line" :class="{ on: step > s.n }" />
          </template>
        </div>
      </div>

      <!-- 第 1 步：替代方案挽留 -->
      <div v-if="step === 1" style="display:grid;gap:16px">
        <div class="grid grid-2">
          <button v-for="a in ALT" :key="a.en" type="button" class="card cf-alt" @click="a.act">
            <span class="cf-alt-ico">{{ a.ico }}</span>
            <span style="flex:1;min-width:0">
              <b style="display:block;font-size:14.5px">{{ tt(a.en, a.zh) }}</b>
              <span style="font-size:12.5px;color:var(--gray);line-height:1.6;display:block;margin-top:2px">{{ tt(a.dEn, a.dZh) }}</span>
              <span class="cf-alt-cta">{{ tt(a.ctaEn, a.ctaZh) }} →</span>
            </span>
          </button>
        </div>
        <!-- 保留订单权益 -->
        <div class="card cf-keep">
          <b style="font-size:13.5px">{{ tt('If you keep this order', '保留订单，这些都在') }} ✨</b>
          <ul class="cf-keep-list">
            <li v-if="o.points_earned">⭐ {{ tt(`${o.points_earned} Glow Points` + ' (unfrozen after delivery)', `${o.points_earned} 积分` + '（确认收货后解冻）') }}</li>
            <li v-if="o.shipping_fee === 0">🚚 {{ tt('Free shipping on this order', '本单包邮权益') }}</li>
            <li>📈 {{ tt('This purchase counts toward your member tier', '本单消费计入会员等级进度') }}</li>
            <li>💅 {{ tt('Hot styles restock slowly — repurchase may be unavailable', '热门款式补货慢，之后未必能原价买回') }}</li>
          </ul>
        </div>
        <div style="text-align:center;padding:6px 0 2px">
          <button type="button" class="cf-still" @click="step = 2">
            {{ tt('Nothing above helps — I still want to cancel →', '以上解决不了我的问题，仍要取消 →') }}
          </button>
        </div>
      </div>

      <!-- 第 2 步：原因选择 -->
      <div v-else-if="step === 2" class="card" style="padding:22px">
        <h3 style="font-size:16px;margin-bottom:4px">{{ tt('What made you cancel?', '是什么让你想取消？') }}</h3>
        <p style="font-size:12.5px;color:var(--gray);margin-bottom:14px">{{ tt('Your answer helps us improve — and might unlock a better fix.', '告诉我们原因，也许有更好的解决办法。') }}</p>
        <div style="display:grid;gap:10px">
          <label
            v-for="r in REASONS" :key="r.k" class="cf-reason"
            :class="{ sel: picked === r.k }" @click="picked = r.k"
          >
            <span class="cf-radio"><span v-if="picked === r.k" /></span>
            <span style="font-size:17px;flex:none">{{ r.ico }}</span>
            <span style="flex:1;font-size:14px;font-weight:500">{{ tt(r.en, r.zh) }}</span>
            <span
              v-if="r.k === 'size' && returnable" class="tag tag-ship"
              style="flex:none;font-size:11px"
            >{{ tt('Free exchange', '可免费换') }}</span>
          </label>
        </div>
        <!-- 针对性挽留提示 -->
        <div v-if="picked" class="cf-hint">
          <template v-if="picked === 'size' && returnable">
            💡 {{ tt(HINT.size[0], HINT.size[1]) }}
            <button type="button" class="btn btn-secondary btn-sm" style="margin-left:8px" @click="goExchange">{{ tt('Go exchange →', '去换货 →') }}</button>
          </template>
          <template v-else-if="picked === 'price'">
            💡 {{ tt(HINT.price[0], HINT.price[1]) }}
            <router-link class="btn btn-secondary btn-sm" style="margin-left:8px" to="/contact">{{ tt('Try price match →', '申请保价 →') }}</router-link>
          </template>
          <template v-else>💡 {{ tt(HINT[picked][0], HINT[picked][1]) }}</template>
        </div>
        <div v-if="picked === 'other'" class="field" style="margin-top:12px">
          <label>{{ tt('Tell us more (optional)', '具体说说（选填）') }}</label>
          <textarea v-model="detail" class="input" rows="3" maxlength="200" style="height:auto;padding:10px 14px" :placeholder="tt('Anything we could do better…', '我们哪里可以做得更好…')" />
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:18px;gap:10px;flex-wrap:wrap">
          <button type="button" class="btn btn-ghost btn-sm" @click="step = 1">← {{ tt('Back', '返回') }}</button>
          <button type="button" class="cf-next" :class="{ ready: picked }" :disabled="!picked" @click="step = 3">
            {{ tt('Continue', '继续') }} →
          </button>
        </div>
      </div>

      <!-- 第 3 步：最终确认 -->
      <div v-else class="card" style="padding:22px">
        <h3 style="font-size:16px;margin-bottom:4px">{{ tt('Last check before cancelling', '最后确认一下') }}</h3>
        <p style="font-size:12.5px;color:var(--gray);margin-bottom:14px">
          {{ tt('Here is exactly what will happen:', '以下是取消后会发生的事，请确认：') }}
        </p>
        <ul class="cf-facts">
          <li v-if="isUnpaid">🧾 {{ tt('No payment was charged — nothing to refund.', '订单未支付，无扣款、无退款。') }}</li>
          <template v-else>
            <li>💳 {{ tt(`Refund ${money(o.grand_total)} to your original payment method`, `退款 ${money(o.grand_total)} 原路退回支付账户`) }}</li>
            <li>⏳ {{ tt('Refunds arrive within 5–10 business days (issuer dependent)', '到账约 5–10 个工作日（视发卡行而定）') }}</li>
            <li v-if="o.points_earned">⭐ {{ tt(`${o.points_earned} points from this order will be voided`, `本单 ${o.points_earned} 积分将作废`) }}</li>
            <li v-if="o.points_used">↩️ {{ tt(`${o.points_used} points used here will be returned`, `本单使用的 ${o.points_used} 积分将返还`) }}</li>
            <li>📦 {{ tt('Reserved stock goes back on sale — a repurchase may find it sold out', '占用的库存将重新上架，之后再买可能无货') }}</li>
          </template>
        </ul>
        <label class="cf-ack" :class="{ sel: acked }" @click.prevent="acked = !acked">
          <span class="cf-check">{{ acked ? '✓' : '' }}</span>
          <span style="font-size:13px">{{ tt("I understand the above and want to cancel this order.", '我已阅读并理解以上内容，确认取消该订单。') }}</span>
        </label>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:18px;gap:10px;flex-wrap:wrap">
          <button type="button" class="btn btn-ghost btn-sm" @click="step = 2">← {{ tt('Back', '返回') }}</button>
          <button
            type="button" class="cf-final" :class="{ arm: submitArm.is('go'), loading: submitting }"
            :disabled="!acked || submitting" @click="confirmBtn"
          >{{ submitArm.is('go') ? tt('Tap again to confirm cancel', '再点一次，确认取消') : tt('Confirm cancellation', '确认取消订单') }}</button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* 头部挽留横幅：柔和玫瑰渐变（对齐 AccountView 头卡风格） */
.cf-hero { padding: 22px; background: linear-gradient(135deg, var(--rose-pale), #fff 70%); }

/* 步骤条：圆点 + 文字 + 连接线；当前=梅紫实心，完成=绿勾 */
.cf-steps { display: flex; align-items: center; gap: 10px; margin-top: 18px; flex-wrap: wrap; }
.cf-step { display: flex; gap: 8px; align-items: center; font-size: 12.5px; font-weight: 600; color: var(--gray); }
.cf-step-dot { width: 26px; height: 26px; border-radius: 50%; background: var(--gray-light); color: var(--gray); display: inline-flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; transition: all .2s; }
.cf-step.on { color: var(--plum); }
.cf-step.on .cf-step-dot { background: var(--plum); color: #fff; box-shadow: 0 4px 12px rgba(138,74,99,.35); }
.cf-step.past { color: var(--success); }
.cf-step.past .cf-step-dot { background: var(--success); color: #fff; }
.cf-step-line { flex: 1; min-width: 24px; height: 2px; background: var(--gray-light); border-radius: 1px; }
.cf-step-line.on { background: var(--success); }

/* 替代方案卡：白卡 hover 上浮，icon 渐变气泡（对齐 newsletter-band news-ico） */
.cf-alt { display: flex; gap: 14px; align-items: flex-start; padding: 18px; text-align: left; cursor: pointer; border: 1.5px solid var(--gray-light); transition: transform .18s ease-out, box-shadow .18s ease-out, border-color .18s; font-family: inherit; width: 100%; }
.cf-alt:hover { transform: translateY(-3px); box-shadow: var(--shadow-pop); border-color: var(--rose); }
.cf-alt-ico { width: 44px; height: 44px; border-radius: 50%; flex: none; background: linear-gradient(135deg, var(--rose), var(--plum)); display: inline-flex; align-items: center; justify-content: center; font-size: 20px; box-shadow: 0 6px 16px rgba(232,180,184,.5); }
.cf-alt-cta { display: inline-block; margin-top: 6px; font-size: 12.5px; font-weight: 700; color: var(--plum); }

/* 保留权益清单 */
.cf-keep { padding: 16px 18px; background: #fff; }
.cf-keep-list { margin: 10px 0 0; padding-left: 4px; list-style: none; display: grid; gap: 6px; font-size: 13px; color: var(--ink); }

/* 「仍要取消」：刻意低调的灰色小字链（挽留出口不显眼，但可达） */
.cf-still { background: none; border: none; cursor: pointer; font-size: 12.5px; color: var(--gray); text-decoration: underline; text-underline-offset: 3px; padding: 8px 10px; }
.cf-still:hover { color: var(--plum); }

/* 原因单选卡（.setopt 加大型：圆形 radio + emoji + 角标） */
.cf-reason { display: flex; gap: 12px; align-items: center; border: 1.5px solid var(--gray-light); border-radius: 12px; padding: 13px 16px; cursor: pointer; background: #fff; transition: all .15s; }
.cf-reason:hover { border-color: var(--rose); }
.cf-reason.sel { border-color: var(--plum); background: var(--rose-pale); box-shadow: 0 4px 14px rgba(138,74,99,.12); }
.cf-radio { width: 20px; height: 20px; border-radius: 50%; border: 2px solid var(--gray-light); flex: none; display: inline-flex; align-items: center; justify-content: center; transition: border-color .15s; }
.cf-radio span { width: 10px; height: 10px; border-radius: 50%; background: var(--plum); }
.cf-reason.sel .cf-radio { border-color: var(--plum); }

/* 原因挽留提示条 */
.cf-hint { margin-top: 12px; padding: 11px 14px; border-radius: 10px; background: var(--rose-pale); color: var(--plum); font-size: 13px; display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }

/* 继续按钮：默认灰描边（弱化），选中原因后点亮梅紫实心 */
.cf-next { height: 40px; padding: 0 22px; border-radius: 10px; border: 1.5px solid var(--gray-light); background: #fff; color: var(--gray); font-size: 14px; font-weight: 600; cursor: not-allowed; transition: all .18s; }
.cf-next.ready { border-color: var(--plum); background: var(--plum); color: #fff; cursor: pointer; }
.cf-next.ready:hover { background: var(--plum-dark); transform: translateY(-1px); }

/* 确认事实清单 */
.cf-facts { margin: 0; padding: 14px 18px; list-style: none; display: grid; gap: 9px; font-size: 13.5px; background: var(--cream); border-radius: 12px; border: 1px dashed var(--gray-light); }

/* 确认勾选框 */
.cf-ack { display: flex; gap: 10px; align-items: center; margin-top: 14px; padding: 12px 14px; border-radius: 10px; border: 1.5px solid var(--gray-light); cursor: pointer; transition: all .15s; }
.cf-ack:hover { border-color: var(--rose); }
.cf-ack.sel { border-color: var(--plum); background: var(--rose-pale); }
.cf-check { width: 20px; height: 20px; border-radius: 6px; border: 2px solid var(--gray-light); flex: none; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; color: #fff; background: #fff; transition: all .15s; }
.cf-ack.sel .cf-check { background: var(--plum); border-color: var(--plum); }

/* 最终取消按钮：默认中性灰（刻意不抢眼），arm 态转红警示 */
.cf-final { height: 40px; padding: 0 22px; border-radius: 10px; border: 1.5px solid var(--gray-light); background: #fff; color: var(--gray); font-size: 14px; font-weight: 600; cursor: pointer; transition: all .18s; }
.cf-final:disabled { opacity: .55; cursor: not-allowed; }
.cf-final:not(:disabled):hover { border-color: var(--plum); color: var(--plum); }
.cf-final.arm { border-color: var(--error); color: var(--error); background: var(--pale-error, #FDE9EA); }

/* 成功面板 */
.cf-done-ico { width: 64px; height: 64px; border-radius: 50%; margin: 0 auto 14px; background: var(--success); color: #fff; font-size: 30px; font-weight: 700; display: flex; align-items: center; justify-content: center; box-shadow: 0 10px 26px rgba(62,189,147,.4); }

@media (max-width: 768px) {
  .cf-step span { display: none; } /* 步骤文字隐藏仅留圆点，防换行挤爆 */
  .cf-steps { gap: 6px; }
}
</style>
