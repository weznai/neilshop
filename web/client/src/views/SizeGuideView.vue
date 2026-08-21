<script setup>
import { computed, ref, watch } from 'vue'
import { i18n } from '../i18n'

/* 选中尺码持久化（再次进入回显；清除时移除键） */
function lsGet(k) { try { return localStorage.getItem(k) } catch (_) { return null } }
function lsSet(k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v) } catch (_) { /* 隐私模式忽略 */ } }
const saved = parseInt(lsGet('gm_size_pick'), 10)
const picked = ref(!isNaN(saved) && saved >= 0 && saved <= 9 ? saved : -1)
watch(picked, (v) => { lsSet('gm_size_pick', v >= 0 ? String(v) : null) })

/* 单位切换持久化（gm_size_unit） */
const unit = ref(lsGet('gm_size_unit') === 'in' ? 'in' : 'mm')
watch(unit, (v) => lsSet('gm_size_unit', v))

const SIZES = [
  [0, 5.5, 3.5], [1, 6.0, 3.8], [2, 6.5, 4.0], [3, 7.0, 4.3], [4, 7.5, 4.5],
  [5, 8.0, 4.8], [6, 8.5, 5.0], [7, 9.0, 5.3], [8, 9.5, 5.5], [9, 10.0, 5.8],
]
const FINGERS = ['pinky', 'pinkyRing', 'ring', 'middle', 'middleIndex', 'index', 'indexThumb', 'thumb', 'thumb', 'thumb']
const finger = (i) => i18n.t('size.finger.' + FINGERS[i])

function conv(mm) {
  return unit.value === 'mm' ? mm.toFixed(1) : (mm / 25.4).toFixed(2)
}
const unitLabel = computed(() => (unit.value === 'mm' ? 'mm' : 'in'))
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:760px">
      <div style="text-align:center;margin-bottom:30px">
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">{{ i18n.t('size.title') }}</h1>
        <p style="color:var(--gray)">{{ i18n.t('size.sub') }}</p>
      </div>

      <div class="card" style="padding:22px;margin-bottom:18px">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px">
          <h3 style="font-size:15px;margin:0">{{ i18n.t('size.step1') }}</h3>
          <div style="display:inline-flex;border:1.5px solid var(--gray-light);border-radius:999px;overflow:hidden">
            <button
              v-for="u in ['mm', 'in']" :key="u"
              style="padding:6px 16px;font-size:12.5px;font-weight:700;border:none;cursor:pointer"
              :style="unit === u ? 'background:var(--plum);color:#fff' : 'background:transparent;color:var(--gray)'"
              @click="unit = u"
            >{{ u === 'mm' ? 'mm' : i18n.t('size.unitInch') }}</button>
          </div>
        </div>
        <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
          <img src="https://placehold.co/220x140/F5D8DA/6D2E46?text=Measure+widest+point" :alt="i18n.t('size.measureAlt')" style="border-radius:12px;flex:none" loading="lazy">
          <p class="sg-measure" style="font-size:13.5px;color:var(--gray);line-height:1.7;flex:1;min-width:220px" v-html="i18n.t('size.measureD')" />
        </div>
      </div>

      <div class="card" style="padding:22px;margin-bottom:18px;overflow-x:auto">
        <h3 style="font-size:15px;margin-bottom:10px">{{ i18n.t('size.step2') }}</h3>
        <table class="table sg-table" style="width:100%">
          <thead>
            <tr>
              <th>{{ i18n.t('size.th.size') }}</th><th>{{ i18n.t('size.th.width', unitLabel) }}</th><th>{{ i18n.t('size.th.cuticle', unitLabel) }}</th><th>{{ i18n.t('size.th.finger') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in SIZES" :key="s[0]" class="sg-row" :class="{ sel: picked === s[0] }" @click="picked = s[0]">
              <td><span v-if="picked === s[0]" class="sg-ok">✓</span><b>{{ s[0] }}</b></td><td>{{ conv(s[1]) }}</td><td>{{ conv(s[2]) }}</td>
              <td style="color:var(--gray)">{{ finger(s[0]) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="picked >= 0" style="font-size:13px;color:var(--plum);font-weight:600;margin-top:10px">
          {{ i18n.t('size.picked', picked) }}
        </p>
      </div>

      <div class="card" style="padding:22px">
        <h3 style="font-size:15px;margin-bottom:10px">{{ i18n.t('size.betweenT') }}</h3>
        <p class="sg-between" style="font-size:13.5px;color:var(--gray);line-height:1.7" v-html="i18n.t('size.betweenD')" />
        <router-link to="/store?cat=nails" class="btn btn-primary" style="margin-top:12px">{{ i18n.t('size.shopCta') }}</router-link>
      </div>
    </div>

    <!-- 移动端底部 sticky 总结条（选中尺码后出现，避开 TabBar；✕ 清除已选） -->
    <div v-if="picked >= 0" class="sg-bar">
      <div style="display:flex;align-items:center;gap:10px;min-width:0">
        <b>{{ i18n.t('size.barPicked', picked) }}</b>
        <button class="sg-clear" :aria-label="i18n.t('size.clear')" @click="picked = -1">✕</button>
      </div>
      <router-link to="/store" class="btn btn-primary btn-sm">{{ i18n.t('size.barShop') }}</router-link>
    </div>
  </section>
</template>

<style scoped>
/* 尺码表：接入全局 .table 视觉（hover rose-pale），选中行左侧 3px plum 指示条 + 首列 ✓ 对勾 */
.sg-row { cursor: pointer; }
.sg-row.sel td { background: var(--rose-pale); }
.sg-row.sel td:first-child { box-shadow: inset 3px 0 0 var(--plum); }
.sg-ok { color: var(--plum); font-weight: 700; margin-right: 6px; }

/* v-html 段落内的 <b>/<a> 品牌色（文案来自 i18n 字典） */
.sg-measure :deep(a), .sg-between :deep(a) { color: var(--plum); }

/* 移动端 sticky 总结条 */
.sg-bar { position: fixed; left: 16px; right: 16px; bottom: calc(70px + env(safe-area-inset-bottom, 0px)); z-index: 140; display: none; align-items: center; justify-content: space-between; gap: 12px; background: #fff; border: 1px solid var(--gray-light); border-radius: 14px; box-shadow: var(--shadow-pop); padding: 12px 16px; }
.sg-bar b { font-size: 14px; color: var(--plum); }
.sg-clear { flex: none; width: 26px; height: 26px; border-radius: 50%; border: none; background: var(--rose-pale); color: var(--plum); font-size: 13px; cursor: pointer; }
.sg-clear:hover { background: var(--rose); color: #fff; }
@media (max-width: 768px) {
  .sg-bar { display: flex; }
}
</style>
