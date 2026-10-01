#!/usr/bin/env node
// 첫 실행 때 의존성을 설치하고 CLI 를 실행한다. 플러그인 설치는 파일만 복사하므로 node_modules 가 없다.
import { existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const REQUIRED = ['jszip', '@xmldom/xmldom', 'kordoc', 'puppeteer-core']
if (!REQUIRED.every((m) => existsSync(join(here, 'node_modules', m)))) {
  console.error('[hwpx] 처음 실행이라 의존성을 설치합니다 (1회)…')
  // npm 로그가 --json 출력(stdout)에 섞이지 않도록 stdout 도 stderr(2)로 보낸다.
  const r = spawnSync('npm', ['install', '--omit=optional', '--no-audit', '--no-fund'], {
    cwd: here, stdio: ['ignore', 2, 2], shell: process.platform === 'win32',
  })
  if (r.status !== 0) {
    console.error(`[hwpx] 의존성 설치 실패. 직접 실행하세요: cd "${here}" && npm install --omit=optional`)
    process.exit(3)
  }
}
const { main } = await import('./lib/cli.mjs')
process.exit(await main(process.argv.slice(2)))
