<script setup>
import { useToast } from '../composables/toast'
const { state, dismiss } = useToast()
</script>

<template>
  <div class="gm-toast-wrap" role="status" aria-live="polite">
    <div v-for="t in state.toasts" :key="t.id" class="gm-toast" :class="[t.type, { out: t.leaving }]">
      <span class="gm-toast-ico" :class="t.type || 'info'" aria-hidden="true">
        <svg v-if="t.type === 'success'" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12" /></svg>
        <svg v-else-if="t.type === 'error'" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
        <svg v-else viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" /></svg>
      </span>
      <span class="gm-toast-msg">{{ t.msg }}</span>
      <button class="gm-toast-x" aria-label="关闭提示" @click="dismiss(t.id)">×</button>
    </div>
  </div>
</template>
