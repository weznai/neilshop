<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../../api/client'

const pts = ref(null)
const loaded = ref(false)

onMounted(async () => {
  try { pts.value = await req('GET', '/api/points') } catch (_) { /* */ }
  loaded.value = true
})

const RULES = [
  ['Place an order', '+1 pt per $1'],
  ['Write a review', '+50 pts'],
  ['Refer a friend', '+500 pts'],
  ['Birthday month', '+200 pts'],
]
</script>

<template>
  <div style="display:grid;gap:16px">
    <div class="card" style="padding:24px;background:linear-gradient(135deg,#2E1430,var(--ink));color:#fff">
      <div style="font-size:12.5px;opacity:.75;letter-spacing:1px">GLOW POINTS BALANCE</div>
      <div style="font-family:var(--font-title);font-size:44px;margin:6px 0">
        {{ pts ? (pts.usable || 0).toLocaleString() : '—' }}
      </div>
      <div style="font-size:13px;opacity:.85">
        ≈ ${{ pts ? ((pts.usable || 0) / 100).toFixed(2) : '0.00' }} off · 100 pts = $1
      </div>
    </div>

    <div class="grid grid-2">
      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">Earn faster</h3>
        <div v-for="[a, b] in RULES" :key="a" style="display:flex;justify-content:space-between;font-size:13.5px;padding:8px 0;border-bottom:1px solid var(--gray-light)">
          <span>{{ a }}</span><b style="color:var(--plum)">{{ b }}</b>
        </div>
      </div>
      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">History</h3>
        <div v-if="pts && pts.items && pts.items.length" style="display:grid;gap:8px;max-height:260px;overflow-y:auto">
          <div v-for="(h, i) in pts.items" :key="i" style="display:flex;justify-content:space-between;font-size:13px">
            <span style="color:var(--gray)">{{ new Date(h.created_at).toLocaleDateString() }} · {{ h.reason }}</span>
            <b :style="{ color: (h.delta || h.points || 0) >= 0 ? 'var(--success)' : 'var(--error)' }">
              {{ (h.delta || h.points || 0) >= 0 ? '+' : '' }}{{ h.delta || h.points }}
            </b>
          </div>
        </div>
        <div v-else-if="loaded" style="font-size:13.5px;color:var(--gray)">No point activity yet.</div>
        <div v-else class="skeleton" style="min-height:120px" />
      </div>
    </div>
  </div>
</template>
