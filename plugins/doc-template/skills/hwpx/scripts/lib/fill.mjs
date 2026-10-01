import { readHwpx, readText, writeHwpx } from './package.mjs'
import { parseXml, serializeXml, descendants } from './dom.mjs'
import { tokenRe } from './tokens.mjs'

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

export async function fill(bytes, input = {}, opts = {}) {
  const values = input.values ?? {}
  const report = newReport()
  const { zip, sectionNames } = await readHwpx(bytes)
  const seen = new Set()
  for (const name of sectionNames) {
    const doc = parseXml(await readText(zip, name))
    replaceTextTokens(doc.documentElement, (k) => values[k], report, seen)
    for (const ls of descendants(doc.documentElement, 'linesegarray')) ls.parentNode.removeChild(ls)
    zip.file(name, serializeXml(doc))
  }
  report.unknownKeys = Object.keys(values).filter((k) => !seen.has(k))
  return { bytes: await writeHwpx(zip), report }
}
