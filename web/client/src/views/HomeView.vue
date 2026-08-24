<script setup>
import { computed, ref, watch } from 'vue'
import { req } from '../api/client'
import { GM_CATALOG } from '../data/catalog'
import { i18n } from '../i18n'
import GmIcon from '../components/GmIcon.vue'
import ProductCard from '../components/ProductCard.vue'

const newProducts = ref([])
const bestProducts = ref([])
const ugcItems = ref([])
const ugcTotal = ref(0)
const loaded = ref(false)
const ugcLoaded = ref(false)

/* 甲型导购卡：icon 为符号非文案，t/d 为 i18n 键 */
const SHAPES = [
  { v: 'almond', icon: '♀', t: 'home.shape.almond', d: 'home.shape.almondD' },
  { v: 'square', icon: '▣', t: 'home.shape.square', d: 'home.shape.squareD' },
  { v: 'stiletto', icon: '▲', t: 'home.shape.stiletto', d: 'home.shape.stilettoD' },
  { v: 'coffin', icon: '◭', t: 'home.shape.coffin', d: 'home.shape.coffinD' },
]
/* 评价：人名/商品名为数据字段不迁，正文走 i18n */
const REVIEWS = [
  { n: 'Maya R.', p: 'Bare Gems', c: 'home.rev.1' },
  { n: 'Jenna K.', p: 'Winter Storm', c: 'home.rev.2' },
  { n: 'Priya S.', p: 'Cherry Bomb', c: 'home.rev.3' },
]

/* 价值条图标（GmIcon 线性图标集：品质/快捷/循环使用/无损防护） */
const VALUES = [
  ['star', 'home.value.1'],
  ['check', 'home.value.2'],
  ['refresh', 'home.value.3'],
  ['shield', 'home.value.4'],
]

function seedCards() {
  return GM_CATALOG.map((c) => ({
    id: c.id, slug: '', title: c.title,
    price_min: Math.round(c.price * 100), price_max: Math.round(c.price * 100),
    compare_at_price: null, hero_image: c.img, tags: [],
    is_new: false, is_best_seller: false, sold_count: 0, rating_count: 0, rating: 0,
    stock_summary: { total: c.stock, low: 0, out: c.stock <= 0 },
  }))
}

/* LCP：请求前置到 setup 顶层立即发出（不等 onMounted）；
   两组卡片并行拉取（allSettled：单接口失败回落种子数据，不拖住另一组）；
   中文环境带 locale 消费后端多语言标题；seq 防语言切换竞态 */
let cardsSeq = 0
async function loadCards() {
  const seq = ++cardsSeq
  const loc = i18n.lang === 'zh' ? '&locale=zh-CN' : ''
  const [nr, br] = await Promise.allSettled([
    req('GET', '/api/catalog/products?sort=new&size=4' + loc),
    req('GET', '/api/catalog/products?sort=best&size=4' + loc),
  ])
  if (seq !== cardsSeq) return
  newProducts.value = nr.status === 'fulfilled' && nr.value.items && nr.value.items.length
    ? nr.value.items : seedCards().slice(0, 4)
  bestProducts.value = br.status === 'fulfilled' && br.value.items && br.value.items.length
    ? br.value.items : seedCards().slice(4, 8)
  loaded.value = true
}
loadCards()
/* 站内切换语言：重拉带 locale 的列表（口径对齐 ProductView watch(locale)） */
watch(() => i18n.lang, () => { loadCards() })

/* UGC 买家秀：从 API 获取真实数据，失败回落空数组；total 供 CTA 数量文案 */
;(async () => {
  try {
    const res = await req('GET', '/api/content/ugc?size=6')
    ugcItems.value = res && res.items ? res.items : []
    ugcTotal.value = (res && res.total) || 0
  } catch (_) { ugcItems.value = [] }
  ugcLoaded.value = true
})()

/* 无真实数据（0/接口失败）不虚构数字：空串时模板隐藏数量行 */
const ugcCount = computed(() => (ugcTotal.value > 0 ? ugcTotal.value.toLocaleString() + '+' : ''))

const heroImg = computed(() => (newProducts.value[0] && newProducts.value[0].hero_image) ||
  'https://placehold.co/600x450/F5D8DA/6D2E46?text=New+Season+Glam')

/* hero 图加载失败：回落 placehold 占位（dataset 防循环） */
const HERO_FALLBACK = 'https://placehold.co/600x450/E8B4B8/552338?text=GLOWMAG'
function heroFallback(e) {
  const img = e.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = HERO_FALLBACK
}

/* UGC 图（外链 media）：同款 dataset 守卫兜底 */
const UGC_FALLBACK = 'https://placehold.co/140x140/E8B4B8/552338?text=GLOWMAG'
function ugcFallback(e) {
  const img = e.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = UGC_FALLBACK
}
</script>

<template>
  <!-- ============ HERO ============ -->
  <section class="fade-up" style="background:linear-gradient(135deg,var(--rose-pale),var(--white) 60%);padding:72px 0 88px">
    <div class="container grid-m-1" style="display:grid;grid-template-columns:1fr 1fr;gap:48px;align-items:center">
      <div>
        <div style="font-size:13px;font-weight:700;letter-spacing:2px;color:var(--coral);text-transform:uppercase;margin-bottom:14px">{{ i18n.t('home.hero.kicker') }}</div>
        <!-- v16: clamp——≥650px 恒为 52px 与桌面一致，375px 收至 30px -->
        <h1 style="font-family:var(--font-title);font-size:clamp(28px,8vw,52px);line-height:1.12;margin-bottom:18px">{{ i18n.t('home.hero.title') }}<br>{{ i18n.t('home.hero.ready') }} <em style="color:var(--plum)">{{ i18n.t('home.hero.mins') }}</em></h1>
        <p style="color:var(--gray);font-size:16px;margin-bottom:14px;max-width:420px">{{ i18n.t('home.hero.sub') }}</p>
        <div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap;font-size:12.5px;color:var(--gray);margin-bottom:26px">
          <span aria-hidden="true" style="font-size:13px">🎵</span> {{ i18n.t('home.hero.tiktok') }}
          <span style="color:var(--gray-light)">·</span>
          <span class="stars" style="font-size:11.5px;color:var(--gold)" aria-hidden="true">★★★★★</span>
          {{ i18n.t('home.hero.reviews') }}
        </div>
        <div class="home-hero-cta" style="display:flex;gap:14px">
          <router-link to="/store" class="btn btn-primary btn-lg">{{ i18n.t('home.hero.shop') }}</router-link>
          <router-link to="/size-guide" class="btn btn-secondary btn-lg">{{ i18n.t('home.hero.size') }}</router-link>
        </div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:22px;font-size:13.5px">
          <span class="stars" style="font-size:15px">★★★★★</span>
          <b>4.8/5</b><span style="color:var(--gray)">{{ i18n.t('home.hero.rating') }}</span>
        </div>
        <div style="display:flex;gap:18px;flex-wrap:wrap;margin-top:12px;font-size:12.5px;color:var(--gray)">
          <span>🚚 {{ i18n.t('home.hero.fship') }}</span><span>↩️ {{ i18n.t('home.hero.ret') }}</span><span>🔒 {{ i18n.t('home.hero.pay') }}</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:16px">
          <span class="pay-pill">VISA</span><span class="pay-pill">MC</span><span class="pay-pill">AMEX</span><span class="pay-pill">PAYPAL</span><span class="pay-pill">KLARNA</span><span class="pay-pill">APPLE PAY</span>
        </div>
      </div>
      <div style="position:relative">
        <img :src="heroImg"
             :alt="i18n.t('home.hero.alt')"
             fetchpriority="high" decoding="async"
             style="width:100%;border-radius:24px;aspect-ratio:4/3;object-fit:cover;background:var(--rose-pale)"
             @error="heroFallback">
        <div style="position:absolute;top:-14px;left:-10px;width:48px;height:48px;border-radius:50%;background:#fff;box-shadow:var(--shadow-card);display:flex;align-items:center;justify-content:center;font-size:22px;transition:transform .2s ease-out" class="hero-float">✨</div>
        <div class="card hero-float" style="position:absolute;bottom:-24px;right:-10px;padding:14px 18px;display:flex;gap:10px;align-items:center">
          <span style="font-size:26px">🧲</span>
          <div><b style="font-size:13px">{{ i18n.t('home.hero.lash') }}</b><div style="font-size:12px;color:var(--gray)">{{ i18n.t('home.hero.lashD') }}</div></div>
        </div>
      </div>
    </div>
  </section>

  <!-- ============ 价值条 ============ -->
  <section style="background:linear-gradient(120deg,var(--rose-light),var(--rose-pale) 55%,var(--white));color:var(--plum);padding:22px 0">
    <div class="container grid-m-2" style="display:grid;grid-template-columns:repeat(4,1fr);gap:20px;text-align:center;font-size:13px;font-weight:600">
      <span v-for="[ico, key] in VALUES" :key="key" class="value-item">
        <GmIcon :name="ico" :size="15" />{{ i18n.t(key) }}
      </span>
    </div>
  </section>

  <!-- ============ NEW ARRIVALS ============ -->
  <section class="section">
    <div class="container">
      <div class="section-head" style="margin-bottom:12px">
        <h2 class="section-title">{{ i18n.t('home.new.t') }}</h2>
        <router-link class="section-link" to="/store?sort=new">{{ i18n.t('home.viewAll') }}</router-link>
      </div>
      <p style="font-size:13px;color:var(--gray);margin:-2px 0 20px">{{ i18n.t('home.new.note') }}</p>
      <div class="grid grid-4">
        <template v-if="!loaded">
          <div v-for="i in 4" :key="'sk' + i" class="home-sk-card">
            <div class="home-sk-img sk-shimmer"></div>
            <div class="home-sk-line sk-shimmer" style="width:70%"></div>
            <div class="home-sk-line sk-shimmer" style="width:40%"></div>
          </div>
        </template>
        <template v-else>
          <ProductCard v-for="p in newProducts" :key="p.id" :p="p" />
        </template>
      </div>
    </div>
  </section>

  <!-- ============ SHOP BY SHAPE ============ -->
  <section class="section" style="background:var(--rose-pale)">
    <div class="container">
      <div class="section-head"><h2 class="section-title">{{ i18n.t('home.shape.t') }}</h2></div>
      <div class="grid grid-4">
        <router-link v-for="s in SHAPES" :key="s.v" class="card shape-card" :to="`/store?cat=nails&shape=${s.v}`">
          <div class="shape-ico" style="font-size:44px;padding:28px 0 12px;text-align:center">{{ s.icon }}</div>
          <div style="padding:0 18px 20px;text-align:center">
            <b style="font-family:var(--font-title);font-size:18px">{{ i18n.t(s.t) }}</b>
            <div style="font-size:12.5px;color:var(--gray);margin-top:4px">{{ i18n.t(s.d) }}</div>
          </div>
        </router-link>
      </div>
    </div>
  </section>

  <!-- ============ BEST SELLERS ============ -->
  <section class="section">
    <div class="container">
      <div class="section-head" style="margin-bottom:12px">
        <h2 class="section-title">{{ i18n.t('home.best.t') }}</h2>
        <router-link class="section-link" to="/store?sort=best">{{ i18n.t('home.viewAll') }}</router-link>
      </div>
      <div class="grid grid-4">
        <template v-if="!loaded">
          <div v-for="i in 4" :key="'sk2' + i" class="home-sk-card">
            <div class="home-sk-img sk-shimmer"></div>
            <div class="home-sk-line sk-shimmer" style="width:70%"></div>
            <div class="home-sk-line sk-shimmer" style="width:40%"></div>
          </div>
        </template>
        <template v-else>
          <ProductCard v-for="p in bestProducts" :key="p.id" :p="p" />
        </template>
      </div>
    </div>
  </section>

  <!-- ============ HOW IT WORKS ============ -->
  <section class="section" style="background:var(--rose-pale)">
    <div class="container" style="text-align:center">
      <h2 class="section-title" style="margin-bottom:8px">{{ i18n.t('home.how.t') }}</h2>
      <p style="color:var(--gray);margin-bottom:36px">{{ i18n.t('home.how.sub') }}</p>
      <div class="grid grid-3 grid-m-1" style="text-align:left">
        <div class="card">
          <div class="step-n">1</div>
          <b style="font-size:15px">{{ i18n.t('home.how.s1t') }}</b>
          <p style="font-size:13px;color:var(--gray);margin-top:6px">{{ i18n.t('home.how.s1d') }}</p>
        </div>
        <div class="card">
          <div class="step-n">2</div>
          <b style="font-size:15px">{{ i18n.t('home.how.s2t') }}</b>
          <p style="font-size:13px;color:var(--gray);margin-top:6px">{{ i18n.t('home.how.s2d') }}</p>
        </div>
        <div class="card">
          <div class="step-n">3</div>
          <b style="font-size:15px">{{ i18n.t('home.how.s3t') }}</b>
          <p style="font-size:13px;color:var(--gray);margin-top:6px">{{ i18n.t('home.how.s3d') }}</p>
        </div>
      </div>
      <router-link to="/how-it-works" class="btn btn-secondary" style="margin-top:28px">{{ i18n.t('home.how.cta') }}</router-link>
    </div>
  </section>

  <!-- ============ REVIEWS ============ -->
  <section class="section">
    <div class="container">
      <div class="section-head"><h2 class="section-title">{{ i18n.t('home.rev.t') }}</h2></div>
      <div class="grid grid-3">
        <div v-for="rv in REVIEWS" :key="rv.n" class="card">
          <div class="stars" style="color:var(--gold)">★★★★★</div>
          <p style="font-size:14px;margin:10px 0 14px">"{{ i18n.t(rv.c) }}"</p>
          <div style="display:flex;align-items:center;gap:10px">
            <span class="rev-ava"><span>{{ rv.n.charAt(0) }}</span></span>
            <div><b style="font-size:13px">{{ rv.n }}</b><div style="font-size:11.5px;color:var(--gray)">✓ {{ i18n.t('home.rev.verified') }} · {{ rv.p }}</div></div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ============ UGC CTA ============ -->
  <section class="section" style="padding-top:0">
    <div class="container">
      <div class="ugc-band" style="margin-bottom:18px">
        <template v-if="ugcItems.length">
          <img v-for="item in ugcItems" :key="item.id" :src="item.image_url" :alt="item.caption || i18n.t('home.ugc.alt')" loading="lazy" @error="ugcFallback">
        </template>
        <template v-else-if="ugcLoaded">
          <img v-for="i in 6" :key="i" :src="`https://placehold.co/140x140/F5D8DA/6D2E46?text=Glam+${i}`" :alt="i18n.t('home.ugc.alt')" loading="lazy">
        </template>
        <router-link class="ugc-cta" to="/gallery">
          <b v-if="ugcCount">{{ ugcCount }}</b><span>{{ i18n.t('home.ugc.looks') }}</span><span style="text-decoration:underline">{{ i18n.t('home.ugc.see') }}</span>
        </router-link>
      </div>
    </div>
  </section>
</template>

<style scoped>
.step-n{width:56px;height:56px;border-radius:50%;background:linear-gradient(135deg,var(--rose),var(--plum));color:#fff;display:inline-flex;align-items:center;justify-content:center;font-family:var(--font-title);font-size:24px;font-weight:700;margin-bottom:14px}
.ugc-band{display:flex;gap:12px;overflow-x:auto;scrollbar-width:none;-ms-overflow-style:none;padding:2px 0 6px}
.ugc-band::-webkit-scrollbar{display:none}
.ugc-band img{width:140px;height:140px;flex:none;border-radius:12px;object-fit:cover;transition:transform .2s ease-out,box-shadow .2s ease-out}
.ugc-band img:hover{transform:scale(1.04);box-shadow:var(--shadow-pop)}
.ugc-cta{width:140px;height:140px;flex:none;border-radius:14px;background:linear-gradient(135deg,var(--rose),var(--plum));color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;font-size:12px;font-weight:500;text-align:center;padding:10px;transition:filter .15s;box-shadow:0 12px 26px rgba(138,74,99,.30);border:2px solid rgba(255,255,255,.55)}
.ugc-cta:hover{filter:brightness(1.08)}
.ugc-cta b{font-size:21px;font-family:var(--font-title)}
.shape-card{display:block;padding:0;overflow:hidden;color:inherit}
.shape-ico{transition:transform .2s ease-out,color .2s ease-out}
.shape-card:hover .shape-ico{transform:scale(1.15);color:var(--plum)}
/* hero 浮动徽标/卡片 hover 上浮 */
.hero-float{transition:transform .2s ease-out,box-shadow .2s ease-out}
.hero-float:hover{transform:translateY(-4px)}
  /* 价值条：GmIcon + 文案（浅粉渐变底上珊瑚色描边图标） */
  .value-item{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-width:0}
  .value-item svg{stroke:var(--coral);flex:none}
/* REVIEWS 头像渐变描边 */
.rev-ava{width:38px;height:38px;padding:2px;border-radius:50%;background:linear-gradient(135deg,var(--rose),var(--plum));flex:none}
.rev-ava span{width:100%;height:100%;border-radius:50%;background:var(--plum);color:#fff;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700}
.home-sk-card{border-radius:12px}
.home-sk-img{aspect-ratio:1;border-radius:12px}
.home-sk-line{height:14px;border-radius:7px;margin-top:10px}
</style>
