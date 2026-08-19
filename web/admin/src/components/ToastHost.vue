<script setup>
import { useToast } from '../composables/toast'
const { state } = useToast()
</script>

<template>
  <div class="gm-toast-wrap">
    <div v-for="t in state.toasts" :key="t.id" class="gm-toast" :class="t.type">{{ t.msg }}</div>
  </div>
</template>
