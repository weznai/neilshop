<script setup>
import { i18n } from '../i18n'

const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)
/* seed 目录无 collab 专属 tag —— CTA 指向最新上架；卡片为编辑部精选合辑（非在售联名系列） */
const PICKS = [
  ['@nailbedbynia', 'Nia x GLOWMAG', 'Editorial pick — her favorite chrome & glass looks', '编辑部精选——她最爱的铬玻璃质感造型', 'https://placehold.co/400x500/DDD6E8/552338?text=NIA+x+GM'],
  ['@thedailyglam', 'Daily Glam Capsule', 'Editorial pick — six everyday neutrals she swears by', '编辑部精选——她日常必戴的六款百搭色', 'https://placehold.co/400x500/FBEBD4/8A6D3B?text=Daily+Glam'],
]
/* 合作流程三步 */
const STEPS = [
  ['📝', 'Apply', '申请', 'Send your handle, audience & 3 best sets.', '提交社交账号、粉丝画像与 3 张最佳作品。'],
  ['🎨', 'Co-create', '共创', 'We co-plan the drop, styles & revenue share.', '一起策划联名款、选品与分成方案。'],
  ['🚀', 'Launch & earn', '上架分成', 'Your capsule goes live — you earn on every set.', '联名系列上线，每售出一副都有你的分成。'],
]
/* 申请条件清单 */
const REQS = [
  ['👥', '10k+ followers', '1 万+ 粉丝'],
  ['💅', 'Nail or lash content creator', '美甲或睫毛内容创作者'],
  ['🌍', 'Based anywhere we ship', '位于可配送地区'],
  ['💜', 'Love a glam drop', '热爱美的事业'],
]
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:960px">

      <!-- Hero：渐变底 + 徽章 + 标题 + 副题 + 迷你数据 -->
      <div class="collab-hero">
        <span class="collab-kicker">{{ tt('CREATOR PROGRAM', '创作者计划') }}</span>
        <h1 class="collab-title">{{ tt('Collabs', '联名合作') }}</h1>
        <p class="collab-sub">{{ tt('Editorial picks curated with creators we love — shop the styles they actually wear.', '编辑部精选 · 与创作者合作的心水款式合辑') }}</p>
        <div class="collab-stats">
          <div class="cs-item"><b>12</b><span>{{ tt('creators', '位创作者') }}</span></div>
          <div class="cs-item"><b>8</b><span>{{ tt('capsule drops', '个联名系列') }}</span></div>
          <div class="cs-item"><b>40k+</b><span>{{ tt('crew reach', '会员覆盖') }}</span></div>
        </div>
      </div>

      <!-- 精选合辑卡：图上浮 handle pill + 底部渐层，hover 浮起 -->
      <div class="grid grid-2 collab-grid">
        <div v-for="c in PICKS" :key="c[1]" class="card collab-card">
          <div class="collab-img">
            <img :src="c[4]" :alt="c[1]" loading="lazy">
            <span class="collab-handle">{{ c[0] }}</span>
            <span class="collab-flag">{{ tt('Editorial pick', '编辑精选') }}</span>
          </div>
          <div class="collab-body">
            <b class="collab-name">{{ c[1] }}</b>
            <p class="collab-desc">{{ tt(c[2], c[3]) }}</p>
            <router-link to="/store?sort=new" class="btn btn-secondary btn-sm">{{ tt('Shop new arrivals →', '去逛最新上架 →') }}</router-link>
          </div>
        </div>
      </div>

      <!-- 合作流程三步 -->
      <div class="collab-flow">
        <div v-for="(s, i) in STEPS" :key="s[1]" class="cf-step" :class="{ 'cf-mid': i === 1 }">
          <div class="cf-ico">{{ s[0] }}</div>
          <div class="cf-no">{{ '0' + (i + 1) }}</div>
          <b class="cf-t">{{ tt(s[1], s[2]) }}</b>
          <p class="cf-d">{{ tt(s[3], s[4]) }}</p>
        </div>
      </div>

      <!-- 申请区：左条件清单 + 右渐变 CTA -->
      <div class="collab-apply">
        <div class="ca-left">
          <b class="ca-t">{{ tt('Want to collab?', '想和我们联名？') }}</b>
          <ul class="ca-reqs">
            <li v-for="r in REQS" :key="r[1]">
              <span class="ca-ico">{{ r[0] }}</span>{{ tt(r[1], r[2]) }}
            </li>
          </ul>
          <p class="ca-note">
            {{ tt(
              'We review every application within a week.',
              '每周内回复所有申请。',
            ) }}
          </p>
        </div>
        <div class="ca-right">
          <b class="ca-cta-t">{{ tt('Ready to drop your capsule?', '准备好推出你的联名系列了吗？') }}</b>
          <p class="ca-cta-d">
            {{ tt(
              'Send us your handle, audience and 3 photos of your best sets — we co-plan the drop, product and revenue share together.',
              '把你的社交账号、粉丝画像和 3 张最佳作品发给我们——一起策划联名款、选品与分成。',
            ) }}
          </p>
          <div class="ca-btns">
            <router-link :to="{ path: '/contact', query: { subject: 'Collab application' } }" class="btn btn-primary btn-sm">{{ tt('Apply via Contact', '通过联系页申请') }}</router-link>
            <a href="mailto:collabs@glowmag.com?subject=Collab%20application" class="btn ca-mail">{{ tt('Email collabs@glowmag.com', '邮件 collabs@glowmag.com') }}</a>
          </div>
        </div>
      </div>

    </div>
  </section>
</template>

<style scoped>
/* Hero：rose-pale 渐变面板 + 居中排版（对齐 AboutView hero 语言） */
.collab-hero {
  text-align: center;
  padding: 46px 24px 38px;
  border-radius: 20px;
  background: linear-gradient(180deg, var(--rose-pale), #fff);
  border: 1px solid var(--rose-light);
  margin-bottom: 34px;
  position: relative;
  overflow: hidden;
}
.collab-hero::after {
  content: "";
  position: absolute;
  top: -70px; right: -70px;
  width: 220px; height: 220px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(232,180,184,.35), transparent 70%);
  pointer-events: none;
}
.collab-kicker {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--plum);
  background: #fff;
  border: 1px solid var(--rose-light);
  border-radius: 999px;
  padding: 5px 14px;
  margin-bottom: 14px;
}
.collab-title { font-family: var(--font-title); font-size: 36px; letter-spacing: -.5px; margin-bottom: 8px; }
.collab-sub { color: var(--gray); max-width: 460px; margin: 0 auto; }
.collab-stats {
  display: flex;
  justify-content: center;
  gap: 14px;
  margin-top: 22px;
  flex-wrap: wrap;
}
.cs-item {
  background: #fff;
  border: 1px solid var(--rose-light);
  border-radius: 12px;
  padding: 10px 22px;
  min-width: 108px;
  box-shadow: 0 2px 8px rgba(138,74,99,.05);
}
.cs-item b { display: block; font-family: var(--font-title); font-size: 22px; color: var(--plum); line-height: 1.2; }
.cs-item span { font-size: 11.5px; color: var(--gray); }

/* 合辑卡：hover 整卡浮起 + 图缩放；图上浮 handle / 精选角标 */
.collab-grid { margin-bottom: 34px; }
.collab-card { padding: 0; overflow: hidden; transition: transform .2s ease-out, box-shadow .2s ease-out; }
.collab-card:hover { transform: translateY(-3px); box-shadow: var(--shadow-pop); }
.collab-img { position: relative; overflow: hidden; }
.collab-img img { width: 100%; aspect-ratio: 4/3; object-fit: cover; display: block; transition: transform .35s ease-out; }
.collab-card:hover .collab-img img { transform: scale(1.04); }
.collab-handle {
  position: absolute;
  left: 12px; bottom: 12px;
  background: rgba(255,255,255,.92);
  backdrop-filter: blur(4px);
  color: var(--plum);
  font-size: 12px;
  font-weight: 700;
  padding: 4px 12px;
  border-radius: 999px;
  box-shadow: 0 2px 8px rgba(31,27,30,.15);
}
.collab-flag {
  position: absolute;
  top: 12px; right: 12px;
  background: rgba(138,74,99,.88);
  color: #fff;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: .5px;
  padding: 4px 10px;
  border-radius: 999px;
}
.collab-body { padding: 18px; }
.collab-name { display: block; font-family: var(--font-title); font-size: 19px; margin-bottom: 4px; }
.collab-desc { font-size: 13px; color: var(--gray); margin: 0 0 14px; }

/* 合作流程：三步卡（中步上移错位） */
.collab-flow { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 34px; }
.cf-step {
  position: relative;
  background: #fff;
  border: 1px solid var(--gray-light);
  border-radius: 14px;
  padding: 20px 18px 18px;
  box-shadow: 0 2px 10px rgba(31,27,30,.03);
}
.cf-mid { transform: translateY(-8px); border-color: var(--rose-light); background: linear-gradient(180deg, #fff, var(--rose-pale)); }
.cf-ico { font-size: 26px; line-height: 1; margin-bottom: 10px; }
.cf-no {
  position: absolute;
  top: 14px; right: 16px;
  font-family: var(--font-title);
  font-size: 26px;
  font-weight: 700;
  color: var(--rose-light);
  line-height: 1;
}
.cf-t { display: block; font-size: 14.5px; margin-bottom: 4px; color: var(--ink); }
.cf-d { font-size: 12.5px; color: var(--gray); margin: 0; line-height: 1.65; }

/* 申请区：左清单 + 右渐变 CTA 双栏 */
.collab-apply {
  display: grid;
  grid-template-columns: 1fr 1.2fr;
  gap: 0;
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid var(--gray-light);
  box-shadow: 0 2px 12px rgba(31,27,30,.04);
}
.ca-left { background: #fff; padding: 26px 24px; }
.ca-t { display: block; font-family: var(--font-title); font-size: 18px; margin-bottom: 14px; }
.ca-reqs { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }
.ca-reqs li { display: flex; align-items: center; gap: 10px; font-size: 13.5px; color: var(--ink); }
.ca-ico {
  width: 30px; height: 30px;
  flex: none;
  border-radius: 50%;
  background: var(--rose-pale);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}
.ca-note { font-size: 12.5px; color: var(--gray); margin: 14px 0 0; }
.ca-right {
  background: linear-gradient(135deg, var(--rose) 0%, var(--plum) 100%);
  color: #fff;
  padding: 26px 24px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.ca-cta-t { display: block; font-family: var(--font-title); font-size: 18px; margin-bottom: 8px; }
.ca-cta-d { font-size: 13px; line-height: 1.75; opacity: .92; margin: 0 0 18px; }
.ca-btns { display: flex; gap: 10px; flex-wrap: wrap; }
.ca-mail { border: 1.5px solid rgba(255,255,255,.55); color: #fff; background: transparent; }
.ca-mail:hover { background: rgba(255,255,255,.14); }

@media (max-width: 768px) {
  .collab-title { font-size: 30px; }
  .collab-hero { padding: 34px 18px 28px; }
  .cs-item { padding: 8px 16px; min-width: 92px; }
  .collab-flow { grid-template-columns: 1fr; gap: 10px; }
  .cf-mid { transform: none; }
  .collab-apply { grid-template-columns: 1fr; }
  .ca-right { padding: 22px 20px; }
}
</style>
