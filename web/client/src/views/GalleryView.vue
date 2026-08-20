<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { req } from '../api/client'
import { i18n } from '../i18n'
import { useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'

const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)
const zh = () => i18n.lang === 'zh'
const auth = useAuthStore()
const ui = useUiStore()
const shots = ref([])
const total = ref(0)
const page = ref(1)
const size = 12
const loading = ref(false)
const loaded = ref(false)
const lbIdx = ref(-1)

/* 投稿上墙弹窗（POST /api/content/ugc：image_url 必填 https，caption/instagram_handle 可选；
 * 采纳奖励 100 积分为后端常量 UGC_REWARD，登录投稿才有积分归属） */
const UGC_REWARD = 100
const postOpen = ref(false)
const posting = ref(false)
const postForm = ref({ image_url: '', handle: '', caption: '' })
const postErr = ref('')
const isHttps = (u) => /^https:\/\//i.test(u)

function openPost() {
  postErr.value = ''
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
  if (!isHttps(url)) { postErr.value = tt('Image URL must start with https://', '图片链接必须以 https:// 开头'); return }
  posting.value = true
  try {
    await req('POST', '/api/content/ugc', {
      image_url: url,
      instagram_handle: handle || null,
      caption: caption || null,
    })
    ui.toast(
      tt(`Submitted! After review it may hit the wall — featured looks earn ${UGC_REWARD} Glow Points 💅`, `投稿成功！审核通过后上墙，采纳奖励 ${UGC_REWARD} 积分 💅`),
      'success',
    )
    postForm.value = { image_url: '', handle: '', caption: '' }
    postOpen.value = false
  } catch (e) {
    ui.toast(tt('Submit failed, please try again', '提交失败，请稍后再试'), 'error')
  } finally {
    posting.value = false
  }
}

async function load(reset) {
  if (loading.value) return
  loading.value = true
  if (reset) { page.value = 1; shots.value = [] }
  try {
    const d = await req('GET', `/api/content/ugc?page=${page.value}&size=${size}`)
    shots.value = reset ? (d.items || []) : shots.value.concat(d.items || [])
    total.value = d.total || 0
  } catch (_) { if (reset) shots.value = [] }
  loading.value = false
  loaded.value = true
}
onMounted(() => load(true))

const hasMore = () => shots.value.length < total.value
function more() { page.value++; load(false) }

/* 灯箱 / 弹窗打开时锁 body 滚动，关闭恢复 */
const overlayCount = computed(() => (lbIdx.value >= 0 ? 1 : 0) + (postOpen.value ? 1 : 0))
watch(overlayCount, (n) => {
  if (typeof document === 'undefined') return
  document.body.style.overflow = n > 0 ? 'hidden' : ''
})
onUnmounted(() => { if (typeof document !== 'undefined') document.body.style.overflow = '' })

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

/* API 无数据时的占位示例卡（不可点开灯箱） */
const usingSeed = computed(() => !shots.value.length)
const SEED = Array.from({ length: 8 }, (_, i) => ({
  image_url: `https://placehold.co/300x300/F5D8DA/6D2E46?text=Look+${i + 1}`,
  instagram_handle: '@glowmag_fan',
  product: null,
}))
function esc(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }
function imgFallback(e) { e.target.src = 'https://placehold.co/300x300/E8B4B8/552338?text=%E2%9C%A8' }
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head">
        <h2 class="section-title">#GLOWMAGGlam</h2>
        <button class="section-link" style="border:none;background:none;cursor:pointer;font:inherit;padding:0" @click="openPost">
          {{ tt('Share your look →', '投稿上墙 →') }}
        </button>
      </div>
      <p style="text-align:center;color:var(--gray);margin-bottom:26px">
        <template v-if="total">{{ total.toLocaleString() }} {{ tt('community looks — tap any shot to shop it', '社区穿搭 — 点击图片查看大图') }}</template>
        <template v-else>{{ tt('Real looks from the community — yours could be next', '真实社区穿搭——欢迎投稿你的第一张') }}</template>
      </p>
      <div class="grid grid-4">
        <template v-if="!loaded">
          <div v-for="i in 8" :key="'sk' + i" class="g-sk"></div>
        </template>
        <template v-else>
          <div
            v-for="(u, i) in usingSeed ? SEED : shots" :key="u.id || i"
            class="shot card g-shot" style="padding:0;overflow:hidden;animation:fadeUp .35s both"
          >
          <div style="position:relative;aspect-ratio:1" :style="{ cursor: usingSeed ? 'default' : 'zoom-in' }" @click="!usingSeed && openLb(i)">
            <img :src="u.image_url" :alt="(u.instagram_handle || 'Glowmag Fan') + ' wearing GLOWMAG nails'" loading="lazy" style="width:100%;height:100%;object-fit:cover" @error="imgFallback">
            <span v-if="usingSeed" class="ontag" style="position:absolute;top:10px;left:10px;background:rgba(0,0,0,.45);color:#fff;font-size:11px;padding:3px 9px;border-radius:999px">
              {{ tt('Sample', '示例图') }}
            </span>
            <span v-if="u.instagram_handle" class="ontag" style="position:absolute;bottom:10px;left:10px;background:rgba(0,0,0,.45);color:#fff;font-size:11px;padding:3px 9px;border-radius:999px">
              On {{ esc(u.instagram_handle) }}
            </span>
            <span v-if="u.caption" style="position:absolute;inset:auto 0 0 0;padding:26px 12px 10px;background:linear-gradient(transparent,rgba(31,27,30,.72));color:#fff;font-size:12px;line-height:1.4">
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
        <button class="btn btn-secondary" :disabled="loading" @click="more">
          {{ tt(`Load more (${total - shots.length} left)`, `加载更多（还有 ${total - shots.length} 条）`) }}
        </button>
      </div>
      <div style="text-align:center;margin-top:26px">
        <button class="btn btn-primary" @click="openPost">{{ tt('📸 Submit your look', '📸 投稿上墙') }}</button>
      </div>
    </div>
  </section>

  <!-- 投稿上墙弹窗 -->
  <div v-if="postOpen" class="g-lb" style="padding:20px" @click.self="closePost">
    <div class="card" style="max-width:420px;width:100%;padding:22px;text-align:left;max-height:86vh;overflow:auto">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <b style="font-family:var(--font-title);font-size:19px">{{ tt('Share your look', '投稿上墙') }}</b>
        <button class="g-lb-x" style="position:static;width:32px;height:32px;font-size:18px" :aria-label="tt('Close', '关闭')" @click="closePost">×</button>
      </div>
      <p style="font-size:12.5px;color:var(--gray);margin:0 0 14px">
        {{ tt(`Post a photo of your GLOWMAG nails — after review it may be featured on the wall. Featured looks earn ${UGC_REWARD} Glow Points.`, `晒出你的 GLOWMAG 美甲，审核通过后即可上墙；被采纳奖励 ${UGC_REWARD} 积分。`) }}
        <span v-if="!auth.isLoggedIn">{{ tt('Log in before submitting so the reward lands in your account.', '建议先登录再投稿，积分才能入账。') }}</span>
      </p>
      <label style="display:block;font-size:12.5px;font-weight:700;margin-bottom:4px">{{ tt('Image URL (https, required)', '图片链接（https，必填）') }}</label>
      <input v-model="postForm.image_url" class="input" style="width:100%;margin-bottom:12px" placeholder="https://…" :disabled="posting">
      <label style="display:block;font-size:12.5px;font-weight:700;margin-bottom:4px">{{ tt('Social handle (optional)', '社交账号句柄（选填）') }}</label>
      <input v-model="postForm.handle" class="input" style="width:100%;margin-bottom:12px" placeholder="@yourhandle" maxlength="60" :disabled="posting">
      <label style="display:block;font-size:12.5px;font-weight:700;margin-bottom:4px">{{ tt('Caption (optional)', '文案（选填）') }}</label>
      <textarea v-model="postForm.caption" class="input" style="width:100%;margin-bottom:6px;min-height:70px;resize:vertical" maxlength="200" :disabled="posting" />
      <p v-if="postErr" style="font-size:12.5px;color:var(--error);margin:0 0 8px">{{ postErr }}</p>
      <button class="btn btn-primary btn-block" :class="{ loading: posting }" :disabled="posting" @click="submitPost">
        {{ tt('Submit for review', '提交审核') }}
      </button>
    </div>
  </div>

  <div v-if="lbIdx >= 0 && shots[lbIdx]" class="g-lb" @click.self="lbIdx = -1">
    <button class="g-lb-x" :aria-label="tt('Close', '关闭')" @click="lbIdx = -1">×</button>
    <button v-if="lbIdx > 0" class="g-lb-nav prev" :aria-label="tt('Previous', '上一张')" @click="lbPrev">‹</button>
    <figure @click.self="lbIdx = -1">
      <img :src="shots[lbIdx].image_url" :alt="shots[lbIdx].instagram_handle || 'GLOWMAG look'" @error="imgFallback">
      <figcaption v-if="shots[lbIdx].caption || shots[lbIdx].instagram_handle">
        <b v-if="shots[lbIdx].instagram_handle">{{ esc(shots[lbIdx].instagram_handle) }}</b>
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
.g-sk { aspect-ratio: 1; border-radius: 12px; background: linear-gradient(100deg, var(--gray-light) 40%, #f7f3f5 50%, var(--gray-light) 60%); background-size: 200% 100%; animation: gSk 1.2s infinite; }
@keyframes gSk { to { background-position: -200% 0; } }
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
