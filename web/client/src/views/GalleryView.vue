<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { req } from '../api/client'
import { i18n, tt } from '../i18n'
import { useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'

const zh = () => i18n.lang === 'zh'
const auth = useAuthStore()
const ui = useUiStore()
const shots = ref([])
const total = ref(0)
const page = ref(1)
const size = 12
const loading = ref(false)
const loaded = ref(false)
const loadErr = ref(false)
const lbIdx = ref(-1)
const moreErr = ref(false)

/* 投稿上墙弹窗（POST /api/content/ugc：image_url 必填 https，caption/instagram_handle 可选；
 * 采纳奖励 100 积分为后端常量 UGC_REWARD，登录投稿才有积分归属） */
const UGC_REWARD = 100
const postOpen = ref(false)
const posted = ref(false)
const posting = ref(false)
const postForm = ref({ image_url: '', handle: '', caption: '' })
const postErr = ref('')
const isHttps = (u) => /^https:\/\//i.test(u)

/* 图片链接预览：输入防抖 500ms 后挂 <img>，@load 置 ok / @error 置 bad；bad 态禁用提交 */
const previewUrl = ref('')
const pvState = ref('') /* '' 未校验 | loading | ok | bad */
let pvTimer = null
watch(() => postForm.value.image_url, (v) => {
  clearTimeout(pvTimer)
  const u = String(v || '').trim()
  if (!u || !isHttps(u)) { previewUrl.value = ''; pvState.value = ''; return }
  pvState.value = 'loading'
  previewUrl.value = ''
  pvTimer = setTimeout(() => { previewUrl.value = u }, 500)
})
onUnmounted(() => clearTimeout(pvTimer))
function pvLoad() { if (pvState.value === 'loading') pvState.value = 'ok' }
function pvError() { if (pvState.value === 'loading') pvState.value = 'bad' }

function openPost() {
  postErr.value = ''
  posted.value = false
  postOpen.value = true
}
function closePost() {
  if (posting.value) return
  postOpen.value = false
}
async function submitPost() {
  const url = postForm.value.image_url.trim()
  const handle = postForm.value.handle.trim()
  const caption = postForm.value.caption.trim()
  postErr.value = ''
  if (!url) { postErr.value = tt('Image URL is required', '请填写图片链接'); return }
  if (pvState.value === 'bad') { postErr.value = tt('This image URL cannot be loaded — check the link and try again', '该图片链接无法加载，请检查后重试'); return }
  if (!isHttps(url)) { postErr.value = tt('Image URL must start with https://', '图片链接必须以 https:// 开头'); return }
  posting.value = true
  try {
    await req('POST', '/api/content/ugc', {
      image_url: url,
      instagram_handle: handle || null,
      caption: caption || null,
    })
    /* 提交成功不关弹窗：切换成功视图（审核时长 / 积分说明 / 未登录提示） */
    postForm.value = { image_url: '', handle: '', caption: '' }
    pvState.value = ''
    previewUrl.value = ''
    posted.value = true
  } catch (e) {
    ui.toast(tt('Submit failed, please try again', '提交失败，请稍后再试'), 'error')
  } finally {
    posting.value = false
  }
}

/* page 只在请求成功后推进（失败不跳页、不清空已有列表，对齐 BlogView） */
async function load(reset) {
  if (loading.value) return
  loading.value = true
  moreErr.value = false
  if (reset) loadErr.value = false
  const target = reset ? 1 : page.value + 1
  try {
    const d = await req('GET', `/api/content/ugc?page=${target}&size=${size}`)
    shots.value = reset ? (d.items || []) : shots.value.concat(d.items || [])
    total.value = d.total || 0
    page.value = target
  } catch (_) {
    if (reset) { shots.value = []; loadErr.value = true }
    else moreErr.value = true
  } finally {
    loading.value = false
    loaded.value = true
  }
}
onMounted(() => load(true))

const hasMore = () => shots.value.length < total.value
function more() { load(false) }

/* 大数字 count-up：进入视口（IO）+ 数据就绪后 900ms ease-out 滚动；
 * prefers-reduced-motion 直出终值；无 IO 环境挂载即出 */
const countWrap = ref(null)
const displayCount = ref(0)
let countSeen = false
let cuRaf = 0
function tryCount() {
  if (!countSeen || !total.value || cuRaf) return
  const target = total.value
  const reduce = typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (reduce) { displayCount.value = target; return }
  const t0 = performance.now()
  const tick = (now) => {
    const p = Math.min(1, (now - t0) / 900)
    displayCount.value = Math.round(target * (1 - Math.pow(1 - p, 3)))
    if (p < 1) cuRaf = requestAnimationFrame(tick)
    else cuRaf = 0
  }
  cuRaf = requestAnimationFrame(tick)
}
watch(total, tryCount)
let cIo = null
onMounted(() => {
  if (typeof window === 'undefined' || !('IntersectionObserver' in window) || !countWrap.value) {
    countSeen = true; tryCount(); return
  }
  cIo = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) { countSeen = true; cIo.disconnect(); tryCount() }
  }, { threshold: 0.3 })
  cIo.observe(countWrap.value)
})
onUnmounted(() => {
  if (cIo) cIo.disconnect()
  if (cuRaf) cancelAnimationFrame(cuRaf)
})

/* 灯箱 / 投稿弹窗打开时经 ui store 汇报（body 滚动锁由 StoreLayout 统一 watch anyOverlay 处理） */
watch(() => lbIdx.value >= 0 || postOpen.value, (v) => { ui.lightboxOpen = v })
onUnmounted(() => { ui.lightboxOpen = false })

function openLb(i) { lbIdx.value = i }
function lbPrev() { if (lbIdx.value > 0) lbIdx.value-- }
function lbNext() { if (lbIdx.value < shots.value.length - 1) lbIdx.value++ }
function onKey(e) {
  if (postOpen.value) { if (e.key === 'Escape') closePost(); return }
  if (lbIdx.value < 0) return
  if (e.key === 'Escape') lbIdx.value = -1
  if (e.key === 'ArrowLeft') lbPrev()
  if (e.key === 'ArrowRight') lbNext()
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))

/* 移动端灯箱触摸滑动：位移 >40px 且横向大于纵向判定翻页（左滑下一张 / 右滑上一张） */
const tsX = ref(0)
const tsY = ref(0)
function lbTs(e) { const t = e.changedTouches[0]; tsX.value = t.clientX; tsY.value = t.clientY }
function lbTe(e) {
  if (lbIdx.value < 0) return
  const t = e.changedTouches[0]
  const dx = t.clientX - tsX.value
  const dy = t.clientY - tsY.value
  if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) (dx < 0 ? lbNext : lbPrev)()
}

/* 成功加载且无数据时的占位示例卡（不可点开灯箱；加载失败走错误卡） */
const usingSeed = computed(() => !loadErr.value && !shots.value.length)
const SEED = Array.from({ length: 8 }, (_, i) => ({
  image_url: `https://placehold.co/300x300/F5D8DA/6D2E46?text=Look+${i + 1}`,
  instagram_handle: '@glowmag_fan',
  product: null,
}))
/* 兜底占位：dataset 守卫防循环（对齐 HomeView heroFallback） */
const IMG_FALLBACK = 'https://placehold.co/300x300/E8B4B8/552338?text=%E2%9C%A8'
function imgFallback(e) {
  const img = e.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = IMG_FALLBACK
}
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head">
        <h1 class="section-title">#GLOWMAGGlam</h1>
        <button class="section-link" style="border:none;background:none;cursor:pointer;font:inherit;padding:0" @click="openPost">
          {{ tt('Share your look →', '投稿上墙 →') }}
        </button>
      </div>
      <div ref="countWrap" class="g-count">
        <template v-if="total">
          <b class="g-count-n">{{ displayCount.toLocaleString() }}</b>
          <span>{{ tt('community looks — tap any shot to shop it', '社区穿搭 — 点击图片查看大图') }}</span>
        </template>
        <template v-else>
          <span>{{ tt('Real looks from the community — yours could be next', '真实社区穿搭——欢迎投稿你的第一张') }}</span>
        </template>
      </div>
      <div class="g-masonry">
        <template v-if="!loaded">
          <div v-for="i in 8" :key="'sk' + i" class="skeleton g-sk"></div>
        </template>
        <div v-else-if="loadErr" class="card" style="padding:48px;text-align:center">
          <div style="font-size:36px;margin-bottom:8px">💅</div>
          <b>{{ tt('Failed to load the gallery', '买家秀加载失败') }}</b>
          <p style="font-size:13.5px;color:var(--gray);margin:6px 0 14px">
            {{ tt('Check your network and try again — community looks are waiting.', '请检查网络后重试，社区穿搭都在等你。') }}
          </p>
          <button class="btn btn-primary btn-sm" :class="{ loading }" :disabled="loading" @click="load(true)">{{ tt('Retry', '重试') }}</button>
        </div>
        <template v-else>
          <div
            v-for="(u, i) in usingSeed ? SEED : shots" :key="u.id || i"
            class="card g-shot"
          >
          <div class="shot-wrap" :style="{ cursor: usingSeed ? 'default' : 'zoom-in' }" @click="!usingSeed && openLb(i)">
            <img class="shot-img" :src="u.image_url" :alt="(u.instagram_handle || 'Glowmag Fan') + ' wearing GLOWMAG nails'" loading="lazy" @error="imgFallback">
            <span v-if="usingSeed" class="ontag tl">{{ tt('Sample', '示例图') }}</span>
            <span v-if="u.instagram_handle" class="ontag bl">On {{ u.instagram_handle }}</span>
            <span v-if="u.caption" class="shot-cap" style="position:absolute;inset:auto 0 0 0;padding:26px 12px 10px;background:linear-gradient(transparent,rgba(31,27,30,.72));color:#fff;font-size:12px;line-height:1.4">
              {{ u.caption.slice(0, 60) }}{{ u.caption.length > 60 ? '…' : '' }}
            </span>
          </div>
          <div v-if="u.product" style="padding:12px 14px;font-size:12.5px;display:flex;justify-content:space-between;align-items:center;gap:8px">
            <span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ u.product.title }}</span>
            <router-link
              class="btn btn-secondary btn-sm" style="font-size:11px;flex:none"
              :to="`/product?slug=${encodeURIComponent(u.product.slug)}`"
            >{{ tt('Shop', '去购买') }} →</router-link>
          </div>
          </div>
        </template>
      </div>
      <div v-if="hasMore()" style="text-align:center;margin-top:26px">
        <button class="btn btn-secondary" :class="{ loading }" :disabled="loading" @click="more">
          {{ moreErr ? tt('Retry load more', '重试加载') : tt(`Load more (${total - shots.length} left)`, `加载更多（还有 ${total - shots.length} 条）`) }}
        </button>
        <p v-if="moreErr" style="font-size:12.5px;color:var(--error);margin-top:8px">
          {{ tt('Failed to load more — tap to retry, no shots skipped.', '加载失败——点击重试，不会跳过任何内容。') }}
        </p>
      </div>
      <div style="text-align:center;margin-top:26px">
        <button class="btn btn-primary" @click="openPost">{{ tt('📸 Submit your look', '📸 投稿上墙') }}</button>
      </div>
    </div>
  </section>

  <!-- 投稿上墙弹窗（提交成功切换成功视图，不关弹窗） -->
  <div v-if="postOpen" class="g-lb" style="padding:20px" @click.self="closePost">
    <div class="card" style="max-width:420px;width:100%;padding:22px;text-align:left;max-height:86vh;overflow:auto">
      <!-- 成功视图 -->
      <template v-if="posted">
        <div class="pv-done">
          <div class="pv-done-ico">✅</div>
          <b class="pv-done-t">{{ tt('Submitted for review!', '投稿成功！') }}</b>
          <p class="pv-done-p">
            {{ tt(
              `Your photo is in the review queue — moderation takes about 3 days. Once it hits the wall, the ${UGC_REWARD} Glow Point reward lands in your account automatically.`,
              `照片已进入审核队列，审核约需 3 天；通过上墙后，采纳奖励 ${UGC_REWARD} 积分将自动入账。`,
            ) }}
          </p>
          <p v-if="!auth.isLoggedIn" class="pv-done-warn">
            {{ tt(
              `You're not logged in — rewards need an account to land in. Log in before your next submit to earn the ${UGC_REWARD} points.`,
              `当前未登录——积分入账需要账户。下次投稿前先登录，才能拿到 ${UGC_REWARD} 积分奖励。`,
            ) }}
          </p>
          <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:6px">
            <button class="btn btn-secondary btn-sm" @click="posted = false">{{ tt('Submit another', '再投一张') }}</button>
            <button class="btn btn-primary btn-sm" @click="closePost">{{ tt('Browse the wall', '去逛买家秀') }}</button>
          </div>
        </div>
      </template>
      <!-- 表单视图 -->
      <template v-else>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
          <b style="font-family:var(--font-title);font-size:19px">{{ tt('Share your look', '投稿上墙') }}</b>
          <button class="g-lb-x" style="position:static;width:32px;height:32px;font-size:18px" :aria-label="tt('Close', '关闭')" @click="closePost">×</button>
        </div>
        <p style="font-size:12.5px;color:var(--gray);margin:0 0 14px">
          {{ tt(`Post a photo of your GLOWMAG nails — after review it may be featured on the wall. Featured looks earn ${UGC_REWARD} Glow Points.`, `晒出你的 GLOWMAG 美甲，审核通过后即可上墙；被采纳奖励 ${UGC_REWARD} 积分。`) }}
          <span v-if="!auth.isLoggedIn">{{ tt('Log in before submitting so the reward lands in your account.', '建议先登录再投稿，积分才能入账。') }}</span>
        </p>
        <label style="display:block;font-size:12.5px;font-weight:700;margin-bottom:4px">{{ tt('Image URL (https, required)', '图片链接（https，必填）') }}</label>
        <input v-model="postForm.image_url" class="input" style="width:100%;margin-bottom:10px" placeholder="https://…" :disabled="posting">
        <div v-if="pvState" class="pv-box">
          <img v-if="previewUrl" :src="previewUrl" :alt="tt('Image preview', '图片预览')" @load="pvLoad" @error="pvError">
          <span v-if="pvState === 'loading'" class="pv-msg">{{ tt('Checking preview…', '正在检查图片…') }}</span>
          <span v-else-if="pvState === 'bad'" class="pv-msg" style="color:var(--error)">
            {{ tt("Couldn't load this URL — check the link and try again.", '该链接无法加载——请检查后重试。') }}
          </span>
        </div>
        <label style="display:block;font-size:12.5px;font-weight:700;margin:10px 0 4px">{{ tt('Social handle (optional)', '社交账号句柄（选填）') }}</label>
        <input v-model="postForm.handle" class="input" style="width:100%;margin-bottom:12px" placeholder="@yourhandle" maxlength="60" :disabled="posting">
        <label style="display:block;font-size:12.5px;font-weight:700;margin-bottom:4px">{{ tt('Caption (optional)', '文案（选填）') }}</label>
        <textarea v-model="postForm.caption" class="input" style="width:100%;margin-bottom:6px;min-height:70px;resize:vertical" maxlength="200" :disabled="posting" />
        <p v-if="postErr" style="font-size:12.5px;color:var(--error);margin:0 0 8px">{{ postErr }}</p>
        <button class="btn btn-primary btn-block" :class="{ loading: posting }" :disabled="posting || pvState === 'bad'" @click="submitPost">
          {{ tt('Submit for review', '提交审核') }}
        </button>
      </template>
    </div>
  </div>

  <div
    v-if="lbIdx >= 0 && shots[lbIdx]" class="g-lb"
    @click.self="lbIdx = -1"
    @touchstart.passive="lbTs"
    @touchend.passive="lbTe"
  >
    <button class="g-lb-x" :aria-label="tt('Close', '关闭')" @click="lbIdx = -1">×</button>
    <button v-if="lbIdx > 0" class="g-lb-nav prev" :aria-label="tt('Previous', '上一张')" @click="lbPrev">‹</button>
    <figure @click.self="lbIdx = -1">
      <img :src="shots[lbIdx].image_url" :alt="shots[lbIdx].instagram_handle || 'GLOWMAG look'" @error="imgFallback">
      <figcaption v-if="shots[lbIdx].caption || shots[lbIdx].instagram_handle">
        <b v-if="shots[lbIdx].instagram_handle">{{ shots[lbIdx].instagram_handle }}</b>
        <span v-if="shots[lbIdx].caption">{{ shots[lbIdx].caption }}</span>
        <router-link
          v-if="shots[lbIdx].product"
          class="btn btn-primary btn-sm" style="margin-top:8px"
          :to="`/product?slug=${encodeURIComponent(shots[lbIdx].product.slug)}`"
          @click="lbIdx = -1"
        >{{ tt('Shop this look', '购买同款') }} · {{ shots[lbIdx].product.title }}</router-link>
      </figcaption>
    </figure>
    <button v-if="lbIdx < shots.length - 1" class="g-lb-nav next" :aria-label="tt('Next', '下一张')" @click="lbNext">›</button>
    <span class="g-lb-count">{{ lbIdx + 1 }} / {{ shots.length }}</span>
  </div>
</template>

<style scoped>
.g-sk { aspect-ratio: 1; border-radius: 12px; }

/* 计数行：font-title 40px plum 大数字 */
.g-count { display: flex; align-items: baseline; justify-content: center; gap: 12px; text-align: center; color: var(--gray); margin-bottom: 26px; font-size: 14px; }
.g-count-n { font-family: var(--font-title); font-size: 40px; font-weight: 700; color: var(--plum); line-height: 1; font-variant-numeric: tabular-nums; }

/* 桌面 CSS columns 瀑布流（≤768px 保持 2 列） */
.g-masonry { columns: 4 240px; column-gap: 16px; }
.g-shot { break-inside: avoid; margin-bottom: 16px; width: 100%; animation: gIn .35s ease-out both; }
@keyframes gIn { from { opacity: 0; } }
.g-shot:hover { transform: translateY(-4px); box-shadow: var(--shadow-pop); transition: transform .2s ease-out, box-shadow .2s ease-out; }
.shot-wrap { position: relative; overflow: hidden; }
.shot-img { width: 100%; height: auto; display: block; transition: transform .35s ease-out; }
.g-shot:hover .shot-img { transform: scale(1.04); }
/* caption 渐变条：hover 设备上悬停浮现，触屏设备常显 */
@media (hover: hover) {
  .shot-cap { opacity: 0; transition: opacity .2s ease-out; }
  .g-shot:hover .shot-cap { opacity: 1; }
}
@media (max-width: 768px) {
  .g-masonry { columns: 2; column-gap: 12px; }
  .g-shot { margin-bottom: 12px; }
}

/* 投稿弹窗图片预览 */
.pv-box { border: 1.5px dashed var(--gray-light); border-radius: 12px; background: var(--cream); min-height: 120px; max-height: 240px; display: flex; align-items: center; justify-content: center; overflow: hidden; margin-bottom: 4px; }
.pv-box img { max-width: 100%; max-height: 220px; object-fit: contain; }
.pv-msg { font-size: 12.5px; color: var(--gray); padding: 12px; text-align: center; }

/* 投稿成功视图：大 ✅ + 审核时长/积分说明 + 未登录提示 */
.pv-done { text-align: center; padding: 18px 4px 8px; }
.pv-done-ico { font-size: 52px; line-height: 1; margin-bottom: 14px; }
.pv-done-t { display: block; font-family: var(--font-title); font-size: 21px; color: var(--plum); margin-bottom: 10px; }
.pv-done-p { font-size: 13.5px; color: var(--gray); line-height: 1.7; margin: 0 0 10px; }
.pv-done-warn { font-size: 12.5px; color: var(--gold); background: var(--cream); border: 1px solid var(--gray-light); border-radius: 10px; padding: 8px 12px; margin: 0 0 14px; line-height: 1.6; }

/* 图片上角标：毛玻璃底（半透明 + backdrop 模糊），示例/句柄统一 */
.ontag { position: absolute; color: #fff; font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 999px; background: rgba(31,27,30,.38); backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px); letter-spacing: .2px; }
.ontag.tl { top: 10px; left: 10px; }
.ontag.bl { bottom: 10px; left: 10px; }
@supports not (backdrop-filter: blur(1px)) { .ontag { background: rgba(0,0,0,.55); } }

.g-lb { position: fixed; inset: 0; z-index: 320; background: rgba(31,27,30,.85); display: flex; align-items: center; justify-content: center; padding: 48px 64px; animation: popIn .2s ease-out; }
.g-lb figure { display: flex; flex-direction: column; align-items: center; gap: 14px; max-width: min(84vw, 640px); }
.g-lb img { max-width: 100%; max-height: 66vh; border-radius: 14px; object-fit: contain; box-shadow: var(--shadow-pop); }
.g-lb figcaption { color: rgba(255,255,255,.9); font-size: 13.5px; text-align: center; display: grid; gap: 4px; justify-items: center; }
.g-lb-x { position: absolute; top: 18px; right: 22px; width: 40px; height: 40px; border-radius: 50%; background: rgba(255,255,255,.14); color: #fff; font-size: 24px; }
.g-lb-x:hover { background: rgba(255,255,255,.28); }
.g-lb-nav { position: absolute; top: 50%; transform: translateY(-50%); width: 46px; height: 46px; border-radius: 50%; background: rgba(255,255,255,.12); color: #fff; font-size: 30px; line-height: 1; }
.g-lb-nav:hover { background: rgba(255,255,255,.26); }
.g-lb-nav.prev { left: 14px; }
.g-lb-nav.next { right: 14px; }
.g-lb-count { position: absolute; bottom: 18px; left: 50%; transform: translateX(-50%); color: rgba(255,255,255,.75); font-size: 12.5px; letter-spacing: 1px; }
@media (max-width: 640px) {
  .g-lb { padding: 48px 12px; }
  .g-lb-nav { display: none; }
}
</style>
