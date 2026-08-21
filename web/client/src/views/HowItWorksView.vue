<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { dict, i18n } from '../i18n'

/* 步骤文案走 i18n 键（模板 i18n.t 渲染）；HowTo JSON-LD 主语言保持 EN，经 dict.en 直读键值 */
const STEPS = [
  ['1', 'how.s1t', 'how.s1d', '/size-guide', 'how.openGuide'],
  ['2', 'how.s2t', 'how.s2d'],
  ['3', 'how.s3t', 'how.s3d'],
  ['4', 'how.s4t', 'how.s4d'],
  ['5', 'how.s5t', 'how.s5d'],
  ['6', 'how.s6t', 'how.s6d'],
]

/* 步骤编号视口内依次点亮（IO 命中加 .lit，编号圈换品牌渐变 + popTick 脉冲；
 * prefers-reduced-motion 下全局规则已禁动画，仅保留状态色变化；无 IO 环境直接全亮） */
const stepRefs = ref([])
let io = null
onMounted(() => {
  if (typeof window === 'undefined' || !('IntersectionObserver' in window)) {
    stepRefs.value.forEach((el) => el && el.classList.add('lit'))
    return
  }
  io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) { e.target.classList.add('lit'); io.unobserve(e.target) }
      }
    },
    { threshold: 0.35 },
  )
  stepRefs.value.forEach((el) => el && io.observe(el))
})
onUnmounted(() => { if (io) io.disconnect() })

/* HowTo 结构化数据（gm:seo 事件通道，seo.js 统一注入 head）；name/text 固定 EN（SEO 主语言） */
onMounted(() => {
  try {
    window.dispatchEvent(new CustomEvent('gm:seo', { detail: { jsonLd: {
      '@context': 'https://schema.org',
      '@type': 'HowTo',
      name: 'How to apply GLOWMAG press-on nails',
      description: 'Apply salon-quality press-on nails at home in about 5 minutes.',
      step: STEPS.map((s) => ({ '@type': 'HowToStep', name: dict.en[s[1]], text: dict.en[s[2]] })),
    } } }))
  } catch (_) { /* SEO 失败不影响页面 */ }
})
</script>

<template>
  <section class="section">
    <div class="container">
      <div style="text-align:center;margin-bottom:34px">
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">{{ i18n.t('how.title') }}</h1>
        <p style="color:var(--gray)">{{ i18n.t('how.sub') }}</p>
      </div>
      <div class="grid grid-3 hiw-grid">
        <div v-for="s in STEPS" :key="s[0]" ref="stepRefs" class="card hiw-step" style="padding:22px">
          <div class="hiw-num">{{ s[0] }}</div>
          <b style="font-size:15px">{{ i18n.t(s[1]) }}</b>
          <p style="font-size:13.5px;color:var(--gray);margin-top:6px;line-height:1.7">{{ i18n.t(s[2]) }}</p>
          <router-link v-if="s[3]" :to="s[3]" class="btn btn-secondary btn-sm" style="margin-top:10px">{{ i18n.t(s[4]) }} →</router-link>
        </div>
      </div>

      <div class="card" style="padding:22px 24px;margin-top:22px;display:flex;gap:18px;align-items:center;flex-wrap:wrap">
        <div style="font-size:34px">👁️</div>
        <div style="flex:1;min-width:240px">
          <b>{{ i18n.t('how.lashT') }}</b>
          <p style="font-size:13.5px;color:var(--gray);margin-top:4px;line-height:1.7">
            {{ i18n.t('how.lashD') }}
          </p>
        </div>
        <router-link to="/store?cat=lashes" class="btn btn-primary btn-sm">{{ i18n.t('how.lashCta') }}</router-link>
      </div>

      <div style="text-align:center;margin-top:26px">
        <router-link to="/store" class="btn btn-primary btn-lg">{{ i18n.t('how.cta') }}</router-link>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 步骤编号：默认灰态，视口命中（.lit）点亮为品牌渐变 + popTick 脉冲（全局 keyframes；reduced-motion 全局禁用） */
.hiw-num { width: 52px; height: 52px; border-radius: 50%; background: var(--gray-light); color: var(--gray); display: inline-flex; align-items: center; justify-content: center; font-family: var(--font-title); font-size: 22px; font-weight: 700; margin-bottom: 12px; transition: background .3s ease-out, color .3s ease-out; }
.hiw-step.lit .hiw-num { background: linear-gradient(135deg, var(--rose), var(--plum)); color: #fff; animation: popTick .3s ease-out; }
/* 点亮卡片 rose-light 描边呼应编号圈 */
.hiw-step.lit { border-color: var(--rose-light); }

/* 桌面横向连接虚线（每行末卡不画；≤768px 两列布局隐藏） */
@media (min-width: 769px) {
  .hiw-step { position: relative; }
  .hiw-step:not(:nth-child(3n))::after {
    content: ""; position: absolute; top: 48px; right: -20px; width: 20px;
    border-top: 2px dashed var(--rose); z-index: 1;
  }
}

/* 超窄屏步骤卡单列（覆盖全局 .grid-3 三列） */
@media (max-width: 420px) {
  .hiw-grid.grid-3 { grid-template-columns: 1fr; }
}
</style>
