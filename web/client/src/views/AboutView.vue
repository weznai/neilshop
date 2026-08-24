<script setup>
import { i18n, tt } from '../i18n'
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:760px">
      <div class="about-hero">
        <h1 style="font-family:var(--font-title);font-size:32px;margin-bottom:8px">{{ i18n.t('about.title') }}</h1>
        <p style="color:var(--gray)">{{ i18n.t('about.heroSub') }}</p>
      </div>
      <div class="about-body">
        <!-- 两段含 <b> 强调，走 v-html（文案来自 i18n 字典） -->
        <p v-html="i18n.t('about.p1')" />
        <p>{{ i18n.t('about.p2') }}</p>
        <div class="grid grid-3 grid-m-1" style="margin:8px 0">
          <div class="card" style="padding:18px;text-align:center"><b class="stat-num">40k+</b><div style="font-size:12.5px;color:var(--gray)">{{ i18n.t('about.stat1') }}</div></div>
          <div class="card" style="padding:18px;text-align:center"><b class="stat-num">4.8/5</b><div style="font-size:12.5px;color:var(--gray)">{{ i18n.t('about.stat2') }}</div></div>
          <div class="card" style="padding:18px;text-align:center"><b class="stat-num">70+</b><div style="font-size:12.5px;color:var(--gray)">{{ i18n.t('about.stat3') }}</div></div>
        </div>
        <p>{{ i18n.t('about.p3') }}</p>
        <div class="card" style="padding:20px;display:flex;gap:14px;align-items:center;flex-wrap:wrap">
          <div style="font-size:30px">💅</div>
          <div style="flex:1;min-width:220px">
            <b>{{ i18n.t('about.ctaT') }}</b>
            <p style="font-size:13.5px;color:var(--gray);margin:4px 0 0">{{ i18n.t('about.ctaD') }}</p>
          </div>
          <router-link to="/store?sort=best" class="btn btn-primary btn-sm">{{ tt('Shop best sellers', '逛热卖爆款') }}</router-link>
          <router-link to="/how-it-works" class="btn btn-secondary btn-sm">{{ i18n.t('about.ctaBtn1') }}</router-link>
          <router-link to="/blog" class="btn btn-ghost btn-sm">{{ i18n.t('about.ctaBtn2') }}</router-link>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* hero 渐变底（rose-pale → #fff） */
.about-hero { text-align: center; margin-bottom: 34px; padding: 42px 20px 34px; border-radius: 20px; background: linear-gradient(180deg, var(--rose-pale), #fff); border: 1px solid var(--rose-light); }
/* 三统计卡数字：--gold 强调 + 衬线字族 */
.stat-num { display: block; font-family: var(--font-title); font-size: 27px; font-weight: 700; color: var(--gold); line-height: 1.2; }
.about-body { display: grid; gap: 18px; font-size: 15px; line-height: 1.85; }
</style>
