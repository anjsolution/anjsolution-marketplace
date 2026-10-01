/**
 * HWPX -> 미리보기 SVG / PDF.
 * 출처: hwpx-editor core/render.js (findChrome 후보 확장·export).
 *
 * 조판은 kordoc 에 맡긴다. 한컴 저장본의 조판 캐시를 지운 뒤라
 * reflow 경로로 재조판되며, 실측에서 한컴 출력과 페이지 수·줄바꿈
 * 위치가 일치했다.
 */
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { renderHwpxToSvg } from 'kordoc'
import puppeteer from 'puppeteer-core'

export async function renderSvg(bytes) {
  const r = await renderHwpxToSvg(new Uint8Array(bytes), { reflow: true })
  if (!r?.svg) throw new Error('SVG 렌더 실패')
  return { svg: r.svg, pageCount: r.pageCount ?? 1 }
}

const CHROME_CANDIDATES = [
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
]

const NO_BROWSER = 'PDF 를 만들 브라우저(Edge/Chrome)를 찾을 수 없습니다. CHROME_PATH 로 지정하거나, hwpx 는 fill 로 받으세요.'

function chromeCandidates() {
  return [process.env.CHROME_PATH, ...CHROME_CANDIDATES].filter((p) => p && existsSync(p))
}

export function findChrome() {
  const hit = chromeCandidates()[0]
  if (!hit) throw new Error(NO_BROWSER)
  return hit
}

// 브라우저 기동이 느려서(약 1초) 프로세스당 하나를 재사용한다.
// 다만 브라우저는 밖에서 죽을 수 있다(사용자가 프로세스를 종료, OOM 등).
// 죽은 인스턴스를 계속 붙들면 이후 모든 PDF 요청이 실패하므로 살아 있는지 보고 다시 띄운다.
let browserPromise = null
// 브라우저 프로필 폴더는 직접 만들어 넘긴다. puppeteer 가 만든 임시 프로필은 브라우저 종료 때
// puppeteer 가 지우는데, Windows 에서는 아직 잠긴 lockfile 때문에 EBUSY 가 나고 그 오류가
// 잡을 수 없는 곳에서 던져져 프로세스가 죽는다(PDF 를 다 쓴 뒤에도 종료 코드 1). 직접 넘긴 폴더는
// puppeteer 가 지우지 않으므로 closeBrowser 에서 재시도하며 지운다.
let profileDir = null

function removeProfile() {
  if (!profileDir) return
  try {
    rmSync(profileDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 })
  } catch {
    /* 지우지 못한 임시 폴더는 남겨 둔다 — PDF 결과에는 영향이 없다 */
  }
  profileDir = null
}

// 기동 "실패"로 보고된 브라우저가 실제로는 떠 있는 경우가 있다. Windows 의 Edge 는 실행 파일이
// 곧바로 끝나고 진짜 브라우저를 따로 띄우므로 puppeteer 는 실패로 보지만, 헤드리스 Edge 가
// 프로세스 트리째 남는다(Task 8 실측: export 한 번에 msedge 약 8개씩 누적). 그 브라우저가 프로필
// 폴더에 남기는 DevToolsActivePort 로 붙어서 닫는다.
async function closeOrphan(userDataDir) {
  const portFile = join(userDataDir, 'DevToolsActivePort')
  for (let i = 0; i < 30; i++) {
    if (existsSync(portFile)) {
      try {
        const [port, path] = readFileSync(portFile, 'utf8').split(/\r?\n/)
        if (port && path) {
          const b = await puppeteer.connect({ browserWSEndpoint: `ws://127.0.0.1:${port}${path}` })
          await b.close()
          return
        }
      } catch {
        /* 파일이 아직 쓰이는 중이거나 이미 종료됨 — 다시 본다 */
      }
    }
    await new Promise((r) => setTimeout(r, 100))
  }
}

// 존재하는 후보를 순서대로 시도한다. 파일은 있어도 기동에 실패하는 브라우저(스텁 등)가 있기 때문이다.
async function launch() {
  const found = chromeCandidates()
  if (!found.length) throw new Error(NO_BROWSER)
  let last
  removeProfile()
  profileDir = mkdtempSync(join(tmpdir(), 'hwpx-pdf-profile-'))
  for (const executablePath of found) {
    // 후보마다 새 하위 폴더 — 기동에 실패한 브라우저가 남긴 잠금을 다음 후보가 물려받지 않게
    const userDataDir = mkdtempSync(join(profileDir, 'p-'))
    try {
      return await puppeteer.launch({
        executablePath,
        userDataDir,
        headless: true,
        args: ['--no-sandbox', '--disable-dev-shm-usage'],
      })
    } catch (e) {
      last = e
      await closeOrphan(userDataDir)
    }
  }
  throw new Error(`브라우저 기동 실패 (시도: ${found.join(', ')}): ${last?.message?.split('\n')[0]}`)
}

async function getBrowser() {
  if (browserPromise) {
    try {
      const b = await browserPromise
      if (b.connected) return b
    } catch {
      /* 기동 자체가 실패했던 경우 — 아래에서 다시 띄운다 */
    }
    browserPromise = null
  }
  browserPromise = launch()
  return browserPromise
}

/**
 * SVG -> PDF.
 *
 * kordoc 은 전 페이지를 하나의 SVG 에 세로로 쌓고 페이지 사이에 여백을 둔다
 * (2페이지 예: 페이지 높이 841.88, 2쪽 오프셋 865.88 = 24pt 간격).
 * 총 높이를 쪽수로 나누면 경계가 어긋나 빈 페이지가 생기므로,
 * <g data-page> 의 실제 오프셋을 읽어 쪽마다 잘라 붙인다.
 */
export async function svgToPdf(svg) {
  const browser = await getBrowser()
  const page = await browser.newPage()
  try {
    await page.setContent(`<!doctype html><body style="margin:0">${svg}</body>`, {
      waitUntil: 'load',
    })

    const geom = await page.evaluate(() => {
      const svgEl = document.querySelector('svg')
      const [, , w, h] = svgEl.getAttribute('viewBox').split(/\s+/).map(Number)
      const offsets = [...svgEl.querySelectorAll('g[data-page]')].map((g) => {
        const m = /translate\(\s*([-\d.]+)[\s,]+([-\d.]+)\s*\)/.exec(g.getAttribute('transform') || '')
        return m ? Number(m[2]) : 0
      })
      // 쪽 높이 = 첫 클립 사각형(= 용지 높이). 없으면 오프셋 간격에서 추정.
      const clip = svgEl.querySelector('clipPath rect')
      const pageH = clip ? Number(clip.getAttribute('height')) : (offsets[1] ?? h)
      return { w, h, pageH, offsets: offsets.length ? offsets : [0] }
    })

    // 쪽마다 같은 SVG 를 음수 top 으로 밀어 넣고 용지 크기로 잘라낸다.
    const pages = geom.offsets
      .map(
        (off) => `<div class="pg"><div class="inner" style="top:${-off}pt">${svg}</div></div>`,
      )
      .join('')
    const html = `<!doctype html><style>
      @page { size: ${geom.w}pt ${geom.pageH}pt; margin: 0 }
      html,body { margin:0; padding:0 }
      .pg { position:relative; width:${geom.w}pt; height:${geom.pageH}pt; overflow:hidden;
            break-after:page; page-break-after:always }
      .pg:last-child { break-after:auto; page-break-after:auto }
      .inner { position:absolute; left:0 }
      .inner svg { display:block }
    </style><body>${pages}</body>`

    await page.setContent(html, { waitUntil: 'load' })
    // page.pdf 는 pt 를 모른다 (px/in/cm/mm 만). 1pt = 1/72in 로 환산한다.
    return await page.pdf({
      width: `${geom.w / 72}in`,
      height: `${geom.pageH / 72}in`,
      printBackground: true,
      pageRanges: '',
    })
  } finally {
    await page.close()
  }
}

export async function closeBrowser() {
  if (!browserPromise) return removeProfile()
  const pending = browserPromise
  browserPromise = null
  try {
    await (await pending).close()
  } catch {
    /* 기동 실패·이미 종료된 브라우저는 닫을 것이 없다 */
  }
  removeProfile()
}
