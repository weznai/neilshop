<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../../api/client'
import { useCartStore } from '../../stores/cart'
import { useUiStore } from '../../stores/ui'
import { i18n } from '../../i18n'

const ui = useUiStore()
const cart = useCartStore()
const items = ref([])
const loaded = ref(false)

onMounted(async () => {
  try {
    items.value = await req('GET', '/api/account/wishlist')
    localStorage.setItem('gm_wl_count', String(items.value.length))
  } catch (_) { items.value = [] }
  loaded.value = true
})

async function add(pid) {
  await cart.addByProductId(pid, 1, ui)
}
async function remove(pid) {
  try {
    await req('DELETE', '/api/account/wishlist/' + pid)
    items.value = items.value.filter((w) => w.id !== pid)
    localStorage.setItem('gm_wl_count', String(items.value.length))
    ui.toast('Removed from wishlist', 'success')
  } catch (_) { ui.toast('Remove failed', 'error') }
}
function money(c) { return '$' + ((c || 0) / 100).toFixed(2) }
</script>

<template>
  <div>
    <div v-if="items.length" class="grid grid-3" style="margin-bottom:12px">
      <div v-for="w in items" :key="w.id" class="pcard">
        <div class="pcard-img">
          <router-link :to="`/product?id=${w.id}`">
            <img class="img-main" :src="w.hero_image" :alt="w.title">
          </router-link>
          <span class="pcard-quick" role="button" tabindex="0" @click="add(w.id)">+ Add to Cart</span>
        </div>
        <div class="pcard-info">
          <div class="pcard-title"><router-link :to="`/product?id=${w.id}`">{{ w.title }}</router-link></div>
          <div class="pcard-price">
            {{ money(w.price_min) }}
            <span v-if="w.compare_at_price && w.compare_at_price > w.price_min" class="compare">{{ money(w.compare_at_price) }}</span>
          </div>
          <button class="btn btn-ghost btn-sm" style="color:var(--gray);margin-top:8px" @click="remove(w.id)">Remove</button>
        </div>
      </div>
    </div>
    <div v-else-if="loaded" class="card" style="padding:30px;text-align:center;color:var(--gray)">
      💜 Nothing saved yet — tap the heart on any product you love.
    </div>
    <div v-else class="grid grid-3">
      <div v-for="i in 3" :key="i" class="pcard skeleton" style="min-height:260px" />
    </div>
  </div>
</template>
