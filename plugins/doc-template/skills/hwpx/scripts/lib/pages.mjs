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

// 구역 정의(secPr)와 단 정의(colPr 를 담은 ctrl)는 문서 첫 문단에 한 번만 있어야 한다
const isHeadPart = (c) => c.localName === 'secPr' || (c.localName === 'ctrl' && children(c, 'colPr').length > 0)
const headParts = (para) => children(para, 'run').flatMap((run) => children(run).filter(isHeadPart).map((el) => ({ el, run })))

// 번호를 다시 매길 개체 요소 (필드·책갈피 등의 id 는 건드리지 않는다)
const OBJECT_TAGS = new Set(['tbl', 'pic', 'container', 'rect', 'ellipse', 'line', 'arc', 'polygon', 'curve',
  'connectLine', 'ole', 'equation', 'textart', 'video', 'chart'])

export function renumberIds(doc) {
  const all = descendants(doc.documentElement, '*').filter((e) => OBJECT_TAGS.has(e.localName))
  const big = 2 ** 31
  let max = 0
  for (const e of all) for (const a of ['id', 'instid']) {
    const v = Number(e.getAttribute(a))
    if (Number.isInteger(v) && v > 0 && v < big) max = Math.max(max, v)
  }
  const seen = new Set()
  for (const e of all) for (const a of ['id', 'instid']) {
    const raw = e.getAttribute(a)
    const v = Number(raw)
    if (!raw || !Number.isInteger(v) || v <= 0 || v >= big) continue
    const key = `${a}:${v}`
    if (seen.has(key)) e.setAttribute(a, String(++max))
    else seen.add(key)
  }
}

export function composePages(doc, spec, onPage) {
  const root = doc.documentElement
  const original = splitPages(doc)
  if (!original[0].length) throw new Error('구역에 문단이 없어 페이지를 구성할 수 없습니다.')
  for (const entry of spec) {
    if (!Number.isInteger(entry.page) || entry.page < 1 || entry.page > original.length)
      throw new Error(`페이지 ${entry.page} 이(가) 서식에 없습니다. 서식 페이지는 1~${original.length} 입니다.`)
  }
  // 원본 첫 문단의 구역·단 정의를 치환 전에 복제해 둔다
  const head = headParts(original[0][0])
  const headClones = head.map(({ el }) => el.cloneNode(true))
  const headCharPr = head[0]?.run.getAttribute('charPrIDRef') ?? '0'
  for (const paras of original) for (const x of paras) root.removeChild(x)

  spec.forEach((entry, i) => {
    const copies = original[entry.page - 1].map((x) => x.cloneNode(true))
    if (entry.page === 1) for (const { el } of headParts(copies[0])) el.parentNode.removeChild(el)
    copies.forEach((x, j) => x.setAttribute('pageBreak', j === 0 && i > 0 ? '1' : '0'))
    for (const x of copies) root.appendChild(x)
    onPage(copies, entry)
  })

  const first = children(root, 'p')[0]
  if (first && headClones.length) {
    const run = doc.createElementNS(first.namespaceURI, `${first.prefix ? first.prefix + ':' : ''}run`)
    run.setAttribute('charPrIDRef', headCharPr)
    for (const c of headClones) run.appendChild(c)
    first.insertBefore(run, first.firstChild)
  }
  renumberIds(doc)
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
