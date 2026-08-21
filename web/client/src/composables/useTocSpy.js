/* 政策页 TOC Scrollspy —— IntersectionObserver 观察 h2[id]，命中项 id 经 ref 暴露（模板绑 .on 高亮）
 * Privacy / Terms / ShippingPolicy / ReturnsPolicy 四页共用；
 * SSR 与无 IO 环境安全降级（不高亮，锚点点击跳转仍可用）
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

export function useTocSpy(ids) {
  const active = ref('')
  let io = null

  /* 触底兜底：末节标题可能永远进不了观测带（尾节太短），滚动触底时强制点亮末节 */
  function onScroll() {
    if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 4) {
      const last = [...(ids || [])].reverse().find(Boolean)
      if (last) active.value = last
    }
  }

  onMounted(() => {
    if (typeof window === 'undefined') return
    if ('IntersectionObserver' in window) {
      /* 观测带：避开 64px 吸顶头部 + 余量，取视口上部 ~35% —— 标题进入带内即视为当前小节 */
      io = new IntersectionObserver(
        (entries) => {
          for (const e of entries) {
            if (e.isIntersecting && e.target.id) active.value = e.target.id
          }
        },
        { rootMargin: '-96px 0px -65% 0px', threshold: 0 },
      )
      for (const id of ids || []) {
        const el = document.getElementById(id)
        if (el) io.observe(el)
      }
    }
    window.addEventListener('scroll', onScroll, { passive: true })
  })
  onBeforeUnmount(() => {
    if (io) io.disconnect()
    if (typeof window !== 'undefined') window.removeEventListener('scroll', onScroll)
  })

  return { active }
}
