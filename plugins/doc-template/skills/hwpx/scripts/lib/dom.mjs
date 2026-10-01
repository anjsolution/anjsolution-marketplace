import { DOMParser, XMLSerializer } from '@xmldom/xmldom'

export const NS = {
  hp: 'http://www.hancom.co.kr/hwpml/2011/paragraph',
  hs: 'http://www.hancom.co.kr/hwpml/2011/section',
  hc: 'http://www.hancom.co.kr/hwpml/2011/core',
}

export function parseXml(str) {
  const errors = []
  const doc = new DOMParser({ errorHandler: { error: (m) => errors.push(m), fatalError: (m) => errors.push(m) } })
    .parseFromString(str, 'text/xml')
  if (errors.length) throw new Error(`XML 파싱 실패: ${errors[0]}`)
  return doc
}

export const serializeXml = (doc) => new XMLSerializer().serializeToString(doc)

const isEl = (n) => n.nodeType === 1
export const children = (el, localName) =>
  Array.from(el.childNodes).filter((n) => isEl(n) && (!localName || n.localName === localName))

export const descendants = (el, localName) => Array.from(el.getElementsByTagNameNS('*', localName))

export function closest(el, localName) {
  for (let n = el; n && isEl(n); n = n.parentNode) if (n.localName === localName) return n
  return null
}
