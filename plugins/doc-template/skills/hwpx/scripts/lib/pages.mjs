import { readHwpx, readText } from './package.mjs'
import { parseXml, serializeXml, children, descendants } from './dom.mjs'
import { scanXml } from './scan.mjs'
import { isImageKey } from './tokens.mjs'

export function splitPages(doc) {
  const pages = [[]]
  for (const para of children(doc.documentElement, 'p')) {
    if (para.getAttribute('pageBreak') === '1' && pages.at(-1).length) pages.push([])
    pages.at(-1).push(para)
  }
  return pages
}

export async function listPages(bytes) {
  const { zip, sectionNames } = await readHwpx(bytes)
  const pages = []
  const warnings = []
  for (const [si, name] of sectionNames.entries()) {
    const doc = parseXml(await readText(zip, name))
    const nested = descendants(doc.documentElement, 'p')
      .filter((x) => x.parentNode !== doc.documentElement && x.getAttribute('pageBreak') === '1')
    if (nested.length) warnings.push(`구역 ${si}: 표 안 문단에 쪽 나눔이 ${nested.length}개 있습니다. 페이지 경계로 쓰지 않습니다.`)
    for (const paras of splitPages(doc)) {
      const xml = paras.map((x) => serializeXml(x)).join('')
      const { counts } = scanXml(xml)
      pages.push({
        page: pages.length + 1,
        section: si,
        fields: [...counts].map(([n, c]) => ({ name: n, count: c, image: isImageKey(n) })),
      })
    }
  }
  return { pages, warnings }
}
