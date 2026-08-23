/* 列表页筛选/分页 URL 同步：setup 时从 route.query 回填 state，之后 deep watch state 变化 → 清洗后 router.replace 写回 URL */
import { watch, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'

export function useQuerySync(state, opts = {}) {
  const route = useRoute()
  const router = useRouter()
  const nums = opts.nums || []
  const defaults = opts.defaults || {}
  const keys = Object.keys(state)
  /* 初始 state 快照：外部导航清掉 query 键时回落到该默认（defaults 显式声明优先） */
  const init = { ...state }
  /* setup 时记录本页路由名：导航离开本页时（卸载前最后一次 route 变更）query 键变空，
   * 不应触发回填/onPop（否则 LogsView 等会发幽灵请求） */
  const selfRoute = route.name

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

  /* 外部导航（浏览器回退/前进）导致 query 变化：归一化后与 state 不一致才应用回 state，
   * 并回调 opts.onPop 触发一次 load（未传则仅同步 state，现有使用方行为不变）。
   * 防回环：应用后上面 deep watch 触发的 replace 因 query 已相同 → changed=false 为 no-op */
  const stopQ = watch(
    () => keys.map((k) => String(route.query[k] ?? '')).join('\n'),
    () => {
      /* 已离开本页（route.name 已变）：忽略，防幽灵回填/onPop */
      if (route.name !== selfRoute) return
      let touched = false
      for (const k of keys) {
        let v = route.query[k]
        if (Array.isArray(v)) v = v[0]
        if (v === undefined || v === '') {
          /* query 键被清掉（回退到无筛选态）：state 回落默认值 */
          const def = defaults[k] != null ? defaults[k] : init[k]
          if (String(state[k]) !== String(def)) { state[k] = def; touched = true }
          continue
        }
        if (nums.includes(k)) {
          /* 数字键同初始回填口径：仅接受 >=1 整数，非法值忽略 */
          const n = Number(v)
          if (!Number.isInteger(n) || n < 1) continue
          if (state[k] !== n) { state[k] = n; touched = true }
        } else if (state[k] !== v) {
          state[k] = v
          touched = true
        }
      }
      if (touched) opts.onPop?.()
    }
  )
  onBeforeUnmount(() => { stop(); stopQ() })
}
