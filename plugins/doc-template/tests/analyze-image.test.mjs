import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, writeFileSync, utimesSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { buildTiff, ascii, short, rationals, makeJpeg, makePngHeader } from './helpers/make-exif.mjs'
import { analyzeFile, collectPaths, summarize, formatLine } from '../skills/manage/scripts/analyze-image.mjs'

const CLI = fileURLToPath(new URL('../skills/manage/scripts/analyze-image.mjs', import.meta.url))
const run = (...args) => spawnSync(process.execPath, [CLI, ...args], { encoding: 'utf8' })
const tmp = () => mkdtempSync(join(tmpdir(), 'analyze-img-'))
const write = (dir, name, buf) => { const p = join(dir, name); writeFileSync(p, buf); return p }
const dms = (d, m, s) => [[d, 1], [m, 1], [Math.round(s * 100), 100]]

function exifJpeg({ le = true, orientation, date, digitized, offset, offsetDigitized, make, model, gps, ptrType } = {}) {
  const ifd0 = []
  if (make) ifd0.push(ascii(0x010f, make))
  if (model) ifd0.push(ascii(0x0110, model))
  if (orientation) ifd0.push(short(0x0112, orientation))
  const exif = []
  if (date) exif.push(ascii(0x9003, date))
  if (digitized) exif.push(ascii(0x9004, digitized))
  if (offset) exif.push(ascii(0x9011, offset))
  if (offsetDigitized) exif.push(ascii(0x9012, offsetDigitized))
  const g = gps ? [
    ascii(0x0001, gps.latRef), rationals(0x0002, dms(...gps.lat)),
    ascii(0x0003, gps.lonRef), rationals(0x0004, dms(...gps.lon)),
    ...(gps.alt != null ? [{ tag: 0x0005, type: 1, value: [gps.altRef || 0] }, rationals(0x0006, [[gps.alt * 10, 10]])] : []),
  ] : null
  return makeJpeg({ tiff: buildTiff({ ifd0, exif: exif.length ? exif : null, gps: g }, { le, ptrType }) })
}

test('JPEG 크기와 파일 크기', async () => {
  const d = tmp()
  const buf = makeJpeg({ width: 1440, height: 1080, extraBytes: 500 })
  const p = write(d, 'a.jpg', buf)
  const r = await analyzeFile(p)
  assert.equal(r.width, 1440); assert.equal(r.height, 1080); assert.equal(r.format, 'jpg')
  assert.equal(r.bytes, buf.length)
  assert.equal(r.file, resolve(p))
  assert.deepEqual([r.taken_at, r.gps, r.device, r.orientation], [null, null, null, null])
  assert.equal('error' in r, false)
})

for (const le of [true, false]) {
  const bo = le ? 'II' : 'MM'
  test(`EXIF 날짜·오프셋·기기·방향 (${bo})`, async () => {
    const d = tmp()
    const p = write(d, 'a.jpg', exifJpeg({ le, orientation: 6, date: '2024:12:12 15:27:27', offset: '+09:00', make: 'samsung', model: 'SM-S918N' }))
    const r = await analyzeFile(p)
    assert.equal(r.taken_at, '2024-12-12 15:27:27 +09:00')
    assert.equal(r.device, 'samsung SM-S918N')
    assert.equal(r.orientation, 6)
    assert.equal(r.width, 1440)
  })
  test(`GPS 북위·동경 + 고도 (${bo})`, async () => {
    const d = tmp()
    const p = write(d, 'a.jpg', exifJpeg({ le, gps: { latRef: 'N', lat: [37, 30, 0], lonRef: 'E', lon: [128, 15, 36], alt: 812.5 } }))
    const r = await analyzeFile(p)
    assert.ok(Math.abs(r.gps.lat - 37.5) < 1e-6)
    assert.ok(Math.abs(r.gps.lon - 128.26) < 1e-6)
    assert.ok(Math.abs(r.gps.alt - 812.5) < 1e-6)
  })
}

test('GPS 남위·서경은 음수, 고도 기준 1 은 해수면 아래', async () => {
  const d = tmp()
  const p = write(d, 'a.jpg', exifJpeg({ gps: { latRef: 'S', lat: [33, 51, 0], lonRef: 'W', lon: [151, 12, 0], alt: 20, altRef: 1 } }))
  const r = await analyzeFile(p)
  assert.ok(Math.abs(r.gps.lat + 33.85) < 1e-6)
  assert.ok(Math.abs(r.gps.lon + 151.2) < 1e-6)
  assert.ok(r.gps.alt < 0)
})

test('GPS 에 고도가 없으면 alt 는 null', async () => {
  const d = tmp()
  const r = await analyzeFile(write(d, 'a.jpg', exifJpeg({ gps: { latRef: 'N', lat: [37, 0, 0], lonRef: 'E', lon: [128, 0, 0] } })))
  assert.equal(r.gps.alt, null)
})

test('DateTimeOriginal 이 없으면 DateTimeDigitized 사용', async () => {
  const d = tmp()
  const r = await analyzeFile(write(d, 'a.jpg', exifJpeg({ digitized: '2023:01:02 03:04:05' })))
  assert.equal(r.taken_at, '2023-01-02 03:04:05')
})

test('EXIF 없는 JPEG 는 값이 모두 null', async () => {
  const d = tmp()
  const r = await analyzeFile(write(d, 'a.jpg', makeJpeg()))
  assert.deepEqual([r.taken_at, r.gps, r.device, r.orientation], [null, null, null, null])
})

test('깨진 EXIF 는 실패가 아니라 null (크기는 유지)', async () => {
  const d = tmp()
  // 1) IFD 오프셋이 파일 밖을 가리키는 TIFF
  const bad = Buffer.concat([Buffer.from('Exif\0\0'), Buffer.from('II'), Buffer.from([42, 0, 0xff, 0xff, 0xff, 0x7f])])
  const r1 = await analyzeFile(write(d, 'bad1.jpg', makeJpeg({ rawApp1: bad })))
  assert.equal(r1.taken_at, null); assert.equal(r1.width, 1440); assert.equal('error' in r1, false)
  // 2) 잘린 파일(EXIF 중간에서 절단)
  const good = exifJpeg({ date: '2024:12:12 15:27:27', make: 'x' })
  const r2 = await analyzeFile(write(d, 'bad2.jpg', good.subarray(0, 60)))
  assert.equal(r2.taken_at, null)
  // 3) 쓰레기 APP1
  const junk = Buffer.concat([Buffer.from('Exif\0\0MM'), Buffer.alloc(40, 0xff)])
  const r3 = await analyzeFile(write(d, 'bad3.jpg', makeJpeg({ rawApp1: junk })))
  assert.equal(r3.taken_at, null); assert.equal(r3.gps, null); assert.equal(r3.width, 1440)
})

test('JPEG 가 아닌 .jpg 는 error 를 담고 던지지 않는다', async () => {
  const d = tmp()
  const r = await analyzeFile(write(d, 'x.jpg', Buffer.from('not a jpeg at all')))
  assert.ok(r.error); assert.equal(r.width, null)
})

test('PNG·GIF·BMP 크기', async () => {
  const d = tmp()
  const png = await analyzeFile(write(d, 'a.png', makePngHeader(640, 480)))
  assert.deepEqual([png.format, png.width, png.height, png.taken_at], ['png', 640, 480, null])
  const gif = Buffer.alloc(13); gif.write('GIF89a'); gif.writeUInt16LE(320, 6); gif.writeUInt16LE(200, 8)
  const g = await analyzeFile(write(d, 'a.gif', gif))
  assert.deepEqual([g.format, g.width, g.height], ['gif', 320, 200])
  const bmp = Buffer.alloc(30); bmp.write('BM'); bmp.writeInt32LE(40, 14); bmp.writeInt32LE(100, 18); bmp.writeInt32LE(-50, 22)
  const b = await analyzeFile(write(d, 'a.bmp', bmp))
  assert.deepEqual([b.format, b.width, b.height], ['bmp', 100, 50])
})

test('HEIC 는 미지원 error', async () => {
  const d = tmp()
  const r = await analyzeFile(write(d, 'a.HEIC', Buffer.from('....ftypheic')))
  assert.equal(r.format, 'heic'); assert.equal(r.width, null); assert.equal(r.taken_at, null)
  assert.equal(r.error, 'HEIC 는 아직 분석하지 않습니다')
})

test('collectPaths: 폴더+파일+--list 혼합, 비사진·하위폴더 제외, 순서 유지', () => {
  const d = tmp(); const sub = join(d, 'dir'); mkdirSync(sub); mkdirSync(join(sub, 'nested'))
  write(sub, 'b.JPG', makeJpeg()); write(sub, 'a.png', makePngHeader(1, 1)); write(sub, 'note.txt', 'x')
  write(join(sub, 'nested'), 'deep.jpg', makeJpeg())
  const single = write(d, 'single.jpeg', makeJpeg())
  const other = write(d, 'other.gif', Buffer.alloc(13))
  const list = write(d, 'list.txt', `# 주석\n\n${other}\n${join(d, 'missing.jpg')}\n`)
  const { files, missing } = collectPaths([sub, single], list)
  assert.deepEqual(files.map((f) => f.split(/[\\/]/).pop()), ['a.png', 'b.JPG', 'single.jpeg', 'other.gif'])
  assert.equal(missing.length, 1)
})

test('summarize: 정렬(촬영순 → 없는 것은 입력 순) 과 요약', () => {
  const mk = (file, taken_at, extra = {}) => ({ file, bytes: 1, width: 1, height: 1, orientation: null, taken_at, gps: null, device: null, format: 'jpg', ...extra })
  const { photos, summary } = summarize([
    mk('n1', null), mk('late', '2024-02-01 00:00:00'), mk('n2', null, { error: 'x' }),
    mk('early', '2024-01-01 00:00:00', { gps: { lat: 1, lon: 2, alt: null } }),
  ])
  assert.deepEqual(photos.map((p) => p.file), ['early', 'late', 'n1', 'n2'])
  assert.deepEqual(summary, { total: 4, withDate: 2, withGps: 1, from: '2024-01-01 00:00:00', to: '2024-02-01 00:00:00', failed: 1 })
})

test('summarize: 날짜가 하나도 없으면 from/to 는 null', () => {
  const { summary } = summarize([{ file: 'a', taken_at: null, gps: null }])
  assert.equal(summary.from, null); assert.equal(summary.to, null)
})

test('formatLine: 사람용 한 줄 / 없는 항목은 "없음"', () => {
  const full = formatLine({ file: '/x/a.jpg', bytes: 523 * 1024, width: 1440, height: 1080, taken_at: '2024-12-12 15:27:27',
    gps: { lat: 37.12345, lon: 128.12345, alt: null }, device: 'samsung SM-S918N' })
  assert.equal(full, 'a.jpg | 1440×1080 | 523KB | 촬영 2024-12-12 15:27:27 | 위치 37.12345,128.12345 | 기기 samsung SM-S918N')
  const none = formatLine({ file: '/x/b.jpg', bytes: 2.5 * 1024 * 1024, width: null, height: null, taken_at: null, gps: null, device: null })
  assert.equal(none, 'b.jpg | 크기 없음 | 2.5MB | 촬영 없음 | 위치 없음 | 기기 없음')
})

test('CLI: 사람용 출력, 요약, 종료 코드 0', () => {
  const d = tmp()
  write(d, 'b.jpg', makeJpeg()); write(d, 'a.jpg', exifJpeg({ date: '2024:12:12 15:27:27' }))
  const r = run(d)
  assert.equal(r.status, 0)
  assert.match(r.stdout, /a\.jpg \| 1440×1080/)
  assert.match(r.stdout, /총 2장/); assert.match(r.stdout, /촬영 날짜 있음 1장/); assert.match(r.stdout, /위치 있음 0장/)
})

test('CLI: --json', () => {
  const d = tmp()
  write(d, 'a.jpg', exifJpeg({ date: '2024:12:12 15:27:27' }))
  const j = JSON.parse(run(d, '--json').stdout)
  assert.equal(j.photos.length, 1); assert.equal(j.summary.total, 1); assert.equal(j.summary.withDate, 1)
  assert.equal(j.summary.from, '2024-12-12 15:27:27')
})

test('CLI: 읽기 실패 파일이 있어도 종료 코드 0, failed 집계', () => {
  const d = tmp(); write(d, 'bad.jpg', Buffer.from('nope')); write(d, 'ok.jpg', makeJpeg())
  const r = run(d, '--json')
  assert.equal(r.status, 0); assert.equal(JSON.parse(r.stdout).summary.failed, 1)
})

test('CLI: 종료 코드 — 인자 없음/알 수 없는 옵션/--list 값 누락 = 2, 경로 전부 없음 = 1', () => {
  assert.equal(run().status, 2)
  assert.equal(run('--bogus').status, 2)
  assert.equal(run('--list').status, 2)
  assert.equal(run(join(tmpdir(), 'no-such-dir-xyz')).status, 1)
})

test('CLI: 사진을 읽기만 한다 (수정 시각 불변)', () => {
  const d = tmp(); const p = write(d, 'a.jpg', makeJpeg())
  const t = new Date('2020-01-01T00:00:00Z'); utimesSync(p, t, t)
  run(d)
  assert.equal(statSync(p).mtime.getTime(), t.getTime())
})

test('DateTimeDigitized 를 쓸 때는 OffsetTimeDigitized 를 붙인다', async () => {
  const d = tmp()
  const r = await analyzeFile(write(d, 'a.jpg', exifJpeg({ digitized: '2023:01:02 03:04:05', offset: '+01:00', offsetDigitized: '+09:00' })))
  assert.equal(r.taken_at, '2023-01-02 03:04:05 +09:00')
  const r2 = await analyzeFile(write(d, 'b.jpg', exifJpeg({ digitized: '2023:01:02 03:04:05', offset: '+01:00' })))
  assert.equal(r2.taken_at, '2023-01-02 03:04:05')
})

test('빈 날짜(0000:00:00 …)는 날짜 없음, Digitized 로 넘어가지 않고 유효한 쪽을 쓴다', async () => {
  const d = tmp()
  const a = await analyzeFile(write(d, 'a.jpg', exifJpeg({ date: '0000:00:00 00:00:00' })))
  assert.equal(a.taken_at, null)
  const b = await analyzeFile(write(d, 'b.jpg', exifJpeg({ date: '2024:00:12 01:02:03' })))
  assert.equal(b.taken_at, null)
  const c = await analyzeFile(write(d, 'c.jpg', exifJpeg({ date: '0000:00:00 00:00:00', digitized: '2023:01:02 03:04:05' })))
  assert.equal(c.taken_at, '2023-01-02 03:04:05')
})

test('GPS 기준이 N/S, E/W 가 아니면 gps 는 null', async () => {
  const d = tmp()
  const bad1 = await analyzeFile(write(d, 'a.jpg', exifJpeg({ gps: { latRef: 'X', lat: [37, 0, 0], lonRef: 'E', lon: [128, 0, 0] } })))
  assert.equal(bad1.gps, null)
  const bad2 = await analyzeFile(write(d, 'b.jpg', exifJpeg({ gps: { latRef: 'N', lat: [37, 0, 0], lonRef: 'N', lon: [128, 0, 0] } })))
  assert.equal(bad2.gps, null)
})

test('AltitudeRef 가 없으면 고도는 양수', async () => {
  const d = tmp()
  const buf = makeJpeg({ tiff: buildTiff({ ifd0: [], gps: [
    ascii(0x0001, 'N'), rationals(0x0002, dms(37, 0, 0)), ascii(0x0003, 'E'), rationals(0x0004, dms(128, 0, 0)),
    rationals(0x0006, [[500, 10]]),
  ] }) })
  const r = await analyzeFile(write(d, 'a.jpg', buf))
  assert.equal(r.gps.alt, 50)
})

test('EXIF/GPS 포인터가 LONG 이 아니면 따라가지 않는다', async () => {
  const d = tmp()
  const r = await analyzeFile(write(d, 'a.jpg', exifJpeg({ ptrType: 3, date: '2024:12:12 15:27:27', gps: { latRef: 'N', lat: [37, 0, 0], lonRef: 'E', lon: [128, 0, 0] } })))
  assert.equal(r.taken_at, null); assert.equal(r.gps, null)
})
