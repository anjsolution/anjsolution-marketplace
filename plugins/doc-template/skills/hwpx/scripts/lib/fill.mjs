import { readFileSync, existsSync, statSync } from 'node:fs'
import { resolve, basename } from 'node:path'
import { createHash } from 'node:crypto'
import { readHwpx, readText, writeHwpx, addBinItem, listManifestIds } from './package.mjs'
import { parseXml, serializeXml, descendants, children, closest, NS } from './dom.mjs'
import { tokenRe, isImageKey, isImagePath } from './tokens.mjs'
import { composePages } from './pages.mjs'
import { readImageInfo, orientationInfo, fitBox, buildPicXml, MEDIA, HWP_PER_MM } from './image.mjs'

const present = (v) => v !== undefined && v !== null && v !== ''

export function newReport() {
  return { filled: {}, missing: [], unknownKeys: [], warnings: [], images: [] }
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

const FIT = 0.98   // 인라인 그림이 문단 줄 높이까지 더해 셀을 넘지 않도록 여유

function imageBox(t, doc) {
  const tc = closest(t, 'tc')
  if (tc) {
    const sz = children(tc, 'cellSz')[0]
    let m = children(tc, 'cellMargin')[0]
    if (tc.getAttribute('hasMargin') === '0') m = children(closest(tc, 'tbl'), 'inMargin')[0] ?? m
    const n = (el, a) => Number(el?.getAttribute(a) ?? 0)
    return {
      boxW: (n(sz, 'width') - n(m, 'left') - n(m, 'right')) * FIT,
      boxH: (n(sz, 'height') - n(m, 'top') - n(m, 'bottom')) * FIT,
    }
  }
  const pagePr = doc.getElementsByTagNameNS('*', 'pagePr')[0]
  const mg = doc.getElementsByTagNameNS('*', 'margin')[0]
  if (!pagePr || !mg) return { boxW: 40000, boxH: 30000 }
  const n = (el, a) => Number(el.getAttribute(a))
  const textW = n(pagePr, 'width') - n(mg, 'left') - n(mg, 'right')
  const textH = n(pagePr, 'height') - n(mg, 'top') - n(mg, 'bottom') - n(mg, 'header') - n(mg, 'footer')
  return { boxW: textW * FIT, boxH: (textH / 2) * FIT }
}

// 구역 안 기존 id/instid 의 최댓값. 그림 id 는 이보다 큰 수부터 발급해 어떤 개체와도 겹치지 않게 한다.
function maxExistingId(doc) {
  let max = 0
  for (const e of descendants(doc.documentElement, '*')) for (const a of ['id', 'instid']) {
    const v = Number(e.getAttribute(a))
    if (Number.isInteger(v) && v > max) max = v
  }
  return max
}

// 문서 단위 이미지 상태: 같은 파일은 BinData 하나를 공유
async function makeImageContext(zip, baseDir, report) {
  const used = new Set(await listManifestIds(zip))
  const byHash = new Map()
  let nextId = 1
  return {
    startIds: (doc) => { nextId = maxExistingId(doc) + 1 },
    newId: () => nextId++,
    async bin(key, value) {
      const rel = typeof value === 'object' ? value.path : value
      const file = resolve(baseDir ?? process.cwd(), rel.trim())
      if (!existsSync(file)) throw new Error(`${key}: 이미지 파일이 없습니다: ${file}`)
      const buf = readFileSync(file)
      let info
      try { info = readImageInfo(buf) } catch (e) { throw new Error(`${key}: ${e.message} (${file})`) }
      if (statSync(file).size > 5 * 1024 * 1024)
        report.warnings.push(`${basename(file)}: 5MB 를 넘습니다. 문서가 커질 수 있습니다.`)
      const o = orientationInfo(info.orientation)
      if (o.mirrored) report.warnings.push(`${basename(file)}: 좌우 반전 정보는 무시하고 회전만 반영했습니다.`)
      const hash = createHash('sha1').update(buf).digest('hex')
      if (!byHash.has(hash)) {
        let n = 1
        while (used.has(`image${n}`)) n++
        const binId = `image${n}`
        used.add(binId)
        const href = `BinData/${binId}.${info.type}`
        zip.file(href, buf)
        await addBinItem(zip, { id: binId, href, mediaType: MEDIA[info.type] })
        byHash.set(hash, binId)
      }
      return { file, info, o, binId: byHash.get(hash) }
    },
  }
}

const PIC_WRAP = `<w xmlns:hp="${NS.hp}" xmlns:hc="${NS.hc}">`

// 이미지 자리 토큰을 그림으로 바꾼다. 텍스트 치환보다 먼저 실행한다.
async function placeImages(root, doc, lookup, ctx, report, seen) {
  for (const t of descendants(root, 't')) {
    const text = t.textContent
    if (!text.includes('{{')) continue
    for (const m of text.matchAll(tokenRe())) {
      const key = m[1].trim()
      const value = lookup(key)
      if (!present(value)) continue
      if (!isImagePath(value)) {
        const w = `${key}: 이미지 자리에 글자를 넣었습니다 (이미지 경로가 아님).`
        if (isImageKey(key) && !report.warnings.includes(w)) report.warnings.push(w)
        continue
      }
      seen.add(key)
      const { file, info, o, binId } = await ctx.bin(key, value)
      const [imgW, imgH] = o.swap ? [info.height, info.width] : [info.width, info.height]
      const opt = typeof value === 'object' ? value : {}
      const disp = fitBox({
        ...imageBox(t, doc), imgW, imgH,
        maxW: opt.width_mm ? opt.width_mm * HWP_PER_MM : undefined,
        maxH: opt.height_mm ? opt.height_mm * HWP_PER_MM : undefined,
      })
      const picXml = buildPicXml({
        id: ctx.newId(), instid: ctx.newId(), binId,
        pxW: info.width, pxH: info.height, dispW: disp.w, dispH: disp.h, angle: o.angle,
      })
      const pic = parseXml(`${PIC_WRAP}${picXml}</w>`).documentElement.firstChild
      t.parentNode.insertBefore(doc.importNode(pic, true), t.nextSibling)
      for (const node of Array.from(t.childNodes)) if (node.nodeType === 3) node.data = node.data.split(m[0]).join('')
      report.filled[key] = (report.filled[key] ?? 0) + 1
      report.images.push({
        key, file, binId, angle: o.angle,
        widthMm: Math.round(disp.w / HWP_PER_MM), heightMm: Math.round(disp.h / HWP_PER_MM),
      })
    }
  }
}

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
  const ctx = await makeImageContext(zip, opts.baseDir, report)
  const seen = new Set()
  const pageValueKeys = new Set()
  // 페이지별 값 우선, 없으면 공통 값. 상속 속성(constructor 등)은 값으로 보지 않는다.
  const lookupFor = (pv) => (k) => (present(own(pv, k)) ? pv[k] : own(values, k))
  for (const name of sectionNames) {
    const doc = parseXml(await readText(zip, name))
    const jobs = []
    if (input.pages) {
      composePages(doc, input.pages, (paras, entry) => {
        Object.keys(entry.values ?? {}).forEach((k) => pageValueKeys.add(k))
        jobs.push({ roots: paras, lookup: lookupFor(entry.values) })
      })
    } else {
      jobs.push({ roots: [doc.documentElement], lookup: lookupFor() })
    }
    ctx.startIds(doc)   // composePages 의 id 재부여가 끝난 뒤 기준으로 발급
    for (const job of jobs) for (const r of job.roots) {
      await placeImages(r, doc, job.lookup, ctx, report, seen)
      replaceTextTokens(r, job.lookup, report, seen)
    }
    for (const ls of descendants(doc.documentElement, 'linesegarray')) ls.parentNode.removeChild(ls)
    zip.file(name, serializeXml(doc))
  }
  report.unknownKeys = [...new Set([...Object.keys(values), ...pageValueKeys])].filter((k) => !seen.has(k))
  return { bytes: await writeHwpx(zip), report }
}
