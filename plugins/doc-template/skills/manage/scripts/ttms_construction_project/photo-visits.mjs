#!/usr/bin/env node
// 현장 사진의 GPS·촬영 시각으로 방문 목록을 만든다. 읽기 전용, Node 내장 모듈만 사용.
// 임시 위치 — TTMS 구축 전용 플러그인으로 옮길 때 ../analyze-image.mjs 와 함께 옮긴다.
import { basename, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { analyzeFile, collectPaths } from '../analyze-image.mjs'

const GEOCODERS = {
  kakao: { envKey: 'KAKAO_REST_KEY' },
  vworld: { envKey: 'VWORLD_KEY' },
}

// ---------- 계산 ----------
export function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371008.8, rad = Math.PI / 180
  const dLat = (lat2 - lat1) * rad, dLon = (lon2 - lon1) * rad
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)))
}

// 'YYYY-MM-DD HH:MM:SS[ +HH:MM]' → 시간대 표기를 버린 시각(ms). 비교에만 쓴다.
const ms = (t) => Date.parse(`${t.slice(0, 10)}T${t.slice(11, 19)}Z`)
const centerOf = (ps) => ({ lat: ps.reduce((s, p) => s + p.gps.lat, 0) / ps.length, lon: ps.reduce((s, p) => s + p.gps.lon, 0) / ps.length })

export function groupVisits(results, { gapMin = 60, radiusM = 500 } = {}) {
  const no_gps = [], no_time = [], no_both = [], usable = []
  for (const p of results) {
    if (p.gps && p.taken_at) usable.push(p)
    else if (p.taken_at) no_gps.push(p.file)
    else if (p.gps) no_time.push(p.file)
    else no_both.push(p.file)
  }
  usable.sort((a, b) => ms(a.taken_at) - ms(b.taken_at))
  const groups = []
  let cur = null
  for (const p of usable) {
    if (cur) {
      const last = cur[cur.length - 1]
      const c = centerOf(cur)
      if (ms(p.taken_at) - ms(last.taken_at) > gapMin * 60000 || haversine(c.lat, c.lon, p.gps.lat, p.gps.lon) > radiusM) cur = null
    }
    if (!cur) { cur = []; groups.push(cur) }
    cur.push(p)
  }
  const visits = groups.map((ps, i) => {
    const center = centerOf(ps)
    return {
      id: i + 1,
      start: ps[0].taken_at.slice(0, 19),
      end: ps[ps.length - 1].taken_at.slice(0, 19),
      count: ps.length,
      center,
      radius_m: Math.round(Math.max(...ps.map((p) => haversine(center.lat, center.lon, p.gps.lat, p.gps.lon)))),
      files: ps.map((p) => p.file),
    }
  })
  return { visits, no_gps, no_time, no_both, summary: { photos: results.length, visits: visits.length, no_gps: no_gps.length, no_time: no_time.length, no_both: no_both.length } }
}

// ---------- 주소 변환 ----------
export async function reverseGeocode(provider, lat, lon, { fetch: f = globalThis.fetch, env = process.env } = {}) {
  const g = GEOCODERS[provider]
  if (!g) throw new Error(`알 수 없는 주소 변환 공급자: ${provider}`)
  const key = env[g.envKey]
  if (!key) throw new Error(`환경변수 ${g.envKey} 가 없습니다`)
  if (provider === 'kakao') {
    const res = await f(`https://dapi.kakao.com/v2/local/geo/coord2address.json?x=${lon}&y=${lat}`, { headers: { Authorization: `KakaoAK ${key}` } })
    if (!res.ok) throw new Error(`카카오 응답 오류 HTTP ${res.status}`)
    const d = (await res.json()).documents?.[0]
    return d?.road_address?.address_name || d?.address?.address_name || null
  }
  const url = `https://api.vworld.kr/req/address?service=address&request=getAddress&version=2.0&crs=epsg:4326&point=${lon},${lat}&format=json&type=both&key=${encodeURIComponent(key)}`
  const res = await f(url)
  if (!res.ok) throw new Error(`VWorld 응답 오류 HTTP ${res.status}`)
  const body = (await res.json()).response
  return body?.status === 'OK' ? body.result?.[0]?.text || null : null
}

// ---------- 출력 ----------
const hm = (t) => t.slice(0, 16)

export function formatVisit(v) {
  const end = v.end.slice(0, 10) === v.start.slice(0, 10) ? hm(v.end).slice(11) : hm(v.end)
  const parts = [`방문 ${v.id}`, `${hm(v.start)} ~ ${end}`, `사진 ${v.count}장`, `반경 ${v.radius_m}m`,
    `${Number(v.center.lat.toFixed(5))},${Number(v.center.lon.toFixed(5))}`]
  if (v.address !== undefined) parts.push(v.address === null ? '주소 없음' : v.address)
  return `${parts.join(' | ')}\n  ${v.files.map((f) => basename(f)).join(', ')}`
}

// ---------- CLI ----------
const USAGE = '사용법: node photo-visits.mjs <경로> [<경로> ...] [--list <목록.txt>] [--recursive|-r] [--gap-min 60] [--radius-m 500] [--geocode kakao|vworld] [--json]'

export async function main(argv, { fetch: f = globalThis.fetch, env = process.env, io = console } = {}) {
  const paths = []
  let list = null, json = false, recursive = false, gapMin = 60, radiusM = 500, geocode = null
  const num = (s, name) => {
    const n = Number(s)
    if (s.trim() === '' || !Number.isFinite(n) || n < 0) { io.error(`${name} 는 0 이상의 숫자여야 합니다.\n${USAGE}`); return null }
    return n
  }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--json') json = true
    else if (a === '--recursive' || a === '-r') recursive = true
    else if (a === '--list' || a === '--gap-min' || a === '--radius-m' || a === '--geocode') {
      if (i + 1 >= argv.length || argv[i + 1].startsWith('-')) { io.error(`${a} 뒤에 값이 필요합니다.\n${USAGE}`); return 2 }
      const v = argv[++i]
      if (a === '--list') list = v
      else if (a === '--geocode') {
        if (!GEOCODERS[v]) { io.error(`--geocode 는 kakao 또는 vworld 만 가능합니다: ${v}\n${USAGE}`); return 2 }
        geocode = v
      } else {
        const n = num(v, a)
        if (n === null) return 2
        if (a === '--gap-min') gapMin = n; else radiusM = n
      }
    } else if (a.startsWith('--')) { io.error(`알 수 없는 옵션: ${a}\n${USAGE}`); return 2 }
    else paths.push(a)
  }
  if (!paths.length && !list) { io.error(USAGE); return 2 }
  if (geocode && !env[GEOCODERS[geocode].envKey]) {
    io.error(`주소 변환에 필요한 환경변수 ${GEOCODERS[geocode].envKey} 가 없습니다. 키를 설정한 뒤 다시 실행하세요(키는 git·문서에 적지 않습니다).`)
    return 1
  }
  let collected
  try { collected = collectPaths(paths, list, { recursive }) } catch (e) { io.error(`입력을 읽지 못했습니다: ${e.message}`); return 1 }
  for (const m of collected.missing) io.error(`경로를 찾을 수 없습니다: ${m}`)
  if (!collected.files.length && collected.missing.length) return 1
  const results = await Promise.all(collected.files.map((p) => analyzeFile(p)))
  const out = groupVisits(results, { gapMin, radiusM })
  if (geocode) {
    for (const v of out.visits) {
      try { v.address = await reverseGeocode(geocode, v.center.lat, v.center.lon, { fetch: f, env }) }
      catch (e) { v.address = null; io.error(`경고: 방문 ${v.id} 주소 변환 실패 — ${e.message}`) }
    }
  }
  if (json) io.log(JSON.stringify(out, null, 2))
  else {
    for (const v of out.visits) io.log(formatVisit(v))
    io.log('')
    const s = out.summary
    io.log(`GPS 없음 ${s.no_gps}장, 시각 없음 ${s.no_time}장, 둘 다 없음 ${s.no_both}장`)
    io.log(`방문 ${s.visits}곳`)
  }
  return 0
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).then((c) => { process.exitCode = c }).catch((e) => { console.error(`예상하지 못한 오류: ${e.message}`); process.exitCode = 1 })
}
