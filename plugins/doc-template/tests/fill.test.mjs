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

test('복사본 개체 id/instid 유일, 필드 id 는 그대로', async () => {
  const table = cellTable('{{사진-1}}', { pageBreak: 1 }).replace('<hp:tbl id=', '<hp:tbl instid="777" id=')
  const field = '<hp:p id="9000" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="0"><hp:ctrl><hp:fieldBegin id="42" type="CLICK_HERE"/></hp:ctrl><hp:t>x</hp:t></hp:run></hp:p>'
  const bytes = await makeHwpx({ sections: [p('{{공사명}}', { head: secPrRun() }) + table + field] })
  const { bytes: out } = await fill(bytes, { values: {}, pages: [{ page: 2 }, { page: 2 }, { page: 2 }] })
  const xml = await section0(out)
  const tags = [...xml.matchAll(/<hp:tbl [^>]*>/g)].map((m) => m[0])
  assert.equal(tags.length, 3)
  for (const a of ['id', 'instid']) {
    const ids = tags.map((t) => t.match(new RegExp(`\\b${a}="(\\d+)"`))[1])
    assert.equal(new Set(ids).size, 3, a)
  }
  assert.equal((xml.match(/<hp:fieldBegin id="42"/g) ?? []).length, 3)
})

const combinedHead = () => secPrRun().replace('</hp:run>', '<hp:t>{{공사명}}</hp:t></hp:run>')

test('첫 문단 run 에 구역 정의와 텍스트가 같이 있어도 텍스트는 모든 복사본에 남는다', async () => {
  const bytes = await makeHwpx({ sections: [p('', { head: combinedHead() }) + cellTable('{{사진-1}}', { pageBreak: 1 })] })
  const { bytes: out } = await fill(bytes, { values: { 공사명: 'P' }, pages: [{ page: 2 }, { page: 1 }, { page: 1 }] })
  const xml = topParas(await section0(out))
  assert.equal((xml.match(/<hp:secPr/g) ?? []).length, 1)
  assert.equal((xml.match(/<hp:colPr/g) ?? []).length, 1)
  assert.match(xml.slice(0, xml.indexOf('</hp:p>')), /<hp:secPr/)
  assert.deepEqual(texts(xml).filter((t) => t.includes('P')), ['P', 'P'])
  assert.ok(!xml.includes('{{'))
})

test('페이지 2의 일반 ctrl(쪽 번호)은 모든 복사본에 남는다', async () => {
  const num = '<hp:p id="9100" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="0"><hp:ctrl><hp:pageNum pos="BOTTOM_CENTER" formatType="DIGIT" sideChar="-"/></hp:ctrl></hp:run></hp:p>'
  const bytes = await makeHwpx({ sections: [p('a', { head: secPrRun() }) + cellTable('t', { pageBreak: 1 }) + num] })
  const { bytes: out } = await fill(bytes, { values: {}, pages: [{ page: 2 }, { page: 2 }, { page: 2 }] })
  assert.equal(((await section0(out)).match(/<hp:pageNum /g) ?? []).length, 3)
})

test('빈 문자열·null 페이지 값은 공통 값으로 대체', async () => {
  const bytes = await makeHwpx({ sections: [p('{{a}}|{{b}}')] })
  const { bytes: out } = await fill(bytes, { values: { a: 'A', b: 'B' }, pages: [{ page: 1, values: { a: '', b: null } }] })
  assert.ok((await section0(out)).includes('<hp:t>A|B</hp:t>'))
})

test('pages 형식이 잘못되면 실패', async () => {
  const bytes = await photoTemplate()
  await assert.rejects(fill(bytes, { pages: [] }), /pages 는 1개 이상/)
  await assert.rejects(fill(bytes, { pages: [null] }), /pages 는 1개 이상/)
  await assert.rejects(fill(bytes, { pages: [{ page: '1' }] }), /pages 는 1개 이상/)
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
