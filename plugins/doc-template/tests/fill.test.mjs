import { test } from 'node:test'
import assert from 'node:assert/strict'
import { fill } from '../skills/hwpx/scripts/lib/fill.mjs'
import { readHwpx, readText } from '../skills/hwpx/scripts/lib/package.mjs'
import { makeHwpx, p } from './helpers/make-hwpx.mjs'

const section0 = async (bytes) => readText((await readHwpx(bytes)).zip, 'Contents/section0.xml')

test('공통 값을 채우고 횟수를 보고한다', async () => {
  const bytes = await makeHwpx({ sections: [p('{{공사명}}-{{공사명}}')] })
  const { bytes: out, report } = await fill(bytes, { values: { 공사명: 'A사업' } })
  assert.match(await section0(out), /<hp:t>A사업-A사업<\/hp:t>/)
  assert.deepEqual(report.filled, { 공사명: 2 })
})

test('값 없는 토큰은 빈칸으로 지우고 missing 에 보고', async () => {
  const bytes = await makeHwpx({ sections: [p('[{{위치}}]')] })
  const { bytes: out, report } = await fill(bytes, { values: {} })
  assert.match(await section0(out), /<hp:t>\[\]<\/hp:t>/)
  assert.deepEqual(report.missing, ['위치'])
})

test('특수문자 값은 XML 을 깨지 않는다', async () => {
  const bytes = await makeHwpx({ sections: [p('{{공사명}}')] })
  const { bytes: out } = await fill(bytes, { values: { 공사명: 'A<B>&C' } })
  assert.match(await section0(out), /A&lt;B>&amp;C|A&lt;B&gt;&amp;C/)
})

test('서식에 없는 키는 unknownKeys', async () => {
  const bytes = await makeHwpx({ sections: [p('{{a}}')] })
  const { report } = await fill(bytes, { values: { a: '1', zz: '2' } })
  assert.deepEqual(report.unknownKeys, ['zz'])
})

test('조판 캐시(linesegarray)를 지운다', async () => {
  const bytes = await makeHwpx({ sections: [p('{{a}}')] })
  const { bytes: out } = await fill(bytes, { values: { a: '1' } })
  assert.doesNotMatch(await section0(out), /linesegarray/)
})
