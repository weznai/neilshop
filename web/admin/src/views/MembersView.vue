<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../api/client'

const members = ref([])
const total = ref(0)
const q = ref('')
const active = ref(null)
const loaded = ref(false)

async function load() {
  loaded.value = false
  try {
    const d = await req('GET', '/api/admin/ops/members?' + new URLSearchParams({ page: 1, size: 50, q: q.value.trim() }))
    members.value = d.items || []
    total.value = d.total ?? members.value.length
  } catch (_) { members.value = [] }
  loaded.value = true
}
onMounted(load)

const TIER = ['Glow', 'Shimmer', 'Diva', 'Queen']
const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

async function openDetail(m) {
  active.value = await req('GET', '/api/admin/ops/members/' + m.id)
}
async function setRisk(m, risk) {
  await req('POST', `/api/admin/ops/members/${m.id}/risk`, { risk })
  active.value.risk = risk
  members.value = members.value.map((x) => (x.id === m.id ? { ...x, risk } : x))
  window.$gmToast('风控状态已更新 ✓', 'success')
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">会员管理</h1>
      <span style="font-size:12.5px;color:var(--gray)">共 {{ total }} 位会员</span>
    </div>
    <input v-model="q" class="input" style="width:220px" placeholder="搜邮箱 / 姓名" @keydown.enter="load()">
  </div>

  <div class="card" style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)">
        <th style="padding:10px">会员</th><th>等级</th><th>积分</th><th>累计消费</th><th>订单数</th><th>风控</th><th style="text-align:right">操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="m in members" :key="m.id" style="border-top:1px solid var(--gray-light)">
          <td style="padding:10px">
            <div style="display:flex;gap:10px;align-items:center">
              <span style="width:34px;height:34px;border-radius:50%;background:var(--rose);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:700">
                {{ (m.name || m.email || '?').charAt(0).toUpperCase() }}
              </span>
              <div><b>{{ m.name || '—' }}</b><div style="font-size:11.5px;color:var(--gray)">{{ m.email }}</div></div>
            </div>
          </td>
          <td><span class="tag tag-paid">{{ TIER[m.tier || 0] }}</span></td>
          <td><b style="color:var(--plum)">{{ (m.points || 0).toLocaleString() }}</b></td>
          <td>{{ money(m.total_spent) }}</td>
          <td style="color:var(--gray)">{{ m.order_count ?? '—' }}</td>
          <td><span class="tag" :class="m.risk === 2 ? 'tag-error' : m.risk === 1 ? 'tag-pending' : 'tag-done'">
            {{ ['正常', '关注', '黑名单'][m.risk || 0] }}</span></td>
          <td style="text-align:right"><button class="btn btn-secondary btn-sm" @click="openDetail(m)">画像</button></td>
        </tr>
      </tbody>
    </table>
    <div v-if="loaded && !members.length" style="text-align:center;color:var(--gray);padding:28px 0">没有匹配会员</div>
  </div>

  <!-- 会员画像弹窗 -->
  <div v-if="active" class="modal open" @click.self="active = null">
    <div class="modal-box" style="max-width:520px">
      <button class="modal-x" @click="active = null">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:4px">{{ active.name || active.email }}</h3>
      <div style="font-size:12.5px;color:var(--gray);margin-bottom:14px">{{ active.email }} · 加入于 {{ (active.created_at || '').slice(0, 10) }}</div>
      <div class="grid-2" style="gap:10px;margin-bottom:14px">
        <div class="stat"><div class="lb">等级</div><div class="vl" style="font-size:18px">{{ TIER[active.tier || 0] }}</div></div>
        <div class="stat"><div class="lb">积分</div><div class="vl" style="font-size:18px;color:var(--plum)">{{ (active.points || 0).toLocaleString() }}</div></div>
        <div class="stat"><div class="lb">累计消费</div><div class="vl" style="font-size:18px">{{ money(active.total_spent) }}</div></div>
        <div class="stat"><div class="lb">订单数</div><div class="vl" style="font-size:18px">{{ active.order_count ?? '—' }}</div></div>
      </div>
      <div class="field">
        <label>风控状态</label>
        <select class="input" :value="active.risk || 0" @change="setRisk(active, parseInt($event.target.value, 10))">
          <option value="0">正常</option><option value="1">关注</option><option value="2">黑名单</option>
        </select>
      </div>
    </div>
  </div>
</template>
