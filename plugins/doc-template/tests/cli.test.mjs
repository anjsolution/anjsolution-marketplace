import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, writeFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
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
