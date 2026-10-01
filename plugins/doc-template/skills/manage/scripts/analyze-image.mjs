#!/usr/bin/env node
// 사진 메타데이터 분석 — 촬영 일시·위치·크기·용량을 한 번에 뽑는다. 읽기 전용, Node 내장 모듈만 사용.
import { promises as fsp, readdirSync, readFileSync, statSync } from 'node:fs'
import { basename, dirname, extname, isAbsolute, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HEAD_BYTES = 256 * 1024
const EXTS = new Set(['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.heif'])
const HEIC_MSG = 'HEIC 는 아직 분석하지 않습니다'

// ---------- EXIF (TIFF) ----------
const TYPE_SIZE = { 1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8 }

function tiffReader(buf, base) {
  // buf[base..] 가 TIFF 헤더. 범위를 벗어나면 null.
  const end = buf.length
  const b0 = buf[base], b1 = buf[base + 1]
  const le = b0 === 0x49 && b1 === 0x49
  if (!le && !(b0 === 0x4d && b1 === 0x4d)) return null
  const u16 = (o) => (o >= 0 && base + o + 2 <= end ? (le ? buf.readUInt16LE(base + o) : buf.readUInt16BE(base + o)) : null)
  const u32 = (o) => (o >= 0 && base + o + 4 <= end ? (le ? buf.readUInt32LE(base + o) : buf.readUInt32BE(base + o)) : null)
  if (u16(2) !== 42) return null
  return { u16, u32, base, end, buf }
}

function readIfd(r, offset) {
  // → { tag: { type, count, pos } } (pos = 값의 TIFF 상대 위치). 깨졌으면 빈 객체.
  const out = {}
  const n = offset == null ? null : r.u16(offset)
  if (n == null || n > 1000) return out
  for (let i = 0; i < n; i++) {
    const e = offset + 2 + i * 12
    const tag = r.u16(e), type = r.u16(e + 2), count = r.u32(e + 4)
    if (tag == null || type == null || count == null) break
    const size = (TYPE_SIZE[type] || 0) * count
    let pos = e + 8
    if (size > 4) {
      pos = r.u32(e + 8)
      if (pos == null) continue
    }
    if (!size || r.base + pos + size > r.end) continue
    out[tag] = { type, count, pos }
  }
  return out
}

function asciiOf(r, en) {
  if (!en || en.type !== 2) return null
  let s = ''
  for (let i = 0; i < en.count; i++) {
    const c = r.buf[r.base + en.pos + i]
    if (c === 0) break
    s += String.fromCharCode(c)
  }
  s = s.trim()
  return s || null
}
function shortOf(r, en) { return en && en.type === 3 && en.count >= 1 ? r.u16(en.pos) : null }
function rationalAt(r, en, i) {
  if (!en || en.type !== 5 || i >= en.count) return null
  const num = r.u32(en.pos + i * 8), den = r.u32(en.pos + i * 8 + 4)
  if (num == null || den == null || den === 0) return null
  return num / den
}

function exifDate(s) {
  const m = /^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})/.exec(s || '')
  if (!m || +m[1] === 0 || +m[2] < 1 || +m[2] > 12 || +m[3] < 1 || +m[3] > 31) return null
  return `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}:${m[6]}`
}

function readGps(r, gps) {
  const latRef = asciiOf(r, gps[1]), lonRef = asciiOf(r, gps[3])
  const dms = (en) => {
    if (!en || en.type !== 5 || en.count < 3) return null
    const [d, m, s] = [0, 1, 2].map((i) => rationalAt(r, en, i))
    return d == null || m == null || s == null ? null : d + m / 60 + s / 3600
  }
  let lat = dms(gps[2]), lon = dms(gps[4])
  if (lat == null || lon == null || !latRef || !lonRef) return null
  const la = latRef[0].toUpperCase(), lo = lonRef[0].toUpperCase()
  if ((la !== 'N' && la !== 'S') || (lo !== 'E' && lo !== 'W')) return null
  if (la === 'S') lat = -lat
  if (lo === 'W') lon = -lon
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null
  let alt = rationalAt(r, gps[6], 0)
  if (alt != null && gps[5] && gps[5].type === 1 && r.buf[r.base + gps[5].pos] === 1) alt = -alt
  return { lat, lon, alt }
}

function parseTiff(buf, base) {
  const res = { orientation: null, taken_at: null, gps: null, device: null }
  try {
    const r = tiffReader(buf, base)
    if (!r) return res
    const ifd0 = readIfd(r, r.u32(4))
    const make = asciiOf(r, ifd0[0x010f]), model = asciiOf(r, ifd0[0x0110])
    res.device = [make, model].filter(Boolean).join(' ') || null
    const o = shortOf(r, ifd0[0x0112])
    res.orientation = o >= 1 && o <= 8 ? o : null
    if (ifd0[0x8769]?.type === 4) {
      const exif = readIfd(r, r.u32(ifd0[0x8769].pos))
      const orig = exifDate(asciiOf(r, exif[0x9003]))
      const t = orig || exifDate(asciiOf(r, exif[0x9004]))
      if (t) {
        const off = asciiOf(r, exif[orig ? 0x9011 : 0x9012])
        res.taken_at = off && /^[+-]\d{2}:\d{2}$/.test(off) ? `${t} ${off}` : t
      }
    }
    if (ifd0[0x8825]?.type === 4) res.gps = readGps(r, readIfd(r, r.u32(ifd0[0x8825].pos)))
  } catch { /* 깨진 EXIF 는 null */ }
  return res
}

// ---------- 형식별 헤더 ----------
const SOF = new Set([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf])

function parseJpeg(buf) {
  const res = { width: null, height: null, orientation: null, taken_at: null, gps: null, device: null }
  let p = 2
  let exifDone = false
  while (p + 4 <= buf.length) {
    if (buf[p] !== 0xff) { p++; continue }
    const m = buf[p + 1]
    if (m === 0xff) { p++; continue }
    if (m === 0xd8 || m === 0x01 || (m >= 0xd0 && m <= 0xd7)) { p += 2; continue }
    if (m === 0xd9 || m === 0xda) break
    const len = buf.readUInt16BE(p + 2)
    if (len < 2) break
    const data = p + 4
    if (m === 0xe1 && !exifDone && buf.toString('latin1', data, data + 6) === 'Exif\0\0') {
      exifDone = true
      Object.assign(res, parseTiff(buf.subarray(0, Math.min(buf.length, p + 2 + len)), data + 6))
    } else if (SOF.has(m) && data + 5 <= buf.length) {
      res.height = buf.readUInt16BE(data + 1)
      res.width = buf.readUInt16BE(data + 3)
      break
    }
    p += 2 + len
  }
  return res
}

function parsePng(b) {
  return b.length >= 24 ? { width: b.readUInt32BE(16), height: b.readUInt32BE(20) } : null
}
function parseGif(b) {
  return b.length >= 10 ? { width: b.readUInt16LE(6), height: b.readUInt16LE(8) } : null
}
function parseBmp(b) {
  if (b.length < 26) return null
  if (b.readUInt32LE(14) === 12) return { width: b.readUInt16LE(18), height: b.readUInt16LE(20) }
  if (b.length < 26) return null
  return { width: b.readInt32LE(18), height: Math.abs(b.readInt32LE(22)) }
}

function sniff(b) {
  if (b.length >= 3 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return 'jpg'
  if (b.length >= 8 && b.toString('latin1', 1, 4) === 'PNG') return 'png'
  if (b.toString('latin1', 0, 4) === 'GIF8') return 'gif'
  if (b.toString('latin1', 0, 2) === 'BM') return 'bmp'
  return null
}

// ---------- 공개 함수 ----------
export async function analyzeFile(file) {
  const abs = resolve(file)
  const ext = extname(abs).toLowerCase()
  const r = { file: abs, bytes: null, width: null, height: null, orientation: null, taken_at: null, gps: null, device: null, format: ext.slice(1).replace('jpeg', 'jpg') }
  try {
    r.bytes = (await fsp.stat(abs)).size
    if (ext === '.heic' || ext === '.heif') { r.format = 'heic'; r.error = HEIC_MSG; return r }
    const fh = await fsp.open(abs, 'r')
    let buf
    try {
      const tmp = Buffer.alloc(Math.min(HEAD_BYTES, Math.max(r.bytes, 0)))
      const { bytesRead } = await fh.read(tmp, 0, tmp.length, 0)
      buf = tmp.subarray(0, bytesRead)
    } finally { await fh.close() }
    const fmt = sniff(buf)
    if (!fmt) { r.error = '사진 형식을 알 수 없습니다'; return r }
    r.format = fmt
    if (fmt === 'jpg') {
      Object.assign(r, parseJpeg(buf))
      if (r.width == null) r.error = 'JPEG 크기를 찾지 못했습니다'
    } else {
      const d = fmt === 'png' ? parsePng(buf) : fmt === 'gif' ? parseGif(buf) : parseBmp(buf)
      if (d) Object.assign(r, d)
      else r.error = '헤더를 읽지 못했습니다'
    }
  } catch (e) {
    r.error = `읽기 실패: ${e.message}`
  }
  return r
}

const isPhoto = (p) => EXTS.has(extname(p).toLowerCase())

export function collectPaths(paths, listFile) {
  const files = [], missing = []
  const seen = new Set()
  const add = (f) => { const a = resolve(f); if (!seen.has(a)) { seen.add(a); files.push(a) } }
  const take = (p) => {
    let st
    try { st = statSync(p) } catch { missing.push(p); return }
    if (st.isDirectory()) {
      const names = readdirSync(p, { withFileTypes: true }).filter((e) => e.isFile() && isPhoto(e.name)).map((e) => e.name)
      names.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()) || (a < b ? -1 : 1))
      for (const n of names) add(join(p, n))
    } else if (isPhoto(p)) add(p)
  }
  for (const p of paths || []) take(p)
  if (listFile) {
    const base = dirname(resolve(listFile))
    const lines = readFileSync(listFile, 'utf8').replace(/^﻿/, '').split(/\r?\n/)
    for (const raw of lines) {
      const line = raw.trim()
      if (!line || line.startsWith('#')) continue
      take(isAbsolute(line) ? line : resolve(base, line))
    }
  }
  return { files, missing }
}

const key = (t) => t.slice(0, 19)

export function summarize(results) {
  const dated = results.filter((p) => p.taken_at).sort((a, b) => (key(a.taken_at) < key(b.taken_at) ? -1 : key(a.taken_at) > key(b.taken_at) ? 1 : 0))
  const photos = [...dated, ...results.filter((p) => !p.taken_at)]
  return {
    photos,
    summary: {
      total: results.length,
      withDate: dated.length,
      withGps: results.filter((p) => p.gps).length,
      from: dated.length ? dated[0].taken_at : null,
      to: dated.length ? dated[dated.length - 1].taken_at : null,
      failed: results.filter((p) => p.error).length,
    },
  }
}

function sizeText(bytes) {
  if (bytes == null) return '없음'
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)}MB` : `${Math.round(bytes / 1024)}KB`
}

export function formatLine(p) {
  const dim = p.width != null && p.height != null ? `${p.width}×${p.height}` : '크기 없음'
  const gps = p.gps ? `${Number(p.gps.lat.toFixed(5))},${Number(p.gps.lon.toFixed(5))}` : '없음'
  const parts = [basename(p.file), dim, sizeText(p.bytes), `촬영 ${p.taken_at || '없음'}`, `위치 ${gps}`, `기기 ${p.device || '없음'}`]
  if (p.error) parts.push(`오류 ${p.error}`)
  return parts.join(' | ')
}

export function formatSummary(s) {
  const period = s.from ? `${s.from} ~ ${s.to}` : '없음'
  return `총 ${s.total}장, 촬영 날짜 있음 ${s.withDate}장, 위치 있음 ${s.withGps}장, 촬영 기간 ${period}, 읽기 실패 ${s.failed}장`
}

// ---------- CLI ----------
const USAGE = '사용법: node analyze-image.mjs <경로> [<경로> ...] [--list <목록.txt>] [--json]'

export async function main(argv) {
  const paths = []
  let list = null, json = false
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--json') json = true
    else if (a === '--list') {
      if (i + 1 >= argv.length || argv[i + 1].startsWith('--')) { console.error(`--list 뒤에 목록 파일 경로가 필요합니다.\n${USAGE}`); return 2 }
      list = argv[++i]
    } else if (a.startsWith('--')) { console.error(`알 수 없는 옵션: ${a}\n${USAGE}`); return 2 }
    else paths.push(a)
  }
  if (!paths.length && !list) { console.error(USAGE); return 2 }
  let collected
  try { collected = collectPaths(paths, list) } catch (e) { console.error(`입력을 읽지 못했습니다: ${e.message}`); return 1 }
  for (const m of collected.missing) console.error(`경로를 찾을 수 없습니다: ${m}`)
  if (!collected.files.length && collected.missing.length) return 1
  const results = await Promise.all(collected.files.map((f) => analyzeFile(f)))
  const { photos, summary } = summarize(results)
  if (json) console.log(JSON.stringify({ photos, summary }, null, 2))
  else {
    for (const p of photos) console.log(formatLine(p))
    console.log('')
    console.log(formatSummary(summary))
  }
  return 0
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).then((c) => { process.exitCode = c })
}
