import { readHwpx, readText } from './package.mjs'
import { tokenRe, isImageKey, unescapeXml } from './tokens.mjs'

export function scanXml(xml) {
  const counts = new Map()
  const broken = []
  for (const m of xml.matchAll(tokenRe())) {
    const name = unescapeXml(m[1])
    counts.set(name, (counts.get(name) ?? 0) + 1)
  }
  // 온전한 토큰을 걷어낸 뒤에도 중괄호가 남은 <hp:t> = 한글이 run 을 쪼갠 토큰
  for (const t of xml.matchAll(/<hp:t>(.*?)<\/hp:t>/gs)) {
    if (/[{}]/.test(t[1].replace(tokenRe(), ''))) broken.push(unescapeXml(t[1]))
  }
  return { counts, broken }
}

export async function scan(bytes) {
  const { zip, sectionNames } = await readHwpx(bytes)
  const counts = new Map()
  const broken = []
  for (const name of sectionNames) {
    const r = scanXml(await readText(zip, name))
    for (const [k, v] of r.counts) counts.set(k, (counts.get(k) ?? 0) + v)
    broken.push(...r.broken)
  }
  const fields = [...counts].map(([name, count]) => ({ name, count, image: isImageKey(name) }))
  return { fields, broken }
}
