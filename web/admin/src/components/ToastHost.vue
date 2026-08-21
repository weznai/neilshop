<script setup>
import { useToast } from '../composables/toast'
const { state, dismiss } = useToast()
</script>

<template>
  <div class="gm-toast-wrap">
    <div v-for="t in state.toasts" :key="t.id" class="gm-toast" :class="[t.type, { out: t.leaving }]">
      <span class="gm-toast-msg">{{ t.msg }}</span>
      <button class="gm-toast-x" aria-label="关闭提示" @click="dismiss(t.id)">×</button>
    </div>
  </div>
</template>
