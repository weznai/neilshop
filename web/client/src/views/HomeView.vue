<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../api/client'
import ProductCard from '../components/ProductCard.vue'

const newProducts = ref([])
const bestProducts = ref([])
const loaded = ref(false)

onMounted(async () => {
  try {
    const d = await req('GET', '/api/catalog/products?sort=new&size=4')
    newProducts.value = d.items || []
  } catch (_) { /* 保留空网格 */ }
  try {
    const d = await req('GET', '/api/catalog/products?sort=best&size=4')
    bestProducts.value = d.items || []
  } catch (_) { /* */ }
  loaded.value = true
})
</script>

<template>
  <!-- ============ HERO ============ -->
  <section class="fade-up" style="background:linear-gradient(135deg,var(--rose-pale),var(--white) 60%);padding:72px 0 88px">
    <div class="container grid-m-1" style="display:grid;grid-template-columns:1fr 1fr;gap:48px;align-items:center">
      <div>
        <div style="font-size:13px;font-weight:700;letter-spacing:2px;color:var(--coral);text-transform:uppercase;margin-bottom:14px">New Season · 70+ Styles</div>
        <h1 style="font-family:var(--font-title);font-size:52px;line-height:1.12;margin-bottom:18px">Salon nails,<br>in <em style="color:var(--plum)">5 minutes</em></h1>
        <p style="color:var(--gray);font-size:16px;margin-bottom:14px;max-width:420px">Best-selling press-on nails & magnetic lashes. Up to 2-week wear, zero damage, endless styles.</p>
        <div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap;font-size:12.5px;color:var(--gray);margin-bottom:26px">
          <span aria-hidden="true" style="font-size:13px">🎵</span> As seen on TikTok
          <span style="color:var(--gray-light)">·</span>
          <span class="stars" style="font-size:11.5px;color:var(--gold)" aria-hidden="true">★★★★★</span>
          23,000+ five-star reviews
        </div>
        <div style="display:flex;gap:14px">
          <router-link to="/store" class="btn btn-primary btn-lg">Shop Now</router-link>
          <router-link to="/size-guide" class="btn btn-secondary btn-lg">Find Your Size</router-link>
        </div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:22px;font-size:13.5px">
          <span class="stars" style="font-size:15px">★★★★★</span>
          <b>4.8/5</b><span style="color:var(--gray)">average rating</span>
        </div>
        <div style="display:flex;gap:18px;flex-wrap:wrap;margin-top:12px;font-size:12.5px;color:var(--gray)">
          <span>🚚 Free shipping over $35</span><span>↩️ 30-day returns</span><span>🔒 Secure checkout</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:16px">
          <span class="pay-pill">VISA</span><span class="pay-pill">MC</span><span class="pay-pill">PAYPAL</span><span class="pay-pill">KLARNA</span><span class="pay-pill">APPLE PAY</span>
        </div>
      </div>
      <div style="position:relative">
        <img src="https://placehold.co/600x450/F5D8DA/6D2E46?text=New+Season+Glam"
             alt="GLOWMAG new season press-on nail collection styled with magnetic lashes"
             style="width:100%;border-radius:24px;aspect-ratio:4/3;object-fit:cover">
        <div style="position:absolute;top:-14px;left:-10px;width:48px;height:48px;border-radius:50%;background:#fff;box-shadow:var(--shadow-card);display:flex;align-items:center;justify-content:center;font-size:22px">✨</div>
        <div class="card" style="position:absolute;bottom:-24px;right:-10px;padding:14px 18px;display:flex;gap:10px;align-items:center">
          <span style="font-size:26px">🧲</span>
          <div><b style="font-size:13px">Magnetic Lashes</b><div style="font-size:12px;color:var(--gray)">Snap on in seconds</div></div>
        </div>
      </div>
    </div>
  </section>

  <!-- ============ 价值条 ============ -->
  <section style="background:var(--ink);color:#fff;padding:22px 0">
    <div class="container grid-m-2" style="display:grid;grid-template-columns:repeat(4,1fr);gap:20px;text-align:center;font-size:13px">
      <span>✨ Salon-quality gel finish</span><span>⏱️ 5-min application</span><span>♻️ Reusable up to 60x</span><span>💚 Zero nail damage</span>
    </div>
  </section>

  <!-- ============ NEW ARRIVALS ============ -->
  <section class="section">
    <div class="container">
      <div class="section-head" style="margin-bottom:12px">
        <h2 class="section-title">New Arrivals</h2>
        <router-link class="section-link" to="/store?sort=new">View all →</router-link>
      </div>
      <p style="font-size:13px;color:var(--gray);margin:-2px 0 20px">🚚 Free shipping over $35 · 🎁 Bundle &amp; save up to 20% — applied in cart</p>
      <div class="grid grid-4">
        <ProductCard v-for="p in newProducts" :key="p.id" :p="p" />
        <div v-if="!loaded" v-for="i in 4" :key="'sk' + i" class="pcard skeleton" style="min-height:280px" />
      </div>
    </div>
  </section>

  <!-- ============ SHOP BY SHAPE ============ -->
  <section class="section" style="background:var(--rose-pale)">
    <div class="container">
      <div class="section-head"><h2 class="section-title">Shop by Shape</h2></div>
      <div class="grid grid-4">
        <router-link v-for="s in [
          ['almond', 'Almond', '♀', 'Soft & flattering'],
          ['square', 'Square', '▣', 'Classic & bold'],
          ['stiletto', 'Stiletto', '▲', 'Sharp & fierce'],
          ['coffin', 'Coffin', '◭', 'Trendy tapered'],
        ]" :key="s[0]" class="card shape-card" :to="`/store?cat=nails&shape=${s[0]}`">
          <div style="font-size:44px;padding:28px 0 12px;text-align:center">{{ s[2] }}</div>
          <div style="padding:0 18px 20px;text-align:center">
            <b style="font-family:var(--font-title);font-size:18px">{{ s[1] }}</b>
            <div style="font-size:12.5px;color:var(--gray);margin-top:4px">{{ s[3] }}</div>
          </div>
        </router-link>
      </div>
    </div>
  </section>

  <!-- ============ BEST SELLERS ============ -->
  <section class="section">
    <div class="container">
      <div class="section-head" style="margin-bottom:12px">
        <h2 class="section-title">Best Sellers</h2>
        <router-link class="section-link" to="/store?sort=best">View all →</router-link>
      </div>
      <div class="grid grid-4">
        <ProductCard v-for="p in bestProducts" :key="p.id" :p="p" />
        <div v-if="!loaded" v-for="i in 4" :key="'sk2' + i" class="pcard skeleton" style="min-height:280px" />
      </div>
    </div>
  </section>

  <!-- ============ HOW IT WORKS ============ -->
  <section class="section" style="background:var(--rose-pale)">
    <div class="container" style="text-align:center">
      <h2 class="section-title" style="margin-bottom:8px">Glam in 5 minutes</h2>
      <p style="color:var(--gray);margin-bottom:36px">No glue mishaps. No salon appointments. No damage.</p>
      <div class="grid grid-3" style="text-align:left">
        <div class="card">
          <div class="step-n">1</div>
          <b style="font-size:15px">Prep &amp; clean</b>
          <p style="font-size:13px;color:var(--gray);margin-top:6px">Wipe nails with the included alcohol pad. Pick your sizes — 10 nails, 24 sizes.</p>
        </div>
        <div class="card">
          <div class="step-n">2</div>
          <b style="font-size:15px">Press on &amp; hold</b>
          <p style="font-size:13px;color:var(--gray);margin-top:6px">Apply adhesive tabs or a thin layer of glue. Press each nail for 5 seconds.</p>
        </div>
        <div class="card">
          <div class="step-n">3</div>
          <b style="font-size:15px">Wear &amp; reuse</b>
          <p style="font-size:13px;color:var(--gray);margin-top:6px">Up to 2-week wear. Soak to remove — your set is reusable up to 60 times.</p>
        </div>
      </div>
      <router-link to="/how-it-works" class="btn btn-secondary" style="margin-top:28px">See the full tutorial</router-link>
    </div>
  </section>

  <!-- ============ REVIEWS ============ -->
  <section class="section">
    <div class="container">
      <div class="section-head"><h2 class="section-title">Loved by 40,000+ glammers</h2></div>
      <div class="grid grid-3">
        <div v-for="rv in [
          { n: 'Maya R.', t: 'Bare Gems', c: 'These lasted my full 2-week vacation — pool, beach, everything. Nobody believed they were press-ons.' },
          { n: 'Jenna K.', t: 'Winter Storm', c: 'The magnetic lashes are LIFE CHANGING. No more glue in my eyeballs. 10/10 would glam again.' },
          { n: 'Priya S.', t: 'Cherry Bomb', c: 'Got so many compliments at work. The sizing guide made it super easy to get a perfect fit.' },
        ]" :key="rv.n" class="card">
          <div class="stars" style="color:var(--gold)">★★★★★</div>
          <p style="font-size:14px;margin:10px 0 14px">"{{ rv.c }}"</p>
          <div style="display:flex;align-items:center;gap:10px">
            <span style="width:34px;height:34px;border-radius:50%;background:var(--rose);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:700">{{ rv.n.charAt(0) }}</span>
            <div><b style="font-size:13px">{{ rv.n }}</b><div style="font-size:11.5px;color:var(--gray)">✓ Verified · {{ rv.t }}</div></div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ============ UGC CTA ============ -->
  <section class="section" style="padding-top:0">
    <div class="container">
      <div class="ugc-band" style="margin-bottom:18px">
        <img v-for="i in 6" :key="i" :src="`https://placehold.co/140x140/F5D8DA/6D2E46?text=Glam+${i}`" alt="Customer wearing GLOWMAG nails" loading="lazy">
        <router-link class="ugc-cta" to="/gallery">
          <b>4,800+</b><span>#GLOWMAGGlam looks</span><span style="text-decoration:underline">See them all →</span>
        </router-link>
      </div>
    </div>
  </section>
</template>

<style scoped>
.step-n{width:56px;height:56px;border-radius:50%;background:linear-gradient(135deg,var(--rose),var(--plum));color:#fff;display:inline-flex;align-items:center;justify-content:center;font-family:var(--font-title);font-size:24px;font-weight:700;margin-bottom:14px}
.ugc-band{display:flex;gap:12px;overflow-x:auto;scrollbar-width:none;-ms-overflow-style:none;padding:2px 0 6px}
.ugc-band::-webkit-scrollbar{display:none}
.ugc-band img{width:140px;height:140px;flex:none;border-radius:12px;object-fit:cover}
.ugc-cta{width:140px;height:140px;flex:none;border-radius:14px;background:linear-gradient(135deg,var(--rose),var(--plum));color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;font-size:12px;font-weight:500;text-align:center;padding:10px;transition:filter .15s;box-shadow:0 12px 26px rgba(109,46,70,.30);border:2px solid rgba(255,255,255,.55)}
.ugc-cta:hover{filter:brightness(1.08)}
.ugc-cta b{font-size:21px;font-family:var(--font-title)}
.shape-card{display:block;padding:0;overflow:hidden;color:inherit}
</style>
