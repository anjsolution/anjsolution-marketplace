import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { buildTiff, ascii, rationals, makeJpeg } from './helpers/make-exif.mjs'
import { groupVisits, haversine, reverseGeocode, formatVisit, main } from '../skills/manage/scripts/ttms_construction_project/photo-visits.mjs'

const CLI = fileURLToPath(new URL('../skills/manage/scripts/ttms_construction_project/photo-visits.mjs', import.meta.url))
const run = (args, env = {}) => spawnSync(process.execPath, [CLI, ...args], { encoding: 'utf8', env: { ...process.env, KAKAO_REST_KEY: '', VWORLD_KEY: '', ...env } })
const tmp = () => mkdtempSync(join(tmpdir(), 'photo-visits-'))

// 십진 도 → 도·분·초(초는 1/1000 정밀)
const dmsOf = (deg) => { const d = Math.floor(deg); const m = Math.floor((deg - d) * 60); const s = ((deg - d) * 60 - m) * 60; return [[d, 1], [m, 1], [Math.round(s * 1000), 1000]] }
function photo(dir, name, { date, lat, lon }) {
  const exif = date ? [ascii(0x9003, date)] : null
  const gps = lat != null ? [ascii(1, 'N'), rationals(2, dmsOf(lat)), ascii(3, 'E'), rationals(4, dmsOf(lon))] : null
  const p = join(dir, name)
  writeFileSync(p, makeJpeg({ tiff: buildTiff({ ifd0: [], exif, gps }) }))
  return p
}
const mk = (file, taken_at, lat, lon) => ({ file, taken_at, gps: lat == null ? null : { lat, lon, alt: null } })
const LAT = 37.5, LON = 128.5
const M = 1 / 111195 // 1m 의 위도(도)

test('haversine: 같은 점 0, 위도 0.01도 약 1112m', () => {
  assert.equal(haversine(LAT, LON, LAT, LON), 0)
  assert.ok(Math.abs(haversine(LAT, LON, LAT + 0.01, LON) - 1112) < 3)
})

test('groupVisits: 시간 간격 기준으로 나뉜다 (기본 60분)', () => {
  const r = [mk('a', '2026-09-17 10:00:00', LAT, LON), mk('b', '2026-09-17 10:30:00', LAT, LON), mk('c', '2026-09-17 11:31:00', LAT, LON)]
  const g = groupVisits(r)
  assert.equal(g.visits.length, 2)
  assert.deepEqual(g.visits.map((v) => v.count), [2, 1])
  assert.deepEqual(g.visits.map((v) => v.id), [1, 2])
  assert.equal(g.visits[0].start, '2026-09-17 10:00:00'); assert.equal(g.visits[0].end, '2026-09-17 10:30:00')
})

test('groupVisits: 정확히 gap 이면 같은 방문, 기준을 바꾸면 달라진다', () => {
  const r = [mk('a', '2026-09-17 10:00:00', LAT, LON), mk('b', '2026-09-17 11:00:00', LAT, LON)]
  assert.equal(groupVisits(r).visits.length, 1)
  assert.equal(groupVisits(r, { gapMin: 30 }).visits.length, 2)
})

test('groupVisits: 거리 기준으로 나뉜다 (기본 500m), radiusM 변경', () => {
  const r = [mk('a', '2026-09-17 10:00:00', LAT, LON), mk('b', '2026-09-17 10:05:00', LAT + 300 * M, LON), mk('c', '2026-09-17 10:10:00', LAT + 2000 * M, LON)]
  assert.equal(groupVisits(r).visits.length, 2)
  assert.equal(groupVisits(r, { radiusM: 100 }).visits.length, 3)
  assert.equal(groupVisits(r, { radiusM: 5000 }).visits.length, 1)
})

test('groupVisits: 중심은 평균, 반경은 중심에서 가장 먼 사진까지(정수 m)', () => {
  const r = [mk('a', '2026-09-17 10:00:00', LAT, LON), mk('b', '2026-09-17 10:05:00', LAT + 200 * M, LON)]
  const v = groupVisits(r).visits[0]
  assert.ok(Math.abs(v.center.lat - (LAT + 100 * M)) < 1e-9); assert.ok(Math.abs(v.center.lon - LON) < 1e-9)
  assert.ok(Math.abs(v.radius_m - 100) <= 1); assert.ok(Number.isInteger(v.radius_m))
  assert.deepEqual(v.files, ['a', 'b'])
})

test('groupVisits: 시각 순 정렬, 시간대 표기는 비교에서 무시', () => {
  const r = [mk('late', '2026-09-17 12:30:00 +09:00', LAT, LON), mk('early', '2026-09-17 10:00:00', LAT, LON), mk('mid', '2026-09-17 10:20:00 +09:00', LAT, LON)]
  const g = groupVisits(r)
  assert.deepEqual(g.visits.map((v) => v.files), [['early', 'mid'], ['late']])
})

test('groupVisits: GPS 없음 / 시각 없음 / 둘 다 없음은 따로 보고', () => {
  const r = [mk('ok', '2026-09-17 10:00:00', LAT, LON), mk('ng', '2026-09-17 10:01:00', null), mk('nt', null, LAT, LON), mk('nb', null, null)]
  const g = groupVisits(r)
  assert.equal(g.visits.length, 1)
  assert.deepEqual(g.no_gps, ['ng']); assert.deepEqual(g.no_time, ['nt']); assert.deepEqual(g.no_both, ['nb'])
  assert.deepEqual(g.summary, { photos: 4, visits: 1, no_gps: 1, no_time: 1, no_both: 1 })
})

test('groupVisits: 대상 사진이 없으면 방문 0', () => {
  const g = groupVisits([mk('a', null, null)])
  assert.deepEqual(g.visits, []); assert.equal(g.summary.visits, 0)
})

test('formatVisit: 한 줄 형식과 주소 표기', () => {
  const v = { id: 1, start: '2026-09-17 10:12:05', end: '2026-09-17 11:40:00', count: 14, center: { lat: 37.68301, lon: 128.71899 }, radius_m: 80, files: ['a.jpg', 'b.jpg'] }
  assert.equal(formatVisit(v), '방문 1 | 2026-09-17 10:12 ~ 11:40 | 사진 14장 | 반경 80m | 37.68301,128.71899\n  a.jpg, b.jpg')
  assert.match(formatVisit({ ...v, address: '강원 평창군 어딘가' }), /37\.68301,128\.71899 \| 강원 평창군 어딘가\n/)
  assert.match(formatVisit({ ...v, address: null }), /\| 주소 없음\n/)
  assert.match(formatVisit({ ...v, end: '2026-09-18 09:00:00' }), /2026-09-17 10:12 ~ 2026-09-18 09:00 \|/)
})

// ---------- 주소 변환 ----------
const jsonRes = (body, ok = true, status = 200) => ({ ok, status, json: async () => body })

test('reverseGeocode kakao: URL·헤더, 도로명 우선, 없으면 지번', async () => {
  const calls = []
  const f = async (url, init) => { calls.push({ url, init }); return jsonRes({ documents: [{ road_address: { address_name: '도로명 주소' }, address: { address_name: '지번 주소' } }] }) }
  assert.equal(await reverseGeocode('kakao', 37.5, 128.5, { fetch: f, env: { KAKAO_REST_KEY: 'K1' } }), '도로명 주소')
  assert.equal(calls[0].url, 'https://dapi.kakao.com/v2/local/geo/coord2address.json?x=128.5&y=37.5')
  assert.equal(calls[0].init.headers.Authorization, 'KakaoAK K1')
  const f2 = async () => jsonRes({ documents: [{ road_address: null, address: { address_name: '지번 주소' } }] })
  assert.equal(await reverseGeocode('kakao', 37.5, 128.5, { fetch: f2, env: { KAKAO_REST_KEY: 'K1' } }), '지번 주소')
})

test('reverseGeocode kakao: 결과 없음은 null, HTTP 오류는 던진다', async () => {
  assert.equal(await reverseGeocode('kakao', 1, 2, { fetch: async () => jsonRes({ documents: [] }), env: { KAKAO_REST_KEY: 'K' } }), null)
  await assert.rejects(reverseGeocode('kakao', 1, 2, { fetch: async () => jsonRes({}, false, 401), env: { KAKAO_REST_KEY: 'K' } }), /401/)
})

test('reverseGeocode vworld: URL, status OK 일 때 result[0].text', async () => {
  const calls = []
  const f = async (url) => { calls.push(url); return jsonRes({ response: { status: 'OK', result: [{ text: '브이월드 주소' }] } }) }
  assert.equal(await reverseGeocode('vworld', 37.5, 128.5, { fetch: f, env: { VWORLD_KEY: 'V1' } }), '브이월드 주소')
  assert.equal(calls[0], 'https://api.vworld.kr/req/address?service=address&request=getAddress&version=2.0&crs=epsg:4326&point=128.5,37.5&format=json&type=both&key=V1')
  await reverseGeocode('vworld', 1, 2, { fetch: async (u) => { calls.push(u); return jsonRes({ response: { status: 'NOT_FOUND' } }) }, env: { VWORLD_KEY: 'a b&c' } })
  assert.match(calls[1], /key=a%20b%26c$/)
  assert.equal(await reverseGeocode('vworld', 1, 2, { fetch: async () => jsonRes({ response: { status: 'NOT_FOUND' } }), env: { VWORLD_KEY: 'V' } }), null)
})

test('reverseGeocode: 키 없음·알 수 없는 공급자는 던진다', async () => {
  await assert.rejects(reverseGeocode('kakao', 1, 2, { fetch: async () => { throw new Error('호출되면 안 됨') }, env: {} }), /KAKAO_REST_KEY/)
  await assert.rejects(reverseGeocode('nope', 1, 2, { fetch: async () => {}, env: {} }), /nope/)
})

// ---------- main (fetch·env·출력 주입) ----------
const capture = () => { const out = [], err = []; return { out, err, log: (s) => out.push(s), error: (s) => err.push(s) } }

test('main --geocode kakao: 방문 중심마다 한 번만 호출, 주소 채움', async () => {
  const d = tmp()
  photo(d, 'a.jpg', { date: '2026:09:17 10:00:00', lat: LAT, lon: LON })
  photo(d, 'b.jpg', { date: '2026:09:17 10:05:00', lat: LAT, lon: LON })
  photo(d, 'c.jpg', { date: '2026:09:17 15:00:00', lat: LAT + 0.1, lon: LON })
  let n = 0
  const c = capture()
  const code = await main([d, '--geocode', 'kakao', '--json'], { fetch: async () => { n++; return jsonRes({ documents: [{ address: { address_name: `주소${n}` } }] }) }, env: { KAKAO_REST_KEY: 'K' }, io: c })
  assert.equal(code, 0); assert.equal(n, 2)
  const j = JSON.parse(c.out.join('\n'))
  assert.deepEqual(j.visits.map((v) => v.address), ['주소1', '주소2'])
})

test('main --geocode: 방문 하나가 실패하면 address null + 경고, 나머지는 계속', async () => {
  const d = tmp()
  photo(d, 'a.jpg', { date: '2026:09:17 10:00:00', lat: LAT, lon: LON })
  photo(d, 'c.jpg', { date: '2026:09:17 15:00:00', lat: LAT + 0.1, lon: LON })
  let n = 0
  const c = capture()
  const code = await main([d, '--geocode', 'vworld', '--json'], {
    fetch: async () => { n++; if (n === 1) throw new Error('네트워크 끊김'); return jsonRes({ response: { status: 'OK', result: [{ text: 'OK 주소' }] } }) },
    env: { VWORLD_KEY: 'V' }, io: c })
  assert.equal(code, 0)
  const j = JSON.parse(c.out.join('\n'))
  assert.deepEqual(j.visits.map((v) => v.address), [null, 'OK 주소'])
  assert.match(c.err.join('\n'), /방문 1.*네트워크 끊김/)
})

test('main --geocode: 키가 없으면 요청 없이 종료 코드 1', async () => {
  const d = tmp(); photo(d, 'a.jpg', { date: '2026:09:17 10:00:00', lat: LAT, lon: LON })
  let n = 0; const c = capture()
  const code = await main([d, '--geocode', 'kakao'], { fetch: async () => { n++; return jsonRes({}) }, env: {}, io: c })
  assert.equal(code, 1); assert.equal(n, 0)
  assert.match(c.err.join('\n'), /KAKAO_REST_KEY/)
})

test('main: geocode 를 안 주면 fetch 를 부르지 않는다', async () => {
  const d = tmp(); photo(d, 'a.jpg', { date: '2026:09:17 10:00:00', lat: LAT, lon: LON })
  const c = capture()
  const code = await main([d], { fetch: async () => { throw new Error('호출되면 안 됨') }, env: {}, io: c })
  assert.equal(code, 0)
})

// ---------- CLI ----------
test('CLI: 사람용 출력 — 방문 줄, 제외 요약, 방문 N곳', () => {
  const d = tmp()
  photo(d, 'a.jpg', { date: '2026:09:17 10:00:00', lat: LAT, lon: LON })
  photo(d, 'b.jpg', { date: '2026:09:17 10:10:00', lat: LAT, lon: LON })
  photo(d, 'n.jpg', { date: '2026:09:17 10:11:00' })
  photo(d, 't.jpg', { lat: LAT, lon: LON })
  writeFileSync(join(d, 'x.jpg'), makeJpeg())
  const r = run([d])
  assert.equal(r.status, 0)
  assert.match(r.stdout, /^방문 1 \| 2026-09-17 10:00 ~ 10:10 \| 사진 2장 \| 반경 0m \| 37\.5,128\.5\r?\n {2}a\.jpg, b\.jpg/m)
  assert.match(r.stdout, /GPS 없음 1장, 시각 없음 1장, 둘 다 없음 1장/)
  assert.match(r.stdout, /방문 1곳/)
})

test('CLI: --json 형태, --gap-min / --radius-m 옵션', () => {
  const d = tmp()
  photo(d, 'a.jpg', { date: '2026:09:17 10:00:00', lat: LAT, lon: LON })
  photo(d, 'b.jpg', { date: '2026:09:17 10:40:00', lat: LAT, lon: LON })
  const j = JSON.parse(run([d, '--json']).stdout)
  assert.deepEqual(Object.keys(j), ['visits', 'no_gps', 'no_time', 'no_both', 'summary'])
  assert.equal(j.summary.visits, 1)
  assert.equal(JSON.parse(run([d, '--json', '--gap-min', '30']).stdout).summary.visits, 2)
  assert.equal(JSON.parse(run([d, '--json', '--radius-m', '1']).stdout).summary.visits, 1)
})

test('CLI: -r 하위 폴더 탐색, 방문 0곳 안내', () => {
  const d = tmp(); const sub = join(d, 'sub'); mkdirSync(sub)
  photo(sub, 'a.jpg', { date: '2026:09:17 10:00:00', lat: LAT, lon: LON })
  assert.equal(JSON.parse(run([d, '--json']).stdout).summary.photos, 0)
  assert.equal(JSON.parse(run([d, '-r', '--json']).stdout).summary.visits, 1)
  const e = tmp(); writeFileSync(join(e, 'x.jpg'), makeJpeg())
  const r = run([e])
  assert.equal(r.status, 0); assert.match(r.stdout, /방문 0곳/)
})

test('CLI: --list 입력', () => {
  const d = tmp(); const p = photo(d, 'a.jpg', { date: '2026:09:17 10:00:00', lat: LAT, lon: LON })
  const l = join(tmp(), 'l.txt'); writeFileSync(l, `${p}\n`)
  assert.equal(JSON.parse(run(['--list', l, '--json']).stdout).summary.visits, 1)
})

test('CLI: 종료 코드 — 사용법 오류 2, 경로 없음 1, geocode 키 없음 1', () => {
  assert.equal(run([]).status, 2)
  assert.equal(run(['--bogus']).status, 2)
  assert.equal(run(['--list']).status, 2)
  assert.equal(run(['--list', '-r']).status, 2)
  const d = tmp(); photo(d, 'a.jpg', { date: '2026:09:17 10:00:00', lat: LAT, lon: LON })
  assert.equal(run([d, '--gap-min']).status, 2)
  assert.equal(run([d, '--gap-min', 'abc']).status, 2)
  assert.equal(run([d, '--radius-m', '-5']).status, 2)
  assert.equal(run([d, '--geocode']).status, 2)
  assert.equal(run([d, '--geocode', '-r']).status, 2)
  assert.equal(run([d, '--gap-min', '-r']).status, 2)
  assert.equal(run([d, '--geocode', 'google']).status, 2)
  assert.equal(run([join(tmpdir(), 'no-such-dir-xyz')]).status, 1)
  const r = run([d, '--geocode', 'kakao'])
  assert.equal(r.status, 1); assert.match(r.stderr, /KAKAO_REST_KEY/)
  assert.equal(run([d, '--geocode', 'vworld']).status, 1)
})

test('groupVisits: 거리는 첫 사진이 아니라 누적 중심 기준으로 본다', () => {
  // 0m, 400m, 800m: 첫 사진 기준이면 800m 에서 갈라지지만 중심(200m) 기준 600m 라 radius 500 에서 갈라진다.
  // 반대로 radius 700 이면 중심 기준(600m)으로 같은 방문이어야 한다(첫 사진 기준 800m 면 갈라짐).
  const r = [mk('a', '2026-09-17 10:00:00', LAT, LON), mk('b', '2026-09-17 10:05:00', LAT + 400 * M, LON), mk('c', '2026-09-17 10:10:00', LAT + 800 * M, LON)]
  assert.equal(groupVisits(r, { radiusM: 700 }).visits.length, 1)
  assert.equal(groupVisits(r, { radiusM: 500 }).visits.length, 2)
})

test('groupVisits: 음수 시간대 표기(-05:00)가 붙은 시각도 정렬·간격 계산이 된다', () => {
  const r = [mk('b', '2026-09-17 10:30:00 -05:00', LAT, LON), mk('a', '2026-09-17 10:00:00 -05:00', LAT, LON)]
  const g = groupVisits(r)
  assert.deepEqual(g.visits[0].files, ['a', 'b'])
  assert.equal(g.visits[0].end, '2026-09-17 10:30:00')
})
