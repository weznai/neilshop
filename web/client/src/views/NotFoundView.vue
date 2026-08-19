<script setup>
const SUGGEST = [
  ['Best sellers', '/store?sort=best'],
  ['New arrivals', '/store?sort=new'],
  ['Sale', '/sale'],
  ['Track order', '/track'],
]
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:640px;text-align:center">
      <div class="b44" style="font-family:var(--font-title);font-size:76px;font-weight:700;letter-spacing:2px">
        <span>4</span><span>0</span><span>4</span>
      </div>
      <h1 style="font-family:var(--font-title);font-size:24px;margin:8px 0 4px">Page not found — but your perfect set is 💅</h1>
      <p style="color:var(--gray);font-size:14px;margin-bottom:22px">
        This page had a chip moment. Let's get you back to the glam.
      </p>
      <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-bottom:28px">
        <router-link to="/" class="btn btn-primary">Back to home</router-link>
        <router-link to="/store" class="btn btn-secondary">Shop all nails</router-link>
      </div>
      <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap">
        <router-link v-for="[label, href] in SUGGEST" :key="href" :to="href" class="trend-chip">{{ label }}</router-link>
      </div>
    </div>
  </section>
</template>

<style scoped>
.b44 span{display:inline-block;animation:bounceIn .7s cubic-bezier(.34,1.56,.64,1) both}
.b44 span:nth-child(2){animation-delay:.1s}
.b44 span:nth-child(3){animation-delay:.2s}
@keyframes bounceIn{
  0%{transform:translateY(-56px) scale(.55);opacity:0}
  60%{transform:translateY(10px) scale(1.06);opacity:1}
  80%{transform:translateY(-5px) scale(1)}
  100%{transform:translateY(0) scale(1)}
}
@media (prefers-reduced-motion: reduce){.b44 span{animation:none}}
</style>
