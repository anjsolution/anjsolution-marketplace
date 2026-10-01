#!/usr/bin/env node
// 템플릿 폴더의 templates.json 을 만들고 갱신한다.
//   sync <폴더|templates.json>          폴더 바로 아래 .hwpx 와 path 로 등록된 파일의 페이지·필드를 채운다
//   add  <templates.json> <hwpx> [이름]  다른 위치의 파일을 path 로 등록한다
// 직접 쓴 키(name·when·aliases·추가 키, 페이지 role 등)는 건드리지 않고 pages[].fields·sha256·updated 만 고친다.
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { basename, dirname, extname, isAbsolute, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ENGINE = new URL('../../hwpx/scripts/lib/pages.mjs', import.meta.url)
const USAGE = '사용법: node template-meta.mjs sync <폴더|templates.json>\n       node template-meta.mjs add <templates.json> <hwpx 경로> [이름]'

const jsonPathOf = (p) => (existsSync(p) && statSync(p).isDirectory() ? join(p, 'templates.json') : p)
const load = (f) => (existsSync(f) ? JSON.parse(readFileSync(f, 'utf8')) : { schema: 1, templates: {} })
const save = (f, j) => writeFileSync(f, JSON.stringify(j, null, 2) + '\n', 'utf8')
const today = () => new Date().toISOString().slice(0, 10)

async function describe(file, entry) {
  const { listPages } = await import(ENGINE)
  const bytes = readFileSync(file)
  const sha256 = createHash('sha256').update(bytes).digest('hex')
  if (entry.sha256 === sha256 && entry.pages) { delete entry.missing; return entry }
  const { pages } = await listPages(bytes)
  const old = new Map((entry.pages || []).map((pg) => [pg.page, pg]))
  entry.pages = pages.map((pg) => ({
    ...(old.get(pg.page) || {}),
    page: pg.page,
    fields: pg.fields.map((f) => ({ name: f.name, type: f.image ? 'image' : 'text', count: f.count })),
  }))
  entry.sha256 = sha256
  entry.updated = today()
  delete entry.missing
  return entry
}

const fileOf = (jsonFile, key, entry) =>
  entry.path ? (isAbsolute(entry.path) ? entry.path : resolve(dirname(jsonFile), entry.path)) : join(dirname(jsonFile), key)

async function sync(target) {
  const f = jsonPathOf(target)
  const j = load(f)
  j.templates ||= {}
  const dir = dirname(f)
  if (existsSync(dir)) {
    for (const n of readdirSync(dir).filter((n) => extname(n).toLowerCase() === '.hwpx').sort())
      if (!j.templates[n] && statSync(join(dir, n)).isFile()) j.templates[n] = { name: basename(n, extname(n)), when: '' }
  }
  for (const [key, entry] of Object.entries(j.templates)) {
    const file = fileOf(f, key, entry)
    if (existsSync(file)) await describe(file, entry)
    else { entry.missing = true; console.error(`없음: ${key} → ${file}`) }
  }
  save(f, j)
  console.log(`${f} — 템플릿 ${Object.keys(j.templates).length}개`)
}

async function add(jsonFile, hwpx, name) {
  const f = jsonPathOf(jsonFile)
  const j = load(f)
  j.templates ||= {}
  const key = name || basename(hwpx, extname(hwpx))
  const entry = j.templates[key] || { name: key, when: '' }
  entry.path = resolve(hwpx)
  j.templates[key] = await describe(entry.path, entry)
  save(f, j)
  console.log(`등록: ${key} → ${entry.path}`)
}

export async function main([cmd, a, b, c]) {
  try {
    if (cmd === 'sync' && a) await sync(a)
    else if (cmd === 'add' && a && b) {
      if (!existsSync(b)) { console.error(`파일이 없습니다: ${b}`); return 1 }
      await add(a, b, c)
    } else { console.error(USAGE); return 2 }
    return 0
  } catch (e) {
    console.error(`실패: ${e.message}`)
    return 1
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).then((code) => { process.exitCode = code })
}
