<script setup>
/* 通用确认弹窗：替代全站原生 confirm；支持危险态主按钮与「原因」输入（reason 模式下 confirm 事件回传原因文本） */
import { ref, watch, onBeforeUnmount } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  body: { type: String, default: '' },
  danger: { type: Boolean, default: false },
  confirmText: { type: String, default: '确认' },
  cancelText: { type: String, default: '取消' },
  reasonLabel: { type: String, default: '' },
  reasonPlaceholder: { type: String, default: '' },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['confirm', 'close'])

const reason = ref('')

/* open 时挂 Esc 监听、重置上次输入；关闭/卸载时移除（非 busy 才允许 Esc/遮罩关闭） */
watch(
  () => props.open,
  (v) => {
    window[v ? 'addEventListener' : 'removeEventListener']('keydown', onKey)
    if (v) reason.value = ''
  }
)
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

function onKey(e) {
  if (e.key === 'Escape' && !props.busy) emit('close')
}
function close() {
  if (!props.busy) emit('close')
}
function onConfirm() {
  if (props.busy) return
  emit('confirm', props.reasonLabel ? reason.value.trim() : undefined)
}
</script>

<template>
  <div class="modal" :class="{ open }" @click.self="close">
    <div class="modal-box cd-box">
      <h3 class="cd-title">{{ title }}</h3>
      <p v-if="body" class="cd-body">{{ body }}</p>
      <div v-if="reasonLabel" class="field cd-field">
        <label>{{ reasonLabel }}</label>
        <input v-model="reason" class="input" type="text" :placeholder="reasonPlaceholder" :disabled="busy" @keydown.enter.prevent="onConfirm">
      </div>
      <div class="cd-foot">
        <button class="btn btn-secondary btn-sm" :disabled="busy" @click="emit('close')">{{ cancelText }}</button>
        <button
          class="btn btn-sm"
          :class="{ 'btn-primary': !danger }"
          :style="danger ? 'background:var(--error);color:#fff' : null"
          :disabled="busy"
          @click="onConfirm"
        >{{ busy ? '处理中…' : confirmText }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cd-box{max-width:420px}
.cd-title{font-family:var(--font-title);font-size:17px;font-weight:700;letter-spacing:-.2px;margin-bottom:8px}
.cd-body{color:var(--gray);font-size:13px;line-height:1.6;white-space:pre-line}
.cd-field{margin:14px 0 2px}
.cd-foot{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:20px}
</style>
