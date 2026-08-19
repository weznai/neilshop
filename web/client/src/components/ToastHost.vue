<script setup>
import { useUiStore } from '../stores/ui'
const ui = useUiStore()
</script>

<template>
  <div class="toast-wrap">
    <div v-for="t in ui.toasts" :key="t.id" class="toast" :class="t.type">
      {{ (t.type === 'success' ? '✓ ' : t.type === 'error' ? '✗ ' : '') + t.msg }}
    </div>
  </div>
</template>
