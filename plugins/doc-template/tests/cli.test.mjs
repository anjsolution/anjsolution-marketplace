import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, writeFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { makeHwpx, p, cellTable, secPrRun, makePng } from './helpers/make-hwpx.mjs'

const CLI = fileURLToPath(new URL('../skills/hwpx/scripts/hwpx.mjs', import.meta.url))
const run = (...args) => spawnSync(process.execPath, [CLI, ...args], { encoding: 'utf8' })

async function setup() {
  const dir = mkdtempSync(join(tmpdir(), 'hwpx-cli-'))
  writeFileSync(join(dir, 't.hwpx'), await makeHwpx({ sections: [
    p('{{공사명}}', { head: secPrRun() }) + cellTable('{{사진-1}}', { pageBreak: 1 }),
  ] }))
  writeFileSync(join(dir, 'a.png'), makePng(10, 10))
  return dir
}

test('scan --json', async () => {
  const dir = await setup()
  const r = run('scan', join(dir, 't.hwpx'), '--json')
  assert.equal(r.status, 0)
  assert.deepEqual(JSON.parse(r.stdout).fields.map((f) => f.name), ['공사명', '사진-1'])
})

test('pages 사람용 출력', async () => {
  const dir = await setup()
  const r = run('pages', join(dir, 't.hwpx'))
  assert.equal(r.status, 0)
  assert.match(r.stdout, /페이지 2: 사진-1 \[이미지\]/)
})

test('fill 은 상대 경로 사진을 값 파일 기준으로 찾는다', async () => {
  const dir = await setup()
  writeFileSync(join(dir, 'v.json'), JSON.stringify({
    values: { 공사명: 'P' }, pages: [{ page: 1 }, { page: 2, values: { '사진-1': 'a.png' } }, { page: 2 }],
  }))
  const out = join(dir, 'o.hwpx')
  const r = spawnSync(process.execPath, [CLI, 'fill', join(dir, 't.hwpx'), join(dir, 'v.json'), '-o', out],
    { encoding: 'utf8', cwd: tmpdir() })
  assert.equal(r.status, 0, r.stderr)
  assert.ok(existsSync(out))
  assert.match(r.stdout, /값 없음: 사진-1/)
})

test('없는 사진은 종료 코드 1', async () => {
  const dir = await setup()
  writeFileSync(join(dir, 'v.json'), JSON.stringify({ values: { '사진-1': 'zz.png' } }))
  const r = run('fill', join(dir, 't.hwpx'), join(dir, 'v.json'), '-o', join(dir, 'o.hwpx'))
  assert.equal(r.status, 1)
  assert.match(r.stderr, /이미지 파일이 없습니다/)
})

test('사용법 오류는 종료 코드 2', () => {
  assert.equal(run('nope').status, 2)
  assert.equal(run('fill', 'a.hwpx').status, 2)
})

test('-o 값이 없으면 종료 코드 2', () => {
  assert.equal(run('fill', 'a.hwpx', 'v.json', '-o').status, 2)
  assert.equal(run('export', 'a.hwpx', 'v.json', '-o', 'x.pdf', '--hwpx').status, 2)
})

test('fill --json 은 {saved, report} 를 낸다', async () => {
  const dir = await setup()
  writeFileSync(join(dir, 'v.json'), JSON.stringify({ values: { 공사명: 'P' } }))
  const out = join(dir, 'o.hwpx')
  const r = run('fill', join(dir, 't.hwpx'), join(dir, 'v.json'), '-o', out, '--json')
  assert.equal(r.status, 0, r.stderr)
  const j = JSON.parse(r.stdout)
  assert.deepEqual(j.saved, [resolve(out)])
  assert.equal(j.report.filled['공사명'], 1)
  assert.ok(Array.isArray(j.report.missing))
})

test('CHROME_PATH 가 기동 불가 파일이어도 다음 브라우저로 넘어간다', async (t) => {
  const { findChrome, svgToPdf, closeBrowser } = await import('../skills/hwpx/scripts/lib/export.mjs')
  const prev = process.env.CHROME_PATH
  delete process.env.CHROME_PATH
  let real
  try { real = findChrome() } catch { t.skip('브라우저 없음'); return }
  const dir = mkdtempSync(join(tmpdir(), 'hwpx-bogus-'))
  const bogus = join(dir, 'fake-chrome.exe')
  writeFileSync(bogus, 'not a browser')
  process.env.CHROME_PATH = bogus
  try {
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 595 842"><g data-page="1"><rect width="10" height="10"/></g></svg>'
    const pdf = await svgToPdf(svg)
    assert.equal(Buffer.from(pdf.subarray(0, 4)).toString(), '%PDF')
  } finally {
    await closeBrowser()
    if (prev === undefined) delete process.env.CHROME_PATH; else process.env.CHROME_PATH = prev
  }
})

// Windows 에서 puppeteer 가 자기 임시 프로필을 지우다 EBUSY 로 프로세스를 죽이는 일이 있었다 (Task 8 실측).
// 프로필 폴더를 직접 만들어 넘기고, 닫을 때 우리가 지운다.
test('PDF 브라우저 프로필은 직접 만든 임시 폴더를 쓰고 닫을 때 지운다', async (t) => {
  const { findChrome, svgToPdf, closeBrowser } = await import('../skills/hwpx/scripts/lib/export.mjs')
  try { findChrome() } catch { t.skip('브라우저 없음'); return }
  const { readdirSync } = await import('node:fs')
  const ours = () => readdirSync(tmpdir()).filter((n) => n.startsWith('hwpx-pdf-profile-'))
  const before = new Set(ours())
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 595 842"><g data-page="1"><rect width="10" height="10"/></g></svg>'
  let during
  try {
    await svgToPdf(svg)
    during = ours().filter((n) => !before.has(n))
  } finally {
    await closeBrowser()
  }
  assert.equal(during.length, 1)
  assert.ok(!existsSync(join(tmpdir(), during[0])), '닫은 뒤 프로필 폴더가 남아 있음')
})

test('값 파일이 객체가 아니면 exit 1 과 한국어 오류', async () => {
  const dir = await setup()
  for (const body of ['null', '[]', '"abc"']) {
    writeFileSync(join(dir, 'v.json'), body)
    const r = run('fill', join(dir, 't.hwpx'), join(dir, 'v.json'), '-o', join(dir, 'o.hwpx'))
    assert.equal(r.status, 1, body)
    assert.match(r.stderr, /객체여야 합니다/)
  }
})
