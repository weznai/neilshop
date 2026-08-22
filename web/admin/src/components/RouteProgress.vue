<script setup>
/* 路由切换进度条：beforeEach 起条（跳 30% 再缓爬到 80%），afterEach/onError 走满 + 淡出复位 */
import { onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const width = ref(0)
const opacity = ref(0)
let timer = null
let timer2 = null

function clearTimers() {
  clearInterval(timer)
  clearTimeout(timer2)
  timer = null
  timer2 = null
}

/* 起条：先跳 ~30%，定时器缓慢增到 ~80%（宽度走 CSS transition 平滑过渡） */
function start() {
  clearTimers()
  opacity.value = 1
  width.value = 30
  timer = setInterval(() => {
    if (width.value < 80) width.value = Math.min(80, width.value + 2)
  }, 220)
}

/* 收尾：走满 100% 并淡出，300ms 后复位；未起条（query-only 变化）直接忽略 */
function finish() {
  clearTimers()
  if (!opacity.value) return
  width.value = 100
  opacity.value = 0
  timer2 = setTimeout(() => { width.value = 0 }, 300)
}

/* 同路由 query 变化不触发（to.path === from.path） */
const unBefore = router.beforeEach((to, from) => { if (to.path !== from.path) start() })
const unAfter = router.afterEach(finish)
const unError = router.onError(finish)

onBeforeUnmount(() => {
  clearTimers()
  unBefore()
  unAfter()
  unError()
})
</script>

<template>
  <div class="route-progress" :style="{ width: width + '%', opacity }"></div>
</template>

<style scoped>
.route-progress{position:fixed;top:0;left:0;height:2px;width:0;opacity:0;z-index:1000;background:linear-gradient(90deg,var(--rose),var(--plum));transition:width .25s ease-out,opacity .3s ease-out;pointer-events:none}
</style>
