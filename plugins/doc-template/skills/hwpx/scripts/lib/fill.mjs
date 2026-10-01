import { readHwpx, readText, writeHwpx } from './package.mjs'
import { parseXml, serializeXml, descendants } from './dom.mjs'
import { tokenRe } from './tokens.mjs'
import { composePages } from './pages.mjs'

const present = (v) => v !== undefined && v !== null && v !== ''

export function newReport() {
  return { filled: {}, missing: [], unknownKeys: [], warnings: [] }
}

// hp:t 의 텍스트 노드 안 토큰만 바꾼다. DOM 텍스트로 넣으므로 이스케이프는 직렬화가 한다.
export function replaceTextTokens(root, lookup, report, seen = new Set()) {
  for (const t of descendants(root, 't')) {
    for (const node of Array.from(t.childNodes)) {
      if (node.nodeType !== 3 || !node.data.includes('{{')) continue
      node.data = node.data.replace(tokenRe(), (_, raw) => {
        const name = raw.trim()
        seen.add(name)
        const v = lookup(name)
        if (!present(v)) {
          if (!report.missing.includes(name)) report.missing.push(name)
          return ''
        }
        report.filled[name] = (report.filled[name] ?? 0) + 1
        return String(v)
      })
    }
  }
  return seen
}

const own = (obj, k) => (obj && Object.hasOwn(obj, k) ? obj[k] : undefined)

export async function fill(bytes, input = {}, opts = {}) {
  const values = input.values ?? {}
  const report = newReport()
  const { zip, sectionNames } = await readHwpx(bytes)
  if (input.pages && sectionNames.length > 1)
    throw new Error('pages 구성은 구역이 하나인 서식만 지원합니다. XML 을 직접 편집하세요 (references/xml-edit.md).')
  if (input.pages !== undefined && input.pages !== null) {
    const ok = Array.isArray(input.pages) && input.pages.length > 0 &&
      input.pages.every((e) => e && typeof e === 'object' && Number.isInteger(e.page))
    if (!ok) throw new Error('pages 는 1개 이상의 {page:번호} 목록이어야 합니다.')
  }
  const seen = new Set()
  const pageValueKeys = new Set()
  // 페이지별 값 우선, 없으면 공통 값. 상속 속성(constructor 등)은 값으로 보지 않는다.
  const lookupFor = (pv) => (k) => (present(own(pv, k)) ? pv[k] : own(values, k))
  for (const name of sectionNames) {
    const doc = parseXml(await readText(zip, name))
    if (input.pages) {
      composePages(doc, input.pages, (paras, entry) => {
        Object.keys(entry.values ?? {}).forEach((k) => pageValueKeys.add(k))
        for (const x of paras) replaceTextTokens(x, lookupFor(entry.values), report, seen)
      })
    } else {
      replaceTextTokens(doc.documentElement, lookupFor(), report, seen)
    }
    for (const ls of descendants(doc.documentElement, 'linesegarray')) ls.parentNode.removeChild(ls)
    zip.file(name, serializeXml(doc))
  }
  report.unknownKeys = [...new Set([...Object.keys(values), ...pageValueKeys])].filter((k) => !seen.has(k))
  return { bytes: await writeHwpx(zip), report }
}
