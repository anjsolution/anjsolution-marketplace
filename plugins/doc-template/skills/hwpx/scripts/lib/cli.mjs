import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { scan } from './scan.mjs'
import { listPages } from './pages.mjs'
import { fill } from './fill.mjs'

const USAGE = `사용법:
  hwpx scan <서식.hwpx> [--json]
  hwpx pages <서식.hwpx> [--json]
  hwpx fill <서식.hwpx> <값.json> -o <결과.hwpx> [--json]
  hwpx export <서식.hwpx> <값.json> -o <결과.pdf> [--hwpx <결과.hwpx>] [--json]`

class UsageError extends Error {}

function parse(argv) {
  const [cmd, ...rest] = argv
  const pos = []
  const opt = {}
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i]
    if (a === '--json') opt.json = true
    else if (a === '-o' || a === '--hwpx') {
      const v = rest[++i]
      if (v === undefined || v.startsWith('-')) throw new UsageError(`${a} 뒤에 값이 필요합니다.`)
      opt[a === '-o' ? 'out' : 'hwpx'] = v
    }
    else pos.push(a)
  }
  const need = { scan: 1, pages: 1, fill: 2, export: 2 }[cmd]
  if (!need) throw new UsageError(`알 수 없는 명령: ${cmd ?? '(없음)'}`)
  if (pos.length !== need) throw new UsageError(`${cmd}: 인자 개수가 맞지 않습니다.`)
  if ((cmd === 'fill' || cmd === 'export') && !opt.out) throw new UsageError(`${cmd}: -o <결과 파일> 이 필요합니다.`)
  return { cmd, pos, opt }
}

const fieldLine = (f) => `${f.name} ×${f.count}${f.image ? ' [이미지]' : ''}`

function printReport(report, saved) {
  const lines = saved.map((s) => `저장: ${s}`)
  const filled = Object.entries(report.filled).map(([k, n]) => `${k}×${n}`)
  if (filled.length) lines.push(`채움: ${filled.join(', ')}`)
  if (report.missing.length) lines.push(`값 없음: ${report.missing.join(', ')}`)
  if (report.unknownKeys.length) lines.push(`서식에 없는 키: ${report.unknownKeys.join(', ')}`)
  for (const im of report.images) lines.push(`이미지: ${im.key} ← ${im.file} (${im.widthMm}×${im.heightMm}mm, 회전 ${im.angle}°)`)
  for (const w of report.warnings) lines.push(`경고: ${w}`)
  console.log(lines.join('\n'))
}

export async function main(argv) {
  let args
  try { args = parse(argv) } catch (e) {
    console.error(`${e.message}\n\n${USAGE}`)
    return 2
  }
  const { cmd, pos, opt } = args
  try {
    const bytes = readFileSync(pos[0])
    if (cmd === 'scan') {
      const r = await scan(bytes)
      if (opt.json) console.log(JSON.stringify(r, null, 2))
      else {
        console.log(r.fields.map(fieldLine).join('\n') || '(토큰 없음)')
        if (r.broken.length) console.log(`쪼개진 토큰: ${r.broken.join(' | ')}`)
      }
      return 0
    }
    if (cmd === 'pages') {
      const r = await listPages(bytes)
      if (opt.json) console.log(JSON.stringify(r, null, 2))
      else {
        for (const pg of r.pages)
          console.log(`페이지 ${pg.page}: ${pg.fields.map((f) => f.name + (f.image ? ' [이미지]' : '')).join(', ') || '(토큰 없음)'}`)
        for (const w of r.warnings) console.log(`경고: ${w}`)
      }
      return 0
    }
    const valuesPath = resolve(pos[1])
    const input = JSON.parse(readFileSync(valuesPath, 'utf8'))
    if (input === null || typeof input !== 'object' || Array.isArray(input)) {
      console.error('값 파일은 { "values": …, "pages": … } 형태의 객체여야 합니다.')
      return 1
    }
    const { bytes: out, report } = await fill(bytes, input, { baseDir: dirname(valuesPath) })
    const saved = []
    if (cmd === 'fill') {
      writeFileSync(opt.out, out); saved.push(resolve(opt.out))
    } else {
      const { renderSvg, svgToPdf, closeBrowser } = await import('./export.mjs')
      try {
        if (opt.hwpx) {
          writeFileSync(opt.hwpx, out); saved.push(resolve(opt.hwpx))
          console.error(`저장: ${resolve(opt.hwpx)} (PDF 변환 전)`)
        }
        const { svg } = await renderSvg(out)
        writeFileSync(opt.out, await svgToPdf(svg)); saved.push(resolve(opt.out))
      } finally { await closeBrowser() }
    }
    if (opt.json) console.log(JSON.stringify({ saved, report }, null, 2))
    else printReport(report, saved)
    return 0
  } catch (e) {
    console.error(`실패: ${e.message}`)
    return 1
  }
}
