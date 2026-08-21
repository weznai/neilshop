<script setup>
import { i18n } from '../i18n'

const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)
/* seed 目录无 collab 专属 tag —— CTA 指向最新上架；卡片为编辑部精选合辑（非在售联名系列） */
const PICKS = [
  ['@nailbedbynia', 'Nia x GLOWMAG', 'Editorial pick — her favorite chrome & glass looks', '编辑部精选——她最爱的铬玻璃质感造型', 'https://placehold.co/400x400/DDD6E8/552338?text=NIA+x+GM'],
  ['@thedailyglam', 'Daily Glam Capsule', 'Editorial pick — six everyday neutrals she swears by', '编辑部精选——她日常必戴的六款百搭色', 'https://placehold.co/400x400/FBEBD4/8A6D3B?text=Daily+Glam'],
]
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:760px">
      <div style="text-align:center;margin-bottom:30px">
        <div style="font-size:46px">🤝</div>
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">{{ tt('Collabs', '联名合作') }}</h1>
        <p style="color:var(--gray)">{{ tt('Editorial picks curated with creators we love — shop the styles they actually wear.', '编辑部精选 · 与创作者合作的心水款式合辑') }}</p>
      </div>
      <div class="grid grid-2">
        <div v-for="c in PICKS" :key="c[1]" class="card collab-card" style="padding:0;overflow:hidden">
          <div class="collab-img">
            <img :src="c[4]" :alt="c[1]" loading="lazy">
          </div>
          <div style="padding:18px">
            <span class="trend-chip collab-chip">{{ c[0] }}</span>
            <b style="display:block;font-family:var(--font-title);font-size:19px;margin:8px 0 4px">{{ c[1] }}</b>
            <div style="font-size:13px;color:var(--gray);margin-bottom:12px">{{ tt(c[2], c[3]) }}</div>
            <router-link to="/store?sort=new" class="btn btn-secondary btn-sm">{{ tt('Shop new arrivals →', '去逛最新上架 →') }}</router-link>
          </div>
        </div>
      </div>
      <div class="card" style="padding:26px;margin-top:22px">
        <b style="font-size:16px">{{ tt('Want to collab?', '想和我们联名？') }}</b>
        <div class="collab-reqs">
          <span v-for="r in [
            tt('10k+ followers', '1 万+ 粉丝'),
            tt('Nail or lash content', '美甲或睫毛内容创作者'),
            tt('Based anywhere we ship', '位于可配送地区'),
            tt('Love a glam drop', '热爱美的事业'),
          ]" :key="r" class="trend-chip collab-chip">{{ r }}</span>
        </div>
        <p style="font-size:13.5px;color:var(--gray);line-height:1.7;margin:0 0 14px">
          {{ tt(
            'Send us your handle, audience and 3 photos of your best sets — we review every application within a week and co-plan the drop, product and revenue share together.',
            '把你的社交账号、粉丝画像和 3 张最佳作品发给我们——每周内回复所有申请，一起策划联名款、选品与分成。',
          ) }}
        </p>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <router-link :to="{ path: '/contact', query: { subject: 'Collab application' } }" class="btn btn-primary btn-sm">{{ tt('Apply via Contact', '通过联系页申请') }}</router-link>
          <a href="mailto:collabs@glowmag.com?subject=Collab%20application" class="btn btn-secondary btn-sm">{{ tt('Email collabs@glowmag.com', '邮件 collabs@glowmag.com') }}</a>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 合辑卡：图 hover scale(1.03) 慢速缩放（容器裁切） */
.collab-img { overflow: hidden; }
.collab-img img { width: 100%; aspect-ratio: 4/5; object-fit: cover; display: block; transition: transform .35s ease-out; }
.collab-card:hover .collab-img img { transform: scale(1.03); }

/* trend-chip 统一（页内 flex 容器内去除自带 margin） */
.collab-reqs { display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }
.collab-chip { margin: 0; }
</style>
