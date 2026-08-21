/* 两段式确认（防误触）：首次点击进入 arm 态（按钮红字/文案切换），5s 无操作自动复位，二次点击才放行
 * 用法：
 *   const { armId, is, hit, reset } = useArmConfirm()
 *   <button :class="{ arm: is('del') }" @click="hit('del', doDelete)">
 *     {{ is('del') ? tt('Tap again to confirm', '再点一次确认') : tt('Delete', '删除') }}
 *   </button>
 */
import { onScopeDispose, ref } from 'vue'

export function useArmConfirm(ms = 5000) {
  const armId = ref(null)
  let timer = null

  function reset() {
    if (timer) { clearTimeout(timer); timer = null }
    armId.value = null
  }

  function is(id) { return armId.value === id }

  /* 命中 arm 态 → 复位并执行 action、返回 true；否则仅进入 arm 态、返回 false */
  function hit(id, action) {
    if (armId.value === id) {
      reset()
      if (typeof action === 'function') action()
      return true
    }
    reset()
    armId.value = id
    timer = setTimeout(reset, ms)
    return false
  }

  onScopeDispose(reset)
  return { armId, is, hit, reset }
}
