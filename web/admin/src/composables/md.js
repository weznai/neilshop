/* 极简 Markdown 渲染（文章/FAQ 弹窗、商品描述预览共用）：先整体转义再插入标签，防 XSS；
 * 支持 h1-h3（先长后短匹配）/ 无序列表 / 引用 / 粗体 / 斜体 / 链接 / 行内代码，对齐 client BlogPostView 先例 */
export function md2html(src) {
  const esc = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
  const inline = (t) => t
    /* 行内代码先于加粗/链接，避免代码片段被二次加工 */
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/\*([^*]+)\*/g, '<i>$1</i>')
    /* 链接协议白名单：http(s) 外链新窗打开，/ 开头站内路径放行；其余（javascript: 等）剥语法留纯文本 */
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, text, href) => (/^https?:\/\//i.test(href)
      ? `<a href="${href}" target="_blank" rel="noopener">${text}</a>`
      : /^\/(?!\/)/.test(href) ? `<a href="${href}">${text}</a>` : text))
  const out = []
  let ul = false
  const closeUl = () => { if (ul) { out.push('</ul>'); ul = false } }
  for (const raw of esc(src).split(/\r?\n/)) {
    const l = raw.trim()
    let m
    if (!l) { closeUl(); continue }
    if ((m = l.match(/^###\s+(.*)$/))) { closeUl(); out.push(`<h3>${inline(m[1])}</h3>`) }
    else if ((m = l.match(/^##\s+(.*)$/))) { closeUl(); out.push(`<h2>${inline(m[1])}</h2>`) }
    else if ((m = l.match(/^#\s+(.*)$/))) { closeUl(); out.push(`<h1>${inline(m[1])}</h1>`) }
    else if ((m = l.match(/^[-*]\s+(.*)$/))) { if (!ul) { out.push('<ul>'); ul = true } out.push(`<li>${inline(m[1])}</li>`) }
    else if ((m = l.match(/^&gt;\s?(.*)$/))) { closeUl(); out.push(`<blockquote>${inline(m[1])}</blockquote>`) }
    else { closeUl(); out.push(`<p>${inline(l)}</p>`) }
  }
  closeUl()
  return out.join('')
}
