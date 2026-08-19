<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../api/client'

const tickets = ref([])
const loaded = ref(false)
const SSTATUS = { 0: ['新工单', 'tag-pending'], 1: ['处理中', 'tag-paid'], 2: ['等待客户', 'tag-pending'], 3: ['已关闭', 'tag-done'] }
const active = ref(null)
const reply = ref('')

onMounted(async () => {
  try { tickets.value = (await req('GET', '/api/admin/ops/tickets')).items || [] } catch (_) { /* */ }
  loaded.value = true
})

async function send() {
  if (!reply.value.trim() || !active.value) return
  try {
    await req('POST', `/api/admin/ops/tickets/${active.value.id}/reply`, { message: reply.value })
    reply.value = ''
    active.value = await req('GET', `/api/admin/ops/tickets/${active.value.id}`)
    window.$gmToast('回复已发送 ✓', 'success')
  } catch (e) { window.$gmToast('回复失败：' + (e.message || ''), 'error') }
}
async function close() {
  if (!confirm('关闭工单 #' + active.value.id + '？')) return
  await req('POST', `/api/admin/ops/tickets/${active.value.id}/close`)
  active.value = null
  tickets.value = (await req('GET', '/api/admin/ops/tickets')).items || []
  window.$gmToast('工单已关闭 ✓', 'success')
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">客服工单</h1>
      <span style="font-size:12.5px;color:var(--gray)">未关 {{ tickets.filter((t) => t.status !== 3).length }} / 共 {{ tickets.length }}</span>
    </div>
  </div>

  <div class="grid-2" style="align-items:start">
    <div class="card" style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:10px">#</th><th>主题</th><th>客户</th><th>SLA</th><th>状态</th></tr></thead>
        <tbody>
          <tr
            v-for="t in tickets" :key="t.id"
            style="border-top:1px solid var(--gray-light);cursor:pointer"
            :style="{ background: active && active.id === t.id ? 'var(--rose-pale)' : '' }"
            @click="active = t"
          >
            <td style="padding:11px 10px"><b>#{{ t.id }}</b></td>
            <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ t.subject }}</td>
            <td>{{ (t.email || '').split('@')[0] }}</td>
            <td><span class="tag" :class="t.status === 3 ? 'tag-done' : 'tag-paid'">{{ t.status === 3 ? '—' : '4h' }}</span></td>
            <td><span class="tag" :class="SSTATUS[t.status]?.[1]">{{ SSTATUS[t.status]?.[0] }}</span></td>
          </tr>
        </tbody>
      </table>
      <div v-if="loaded && !tickets.length" style="text-align:center;color:var(--gray);padding:28px 0">暂无工单</div>
    </div>

    <div class="card" style="padding:20px;position:sticky;top:16px">
      <div v-if="!active" style="text-align:center;color:var(--gray);padding:40px 0">← 选择一个工单查看对话</div>
      <template v-else>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <b style="font-size:14.5px">#{{ active.id }} · {{ active.subject }}</b>
          <span class="tag" :class="SSTATUS[active.status]?.[1]">{{ SSTATUS[active.status]?.[0] }}</span>
        </div>
        <div style="display:grid;gap:10px;max-height:320px;overflow-y:auto;margin-bottom:14px">
          <div v-for="(m, i) in active.messages || [{ who: 'user', body: active.message }]" :key="i"
               class="chat-msg" :class="m.who === 'staff' ? 'bot' : ''"
               style="max-width:85%;padding:10px 14px;border-radius:12px;font-size:13px"
               :style="{
                 background: m.who === 'staff' ? 'var(--rose-pale)' : 'var(--gray-light)',
                 justifySelf: m.who === 'staff' ? 'end' : 'start',
               }">
            {{ m.body || m.message }}
          </div>
        </div>
        <textarea v-model="reply" class="input" rows="3" placeholder="输入回复…" style="margin-bottom:10px"></textarea>
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" style="flex:1" @click="send">发送回复</button>
          <button v-if="active.status !== 3" class="btn btn-ghost" style="color:var(--error)" @click="close">关闭</button>
        </div>
      </template>
    </div>
  </div>
</template>
