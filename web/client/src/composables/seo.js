/* GLOWMAG SEO 基建 —— meta/OG/Twitter/canonical/JSON-LD 注入与清理（Vue3 组合式，零依赖，SSR 安全）
 *
 * 三层接入：
 *   1) 路由级兜底：router.afterEach 调 applyRouteSeo(to)。title 沿用路由表 meta.title，
 *      description 查下方 ROUTE_SEO 表，canonical = location.origin + path
 *      （product / blog-post 详情页带 ?slug= 或 ?id=，保留 query 唯一化 URL）
 *   2) 页面级动态数据（views 数据就绪后）：dispatchEvent(new CustomEvent('gm:seo', { detail: {...} }))
 *      —— views 未发事件也不报错，保持路由级兜底
 *   3) 页面级直调：import { setSeo } / useSeo（事件与直调走同一合并逻辑，未来 views 接入用）
 */

const MARK = 'data-gm-seo' // 本模块动态创建的标签标记（canonical/JSON-LD 重建时清理）
const JSONLD_ID = 'gm-jsonld'

const SITE = {
  name: 'GLOWMAG',
  baseTitle: 'GLOWMAG · Press-On Nails & Magnetic Lashes',
  titleSuffix: ' · GLOWMAG',
  description: 'Shop handmade press-on nails & magnetic lashes. Salon-quality glam in 5 minutes, 2-week wear. Free US shipping over $35.',
  image: '/og-cover.png',
  type: 'website',
}

/* 路由级 description（title 由路由表 meta 提供；未列出路由回落默认文案） */
const ROUTE_SEO = {
  store: 'Shop all handmade press-on nail sets and magnetic lashes — every shape, length and finish. Reusable, salon-quality glam shipped free over $35.',
  product: 'Handmade press-on nails with a salon-quality finish — pick your shape, length and art. 2-week wear, application in 5 minutes.',
  sale: 'Limited-time deals on handmade press-on nails and magnetic lashes — save on best sellers and last-chance glam while sets last.',
  bundles: 'Bundle & save on press-on nails, magnetic lashes and care kits — curated GLOWMAG sets at a better price.',
  gallery: 'Real GLOWMAG glam from the community — press-on nails and magnetic lashes worn by customers worldwide. #GLOWMAGGlam',
  blog: 'Nail care tips, trend guides and glam stories from the GLOWMAG team — everything press-on nails and magnetic lashes.',
  'blog-post': 'Nail care tips, trend guides and glam stories from the GLOWMAG team — everything press-on nails and magnetic lashes.',
  faq: 'Answers on sizing, application, wear time, shipping, returns and care for GLOWMAG press-on nails and magnetic lashes.',
  about: 'The story behind GLOWMAG — why we handcraft press-on nails and magnetic lashes for salon-quality glam at home.',
  'how-it-works': 'How GLOWMAG works — measure, apply, wear. Salon-quality press-on nails and magnetic lashes in 5 minutes.',
  'size-guide': 'Find your perfect fit — measuring tips and full size charts for GLOWMAG press-on nails and magnetic lashes.',
  contact: 'Questions about orders, sizing or wholesale? Reach the GLOWMAG team — we reply within one business day.',
  rewards: 'Earn Glow Points on every order, review and referral — redeem them for discounts on press-on nails and magnetic lashes.',
  refer: 'Refer a friend to GLOWMAG — you both earn rewards toward handmade press-on nails and magnetic lashes.',
  subscribe: 'GLOWMAG Nail Club — a fresh handcrafted press-on nail set delivered monthly. Pause or cancel anytime.',
  'gift-cards': 'Give the gift of glam — digital GLOWMAG gift cards for handmade press-on nails and magnetic lashes.',
  collabs: 'Limited-edition press-on nail sets from GLOWMAG collabs with artists and creators — once they are gone, they are gone.',
  privacy: 'How GLOWMAG collects, uses and protects your personal data — cookies, retention, and your GDPR & CCPA rights.',
  terms: 'The terms of service for shopping GLOWMAG — orders, payment, shipping, returns and intellectual property.',
  'shipping-policy': 'GLOWMAG shipping rates and speeds — US and international delivery, processing times, tracking and lost parcels.',
  'returns-policy': 'GLOWMAG returns & exchanges — 30-day returns, always-free exchanges and what is final sale.',
  unsubscribe: 'Manage your GLOWMAG email preferences — opt in or out of promos, new arrivals and cart reminders anytime.',
}

/* 站内确认不收录的路由（路由 meta.noindex 由 router 配置时同样生效） */
const NOINDEX_ROUTES = new Set(['unsubscribe'])

let base = {} // 最近一次路由级 meta（页面级注入在其上合并，保证 canonical 等不被局部 detail 抹掉）
let current = {} // 累计生效 meta（路由切换整体重置，避免上一页动态数据残留）

const hasDoc = () => typeof document !== 'undefined'

function absUrl(u) {
  if (!u) return ''
  if (/^https?:\/\//i.test(u)) return u
  if (typeof location === 'undefined') return u
  try { return new URL(u, location.origin).href } catch { return u }
}

/* 更新 head meta：index.html 预置的静态标签原地改写，缺失则带 MARK 新建 */
function upsertMeta(kind, key, content) {
  if (!hasDoc() || content == null) return
  let el = document.head.querySelector(`meta[${kind}="${key}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(kind, key)
    el.setAttribute(MARK, '')
    document.head.appendChild(el)
  }
  el.setAttribute('content', String(content))
}

function setCanonical(href) {
  if (!hasDoc() || !href) return
  document.head.querySelectorAll(`link[rel="canonical"][${MARK}]`).forEach((el) => el.remove())
  const el = document.createElement('link')
  el.setAttribute('rel', 'canonical')
  el.setAttribute('href', href)
  el.setAttribute(MARK, '')
  document.head.appendChild(el)
}

/* noindex 开关：注入 <meta name="robots" content="noindex">；关闭时仅移除本模块注入的（不动 index.html 静态标签） */
function setNoindex(on) {
  if (!hasDoc()) return
  if (on) upsertMeta('name', 'robots', 'noindex')
  else document.head.querySelectorAll(`meta[name="robots"][${MARK}]`).forEach((el) => el.remove())
}

function clearJsonLd() {
  if (hasDoc()) document.head.querySelectorAll(`script#${JSONLD_ID}`).forEach((el) => el.remove())
}

function setJsonLd(data) {
  if (!hasDoc()) return
  clearJsonLd()
  const items = Array.isArray(data) ? data : [data]
  const payload = items.length === 1 ? items[0] : { '@context': 'https://schema.org', '@graph': items }
  const el = document.createElement('script')
  el.setAttribute('type', 'application/ld+json')
  el.setAttribute('id', JSONLD_ID)
  el.textContent = JSON.stringify(payload)
  document.head.appendChild(el)
}

function render(m) {
  if (!hasDoc()) return
  const title = m.title || SITE.baseTitle
  const description = m.description || SITE.description
  const image = absUrl(m.image || SITE.image)
  const url = absUrl(m.url || (typeof location !== 'undefined' ? location.pathname + location.search : ''))
  document.title = title
  upsertMeta('name', 'description', description)
  upsertMeta('property', 'og:title', title)
  upsertMeta('property', 'og:description', description)
  upsertMeta('property', 'og:site_name', SITE.name)
  upsertMeta('property', 'og:type', m.type || SITE.type)
  upsertMeta('property', 'og:url', url)
  upsertMeta('property', 'og:image', image)
  upsertMeta('name', 'twitter:card', 'summary_large_image')
  upsertMeta('name', 'twitter:title', title)
  upsertMeta('name', 'twitter:description', description)
  upsertMeta('name', 'twitter:image', image)
  setCanonical(url)
  setNoindex(!!m.noindex)
  if (m.jsonLd && (Array.isArray(m.jsonLd) ? m.jsonLd.length : true)) setJsonLd(m.jsonLd)
  else clearJsonLd()
}

/* 页面级注入：与已生效 meta 合并后渲染（传局部字段即可，未传字段保持现状） */
export function setSeo(meta = {}) {
  const patch = Object.fromEntries(Object.entries(meta).filter(([, v]) => v != null && v !== false))
  current = { ...current, ...patch }
  render(current)
}

/* 路由级兜底：整体重置 current（清掉上一页动态残留）；首页附 Organization + WebSite 结构化数据 */
export function applyRouteSeo(route) {
  const name = route && route.name ? String(route.name) : ''
  /* 详情页语义在 query（slug / id）：canonical 保留 query 才能唯一化，其余路由去掉 query */
  const detailSlug = (name === 'product' || name === 'blog-post') && route.query && (route.query.slug || route.query.id)
  base = {
    title: route && route.meta && route.meta.title ? route.meta.title + SITE.titleSuffix : SITE.baseTitle,
    description: ROUTE_SEO[name] || SITE.description,
    image: SITE.image,
    url: detailSlug && route.fullPath ? route.fullPath : (route ? route.path : '/'),
    type: 'website',
    noindex: !!(route && route.meta && route.meta.noindex) || NOINDEX_ROUTES.has(name),
  }
  if (name === 'home') {
    const origin = typeof location !== 'undefined' ? location.origin : ''
    base.jsonLd = [
      { '@context': 'https://schema.org', '@type': 'Organization', name: SITE.name, url: origin, logo: absUrl(SITE.image) },
      {
        '@context': 'https://schema.org',
        '@type': 'WebSite',
        name: SITE.name,
        url: origin,
        potentialAction: {
          '@type': 'SearchAction',
          target: origin + '/search?q={search_term_string}',
          'query-input': 'required name=search_term_string',
        },
      },
    ]
  }
  current = { ...base }
  render(current)
}

/* 组合式入口：立即应用初始 meta 并返回 setSeo（未来 views 接入用） */
export function useSeo(init = {}) {
  if (init && Object.keys(init).length) setSeo(init)
  return { setSeo }
}

/* 页面级动态数据事件通道：views 数据就绪后 dispatch gm:seo（不发事件则保持路由级兜底） */
if (typeof window !== 'undefined') {
  window.addEventListener('gm:seo', (e) => {
    if (e && e.detail && typeof e.detail === 'object') setSeo(e.detail)
  })
}
