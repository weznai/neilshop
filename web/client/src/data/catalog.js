/* 演示目录种子（快速首屏/本地回退卡片 · 真实数据一律以 API 为准） */
export const GM_CATALOG = [
  { id: 1, title: 'Ma Damn', titleZh: '玛丹', price: 15.99, stock: 34, cat: 'nails', img: 'https://placehold.co/200x200/F5D8DA/6D2E46?text=Ma+Damn' },
  { id: 2, title: 'Winter Storm', titleZh: '冬季风暴', price: 15.99, stock: 8, cat: 'nails', img: 'https://placehold.co/200x200/E8B4B8/552338?text=Winter+Storm' },
  { id: 3, title: 'Bare Gems', titleZh: '裸钻', price: 15.99, stock: 120, cat: 'nails', img: 'https://placehold.co/200x200/F5D8DA/6D2E46?text=Bare+Gems' },
  { id: 4, title: 'French Kiss', titleZh: '法式之吻', price: 14.99, stock: 56, cat: 'nails', img: 'https://placehold.co/200x200/E8C5D8/552338?text=French+Kiss' },
  { id: 5, title: 'Cherry Bomb', titleZh: '樱桃炸弹', price: 13.99, stock: 0, cat: 'nails', img: 'https://placehold.co/200x200/E8C5D8/552338?text=Cherry+Bomb' },
  { id: 6, title: 'Golden Hour', titleZh: '黄金时刻', price: 17.99, stock: 23, cat: 'nails', img: 'https://placehold.co/200x200/FBEBD4/8A6D3B?text=Golden+Hour' },
  { id: 7, title: 'Cloud Nine', titleZh: '九霄云上', price: 15.99, stock: 41, cat: 'nails', img: 'https://placehold.co/200x200/DDD6E8/552338?text=Cloud+Nine' },
  { id: 8, title: 'Midnight Muse', titleZh: '午夜缪斯', price: 16.99, stock: 3, cat: 'nails', img: 'https://placehold.co/200x200/DDD6E8/552338?text=Midnight+Muse' },
  { id: 9, title: 'Peachy Keen', titleZh: '蜜桃乌龙', price: 12.99, stock: 67, cat: 'nails', img: 'https://placehold.co/200x200/FBEBD4/8A6D3B?text=Peachy+Keen' },
  { id: 10, title: 'Venus Cat-Eye Lashes', titleZh: '维纳斯猫眼睫毛', price: 19.99, stock: 88, cat: 'lashes', img: 'https://placehold.co/200x200/DDD6E8/552338?text=Venus' },
  { id: 11, title: 'Aurora Lashes', titleZh: '极光睫毛', price: 17.99, stock: 45, cat: 'lashes', img: 'https://placehold.co/200x200/E8B4B8/552338?text=Aurora' },
  { id: 12, title: 'Nova Everyday Lashes', titleZh: 'Nova 日常睫毛', price: 15.99, stock: 0, cat: 'lashes', img: 'https://placehold.co/200x200/F5D8DA/6D2E46?text=Nova' },
]

export function catalogById(id) {
  return GM_CATALOG.find((p) => p.id === id) || null
}
