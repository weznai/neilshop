/* 演示目录种子（快速首屏/本地回退卡片 · 真实数据一律以 API 为准）
   对齐 server/scripts/seed.py 全新库 16 款可见商品：id 随自增顺序（睫毛 1-3 → 美甲 4-15 → 胶水 16），
   价格/库存/取色与 seed 基线一致；velvet-nights 为定时上架（前台不可见）不入兜底 */
export const GM_CATALOG = [
  { id: 1, title: 'Venus Lash', titleZh: '维纳斯睫毛', price: 12.99, stock: 52, cat: 'lashes', img: 'https://placehold.co/200x200/E8C5D8/552338?text=Venus+Lash' },
  { id: 2, title: 'Aurora Lash', titleZh: '极光睫毛', price: 9.99, stock: 30, cat: 'lashes', img: 'https://placehold.co/200x200/DDD6E8/552338?text=Aurora+Lash' },
  { id: 3, title: 'Midnight Lash', titleZh: '午夜睫毛', price: 15.99, stock: 18, cat: 'lashes', img: 'https://placehold.co/200x200/FBEBD4/8A6D3B?text=Midnight+Lash' },
  { id: 4, title: 'Ma Damn', titleZh: '玛丹', price: 15.99, stock: 34, cat: 'nails', img: 'https://placehold.co/200x200/F5D8DA/6D2E46?text=Ma+Damn' },
  { id: 5, title: 'Winter Storm', titleZh: '冬季风暴', price: 15.99, stock: 8, cat: 'nails', img: 'https://placehold.co/200x200/E8B4B8/552338?text=Winter+Storm' },
  { id: 6, title: 'Bare Gems', titleZh: '裸钻', price: 15.99, stock: 120, cat: 'nails', img: 'https://placehold.co/200x200/E8C5D8/552338?text=Bare+Gems' },
  { id: 7, title: 'French Kiss', titleZh: '法式之吻', price: 14.99, stock: 56, cat: 'nails', img: 'https://placehold.co/200x200/DDD6E8/552338?text=French+Kiss' },
  { id: 8, title: 'Cherry Bomb', titleZh: '樱桃炸弹', price: 13.99, stock: 0, cat: 'nails', img: 'https://placehold.co/200x200/FBEBD4/8A6D3B?text=Cherry+Bomb' },
  { id: 9, title: 'Golden Hour', titleZh: '黄金时刻', price: 17.99, stock: 23, cat: 'nails', img: 'https://placehold.co/200x200/F5D8DA/6D2E46?text=Golden+Hour' },
  { id: 10, title: 'Cloud Nine', titleZh: '九霄云上', price: 15.99, stock: 41, cat: 'nails', img: 'https://placehold.co/200x200/E8B4B8/552338?text=Cloud+Nine' },
  { id: 11, title: 'Midnight Muse', titleZh: '午夜缪斯', price: 16.99, stock: 3, cat: 'nails', img: 'https://placehold.co/200x200/E8C5D8/552338?text=Midnight+Muse' },
  { id: 12, title: 'Peachy Keen', titleZh: '蜜桃乌龙', price: 12.99, stock: 67, cat: 'nails', img: 'https://placehold.co/200x200/DDD6E8/552338?text=Peachy+Keen' },
  { id: 13, title: 'Venus', titleZh: '维纳斯', price: 19.99, stock: 88, cat: 'nails', img: 'https://placehold.co/200x200/FBEBD4/8A6D3B?text=Venus' },
  { id: 14, title: 'Aurora', titleZh: '极光', price: 17.99, stock: 45, cat: 'nails', img: 'https://placehold.co/200x200/F5D8DA/6D2E46?text=Aurora' },
  { id: 15, title: 'Nova', titleZh: '新星', price: 15.99, stock: 0, cat: 'nails', img: 'https://placehold.co/200x200/E8B4B8/552338?text=Nova' },
  { id: 16, title: 'Magic Glue', titleZh: '魔力胶水', price: 13.99, stock: 50, cat: 'tools', img: 'https://placehold.co/200x200/DDD6E8/552338?text=Magic+Glue' },
]

/* 分类短别名 → 后端真实 slug（导航/旧链接 ?cat=nails|lashes；StoreView 与 StoreLayout 共用） */
export const CAT_ALIAS = { nails: 'press-on-nails', lashes: 'magnetic-lashes' }

export function catalogById(id) {
  return GM_CATALOG.find((p) => p.id === id) || null
}
