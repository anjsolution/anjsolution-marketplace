import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { makeHwpx, p, cellTable, secPrRun } from './helpers/make-hwpx.mjs'

const CLI = fileURLToPath(new URL('../skills/manage/scripts/template-meta.mjs', import.meta.url))
const run = (...a) => spawnSync(process.execPath, [CLI, ...a], { encoding: 'utf8' })
const read = (f) => JSON.parse(readFileSync(f, 'utf8'))

const tpl = () => makeHwpx({ sections: [p('{{공사명}}', { head: secPrRun() }) + cellTable('{{사진-1}}', { pageBreak: 1 }) + p('{{내용-1}}')] })

test('sync: 폴더의 hwpx 를 등록하고 페이지·필드를 채운다 (하위 폴더 제외)', async () => {
  const d = mkdtempSync(join(tmpdir(), 'tm-'))
  writeFileSync(join(d, 'a.hwpx'), await tpl())
  mkdirSync(join(d, 'sub')); writeFileSync(join(d, 'sub', 'b.hwpx'), await tpl())
  assert.equal(run('sync', d).status, 0)
  const j = read(join(d, 'templates.json'))
  assert.deepEqual(Object.keys(j.templates), ['a.hwpx'])
  const t = j.templates['a.hwpx']
  assert.equal(t.name, 'a')
  assert.deepEqual(t.pages.map((x) => x.page), [1, 2])
  assert.deepEqual(t.pages[1].fields, [{ name: '사진-1', type: 'image', count: 1 }, { name: '내용-1', type: 'text', count: 1 }])
  assert.match(t.sha256, /^[0-9a-f]{64}$/)
})

test('sync: 직접 쓴 키(추가 키 포함)와 페이지 role 은 보존하고 자동 키만 갱신', async () => {
  const d = mkdtempSync(join(tmpdir(), 'tm-'))
  writeFileSync(join(d, 'a.hwpx'), await tpl())
  run('sync', d)
  const f = join(d, 'templates.json')
  const j = read(f)
  j.templates['a.hwpx'].when = '입고 때'
  j.templates['a.hwpx'].담당팀 = 'Ai-Ops'
  j.templates['a.hwpx'].pages[1].role = '사진 칸'
  writeFileSync(f, JSON.stringify(j))
  writeFileSync(join(d, 'a.hwpx'), await makeHwpx({ sections: [p('{{공사명}} {{날짜}}', { head: secPrRun() }) + cellTable('{{사진-1}}', { pageBreak: 1 })] }))
  run('sync', d)
  const t = read(f).templates['a.hwpx']
  assert.equal(t.when, '입고 때'); assert.equal(t.담당팀, 'Ai-Ops'); assert.equal(t.pages[1].role, '사진 칸')
  assert.deepEqual(t.pages[0].fields.map((x) => x.name), ['공사명', '날짜'])
})

test('add: 다른 위치 파일을 path 로 등록, 없어지면 missing 표시', async () => {
  const d = mkdtempSync(join(tmpdir(), 'tm-')); const other = mkdtempSync(join(tmpdir(), 'tm-o-'))
  // 이 PC 의 Node 는 한글 이름 파일을 rmSync 하면 프로세스가 죽는다 — 파일 이름은 영문, 키는 이름 인자로
  const ext = join(other, 'cert.hwpx'); writeFileSync(ext, await tpl())
  const f = join(d, 'templates.json')
  assert.equal(run('add', f, ext, '증명서').status, 0)
  let t = read(f).templates['증명서']
  assert.equal(t.path, ext); assert.equal(t.pages.length, 2)
  rmSync(ext)
  run('sync', f)
  t = read(f).templates['증명서']
  assert.equal(t.missing, true); assert.equal(t.pages.length, 2)   // 마지막 정보는 남긴다
})

test('사용법 오류는 종료 코드 2', () => {
  assert.equal(run().status, 2)
  assert.equal(run('nope', 'x').status, 2)
})
