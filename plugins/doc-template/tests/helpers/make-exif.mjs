// 합성 JPEG(EXIF 포함) 생성 도우미 — 테스트 전용
// 엔트리: { tag, type(1=BYTE,2=ASCII,3=SHORT,4=LONG,5=RATIONAL), value }
function enc(le) {
  return {
    u16: (n) => { const b = Buffer.alloc(2); if (le) b.writeUInt16LE(n); else b.writeUInt16BE(n); return b },
    u32: (n) => { const b = Buffer.alloc(4); if (le) b.writeUInt32LE(n); else b.writeUInt32BE(n); return b },
  }
}

function countOf(en) {
  if (en.type === 2) return Buffer.byteLength(en.value) + 1
  if (!Array.isArray(en.value)) return 1
  return en.type === 5 ? en.value.length / 2 : en.value.length
}
function dataBytes(en, e) {
  const v = en.value
  if (en.type === 2) return Buffer.concat([Buffer.from(v, 'latin1'), Buffer.alloc(1)])
  const arr = Array.isArray(v) ? v : [v]
  if (en.type === 1) return Buffer.from(arr)
  if (en.type === 3) return Buffer.concat(arr.map(e.u16))
  return Buffer.concat(arr.map(e.u32)) // LONG, RATIONAL(분자,분모 평탄 배열)
}
const padded = (b) => (b.length % 2 ? Buffer.concat([b, Buffer.alloc(1)]) : b)

// ifds: { ifd0: [...], exif: [...]|null, gps: [...]|null } → TIFF 바이트
export function buildTiff(ifds, { le = true } = {}) {
  const e = enc(le)
  const ifd0 = [...(ifds.ifd0 || [])]
  const exif = ifds.exif || null
  const gps = ifds.gps || null
  if (exif) ifd0.push({ tag: 0x8769, type: 4, value: 'EXIFPTR' })
  if (gps) ifd0.push({ tag: 0x8825, type: 4, value: 'GPSPTR' })
  const lists = [['ifd0', ifd0]]
  if (exif) lists.push(['exif', exif])
  if (gps) lists.push(['gps', gps])

  const sizeOf = (list) => 2 + list.length * 12 + 4 + list.reduce((s, en) => {
    const n = en.value === 'EXIFPTR' || en.value === 'GPSPTR' ? 4 : dataBytes(en, e).length
    return s + (n > 4 ? padded(Buffer.alloc(n)).length : 0)
  }, 0)
  const offsets = {}
  let off = 8
  for (const [name, list] of lists) { offsets[name] = off; off += sizeOf(list) }

  const parts = [Buffer.concat([Buffer.from(le ? 'II' : 'MM'), e.u16(42), e.u32(8)])]
  for (const [name, list] of lists) {
    let valuePos = offsets[name] + 2 + list.length * 12 + 4
    const entries = []
    const extras = []
    for (const en of [...list].sort((a, b) => a.tag - b.tag)) {
      let value = en.value
      if (value === 'EXIFPTR') value = [offsets.exif]
      if (value === 'GPSPTR') value = [offsets.gps]
      const full = { ...en, value }
      const d = dataBytes(full, e)
      const head = Buffer.concat([e.u16(en.tag), e.u16(en.type), e.u32(countOf(full))])
      if (d.length <= 4) {
        entries.push(Buffer.concat([head, d, Buffer.alloc(4 - d.length)]))
      } else {
        entries.push(Buffer.concat([head, e.u32(valuePos)]))
        const p = padded(d)
        extras.push(p)
        valuePos += p.length
      }
    }
    parts.push(e.u16(list.length), ...entries, e.u32(0), ...extras)
  }
  return Buffer.concat(parts)
}

export const ascii = (tag, value) => ({ tag, type: 2, value })
export const short = (tag, value) => ({ tag, type: 3, value: [value] })
export const rationals = (tag, pairs) => ({ tag, type: 5, value: pairs.flat() })

// SOI + (APP1 Exif) + SOF0(크기) + EOI 형태의 최소 JPEG
export function makeJpeg({ width = 1440, height = 1080, tiff = null, rawApp1 = null, extraBytes = 0 } = {}) {
  const segs = [Buffer.from([0xff, 0xd8])]
  const app1 = rawApp1 || (tiff ? Buffer.concat([Buffer.from('Exif\0\0', 'latin1'), tiff]) : null)
  if (app1) {
    const len = Buffer.alloc(2); len.writeUInt16BE(app1.length + 2)
    segs.push(Buffer.from([0xff, 0xe1]), len, app1)
  }
  const sof = Buffer.alloc(17)
  sof.writeUInt16BE(17, 0); sof[2] = 8; sof.writeUInt16BE(height, 3); sof.writeUInt16BE(width, 5); sof[7] = 3
  segs.push(Buffer.from([0xff, 0xc0]), sof, Buffer.alloc(extraBytes), Buffer.from([0xff, 0xd9]))
  return Buffer.concat(segs)
}

export function makePngHeader(w, h) {
  const b = Buffer.alloc(33)
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).copy(b)
  b.writeUInt32BE(13, 8); b.write('IHDR', 12); b.writeUInt32BE(w, 16); b.writeUInt32BE(h, 20)
  return b
}
