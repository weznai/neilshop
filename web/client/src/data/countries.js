/* 常用国家（2 字母码 + 中英文名，AddressView / CheckoutView 共享）与全站电话格式校验 */
export const COUNTRIES = [
  ['US', 'United States 美国'],
  ['CA', 'Canada 加拿大'],
  ['GB', 'United Kingdom 英国'],
  ['AU', 'Australia 澳大利亚'],
  ['DE', 'Germany 德国'],
  ['FR', 'France 法国'],
  ['NL', 'Netherlands 荷兰'],
  ['NZ', 'New Zealand 新西兰'],
  ['SG', 'Singapore 新加坡'],
  ['JP', 'Japan 日本'],
]
export const PHONE_RE = /^[\+()\-\s\d]{6,20}$/
