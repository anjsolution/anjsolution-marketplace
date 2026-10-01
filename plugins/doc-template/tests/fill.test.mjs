import { test } from 'node:test'
import assert from 'node:assert/strict'
import { fill } from '../skills/hwpx/scripts/lib/fill.mjs'
import { readHwpx, readText } from '../skills/hwpx/scripts/lib/package.mjs'
import { makeHwpx, p, cellTable, secPrRun } from './helpers/make-hwpx.mjs'

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

const photoTemplate = () => makeHwpx({ sections: [
  p('{{공사명}}', { head: secPrRun() }) +
  cellTable('{{사진-1}}', { pageBreak: 1 }) + p('{{내용-1}} {{날짜}}'),
] })

const texts = (xml) => [...xml.matchAll(/<hp:t>(.*?)<\/hp:t>/g)].map((m) => m[1])
const topParas = (xml) => xml.match(/<hs:sec[^>]*>(.*)<\/hs:sec>/s)[1]

test('같은 페이지를 반복하고 페이지별 값이 공통 값보다 우선', async () => {
  const { bytes: out } = await fill(await photoTemplate(), {
    values: { 공사명: 'P', 날짜: 'D', '내용-1': '공통' },
    pages: [{ page: 1 }, { page: 2, values: { '내용-1': '첫째' } }, { page: 2, values: { '내용-1': '둘째', 날짜: 'D2' } }],
  })
  const xml = await section0(out)
  assert.deepEqual(texts(xml).filter(Boolean), ['P', '첫째 D', '둘째 D2'])
})

test('pageBreak 는 둘째 페이지부터 첫 문단에만', async () => {
  const { bytes: out } = await fill(await photoTemplate(), {
    values: {}, pages: [{ page: 2 }, { page: 2 }, { page: 1 }],
  })
  const xml = topParas(await section0(out))
  const flags = [...xml.matchAll(/<hp:p [^>]*pageBreak="(\d)"/g)].map((m) => m[1])
  assert.equal(flags.filter((f) => f === '1').length, 2)
  assert.match(xml, /^<hp:p [^>]*pageBreak="0"/)
})

test('secPr 은 첫 문단에 정확히 하나', async () => {
  const { bytes: out } = await fill(await photoTemplate(), { values: {}, pages: [{ page: 2 }, { page: 1 }, { page: 1 }] })
  const xml = topParas(await section0(out))
  assert.equal((xml.match(/<hp:secPr/g) ?? []).length, 1)
  const first = xml.slice(0, xml.indexOf('</hp:p>'))
  assert.match(first, /<hp:secPr/)
})

test('복사본 id 유일', async () => {
  const { bytes: out } = await fill(await photoTemplate(), { values: {}, pages: [{ page: 2 }, { page: 2 }, { page: 2 }] })
  const xml = await section0(out)
  const ids = [...xml.matchAll(/<hp:(?!p )\w+ [^>]*\bid="(\d+)"/g)].map((m) => m[1]).filter((x) => x !== '0')
  assert.equal(new Set(ids).size, ids.length)
})

test('없는 페이지 번호는 실패', async () => {
  await assert.rejects(fill(await photoTemplate(), { pages: [{ page: 3 }] }), /페이지 3/)
})

test('구역이 둘인 서식에 pages 를 주면 실패', async () => {
  const bytes = await makeHwpx({ sections: [p('a'), p('b')] })
  await assert.rejects(fill(bytes, { pages: [{ page: 1 }] }), /구역이 하나/)
})

test('pages 를 생략하면 원본 그대로', async () => {
  const { bytes: out } = await fill(await photoTemplate(), { values: { 공사명: 'P' } })
  assert.equal((topParas(await section0(out)).match(/pageBreak="1"/g) ?? []).length, 1)
})

test('상속 속성 이름 토큰은 값 없음으로 처리', async () => {
  const bytes = await makeHwpx({ sections: [p('[{{constructor}}][{{toString}}]')] })
  const { bytes: out, report } = await fill(bytes, { values: {} })
  assert.match(await section0(out), /<hp:t>\[\]\[\]<\/hp:t>/)
  assert.deepEqual(report.missing, ['constructor', 'toString'])
  const r2 = await fill(bytes, { values: {}, pages: [{ page: 1, values: {} }] })
  assert.deepEqual(r2.report.missing, ['constructor', 'toString'])
})
