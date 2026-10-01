import JSZip from 'jszip'

const isSection = (name) => /^Contents\/section\d+\.xml$/.test(name)
const HPF = 'Contents/content.hpf'

export async function readHwpx(bytes) {
  const zip = await JSZip.loadAsync(bytes)
  const sectionNames = Object.keys(zip.files).filter(isSection)
    .sort((a, b) => Number(a.match(/\d+/)[0]) - Number(b.match(/\d+/)[0]))
  if (sectionNames.length === 0) throw new Error('HWPX 본문(Contents/sectionN.xml)을 찾을 수 없습니다.')
  return { zip, sectionNames }
}

export const readText = (zip, name) => zip.file(name).async('string')

// 한글은 mimetype 이 첫 항목·무압축이 아니면 파일을 거부한다.
export async function writeHwpx(zip) {
  const out = new JSZip()
  const mime = zip.file('mimetype')
  out.file('mimetype', mime ? await mime.async('string') : 'application/hwp+zip', { compression: 'STORE' })
  for (const [name, f] of Object.entries(zip.files)) {
    if (name === 'mimetype' || f.dir) continue
    out.file(name, await f.async('uint8array'))
  }
  return out.generateAsync({ type: 'nodebuffer', compression: 'DEFLATE' })
}

export async function listManifestIds(zip) {
  const hpf = await readText(zip, HPF)
  return [...hpf.matchAll(/<opf:item\b[^>]*\bid="([^"]*)"/g)].map((m) => m[1])
}

export async function addBinItem(zip, { id, href, mediaType }) {
  const hpf = await readText(zip, HPF)
  const item = `<opf:item id="${id}" href="${href}" media-type="${mediaType}" isEmbeded="1"/>`
  if (!hpf.includes('</opf:manifest>')) throw new Error('content.hpf 에 manifest 가 없습니다.')
  zip.file(HPF, hpf.replace('</opf:manifest>', `${item}</opf:manifest>`))
}
