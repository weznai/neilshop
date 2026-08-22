/* 列表页筛选/分页 URL 同步：setup 时从 route.query 回填 state，之后 deep watch state 变化 → 清洗后 router.replace 写回 URL */
import { watch, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'

export function useQuerySync(state, opts = {}) {
  const route = useRoute()
  const router = useRouter()
  const nums = opts.nums || []
  const defaults = opts.defaults || {}
  const keys = Object.keys(state)

  /* 初始回填：query 有值才覆盖（数组取首项），数字键转 Number */
  for (const k of keys) {
    let v = route.query[k]
    if (Array.isArray(v)) v = v[0]
    if (v === undefined || v === '') continue
    if (nums.includes(k)) {
      /* 页码等数字键仅接受 >=1 的整数（0/负数/NaN/小数忽略，保留默认值） */
      const n = Number(v)
      if (Number.isInteger(n) && n >= 1) state[k] = n
    } else {
      state[k] = v
    }
  }

  const stop = watch(
    state,
    () => {
      const q = {}
      let changed = false
      /* 保留 state 之外的现有 query 键（如 order-detail 的 id） */
      for (const [k, v] of Object.entries(route.query)) {
        if (!keys.includes(k)) q[k] = v
      }
      /* 仅写入非空且 ≠ 默认值的键 */
      for (const k of keys) {
        const v = state[k]
        if (v === '' || v == null || v === defaults[k]) {
          if (route.query[k] !== undefined) changed = true
          continue
        }
        const sv = String(v)
        if (route.query[k] !== sv) changed = true
        q[k] = sv
      }
      if (changed) router.replace({ query: q })
    },
    { deep: true }
  )
  onBeforeUnmount(stop)
}
