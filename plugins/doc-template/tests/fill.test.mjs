import { test } from 'node:test'
import assert from 'node:assert/strict'
import { fill } from '../skills/hwpx/scripts/lib/fill.mjs'
import { readHwpx, readText } from '../skills/hwpx/scripts/lib/package.mjs'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { makeHwpx, p, cellTable, secPrRun, makePng, makeJpeg } from './helpers/make-hwpx.mjs'

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

const objectIds = (xml) => [...xml.matchAll(/<hp:(?:tbl|pic) [^>]*>/g)]
  .flatMap((t) => [...t[0].matchAll(/\s(?:id|instid)="(\d+)"/g)].map((m) => m[1]))
const workdir = () => mkdtempSync(join(tmpdir(), 'hwpx-'))

test('셀 안 이미지: 그림 삽입·BinData·매니페스트', async () => {
  const dir = workdir()
  writeFileSync(join(dir, 'a.png'), makePng(400, 200))
  const bytes = await makeHwpx({ sections: [cellTable('{{사진-1}}', { width: 41000, height: 21000, margin: 500 })] })
  const { bytes: out, report } = await fill(bytes, { values: { '사진-1': 'a.png' } }, { baseDir: dir })
  const { zip } = await readHwpx(out)
  const xml = await readText(zip, 'Contents/section0.xml')
  assert.match(xml, /<hp:pic /)
  assert.doesNotMatch(xml, /\{\{사진-1\}\}/)
  assert.match(xml, /<hp:sz width="39200" [^>]*height="19600"/)
  assert.ok(zip.file('BinData/image1.png'))
  assert.match(await readText(zip, 'Contents/content.hpf'), /id="image1" href="BinData\/image1.png"/)
  assert.equal(report.images[0].binId, 'image1')
})

test('hasMargin=0 이면 표 안쪽 여백(510/141)을 쓴다', async () => {
  const dir = workdir()
  writeFileSync(join(dir, 'a.png'), makePng(100, 100))
  const bytes = await makeHwpx({ sections: [cellTable('{{사진}}', { width: 11020, height: 10282, hasMargin: 0 })] })
  const { bytes: out } = await fill(bytes, { values: { 사진: 'a.png' } }, { baseDir: dir })
  assert.match(await section0(out), /<hp:sz width="9800" [^>]*height="9800"/)
})

test('같은 파일은 BinData 하나를 공유', async () => {
  const dir = workdir()
  writeFileSync(join(dir, 'a.png'), makePng(10, 10))
  const bytes = await makeHwpx({ sections: [cellTable('{{사진-1}}') + cellTable('{{사진-2}}')] })
  const { bytes: out } = await fill(bytes, { values: { '사진-1': 'a.png', '사진-2': 'a.png' } }, { baseDir: dir })
  const { zip } = await readHwpx(out)
  assert.equal(Object.values(zip.files).filter((f) => !f.dir && f.name.startsWith('BinData/')).length, 1)
})

test('EXIF 6 사진은 90도 회전 속성', async () => {
  const dir = workdir()
  writeFileSync(join(dir, 'v.jpg'), makeJpeg(400, 300, 6))
  const bytes = await makeHwpx({ sections: [cellTable('{{사진}}')] })
  const { bytes: out, report } = await fill(bytes, { values: { 사진: 'v.jpg' } }, { baseDir: dir })
  assert.match(await section0(out), /<hp:rotationInfo angle="90"/)
  assert.equal(report.images[0].angle, 90)
})

test('상대 경로는 값 파일 기준(baseDir)', async () => {
  const dir = workdir()
  writeFileSync(join(dir, 'a.png'), makePng(10, 10))
  const bytes = await makeHwpx({ sections: [cellTable('{{사진}}')] })
  await assert.rejects(fill(bytes, { values: { 사진: 'a.png' } }, { baseDir: tmpdir() }), /이미지 파일이 없습니다/)
  await fill(bytes, { values: { 사진: 'a.png' } }, { baseDir: dir })
})

test('이미지 키에 글자 값이면 텍스트로 채우고 경고', async () => {
  const bytes = await makeHwpx({ sections: [p('{{사진 설명}}')] })
  const { bytes: out, report } = await fill(bytes, { values: { '사진 설명': '박스 전체' } })
  assert.match(await section0(out), /<hp:t>박스 전체<\/hp:t>/)
  assert.match(report.warnings[0], /사진 설명/)
})

test('지원하지 않는 형식은 실패', async () => {
  const dir = workdir()
  writeFileSync(join(dir, 'x.png'), Buffer.from('not an image at all'))
  const bytes = await makeHwpx({ sections: [cellTable('{{사진}}')] })
  await assert.rejects(fill(bytes, { values: { 사진: 'x.png' } }, { baseDir: dir }), /지원하지 않는/)
})

test('셀 밖 문단 이미지는 본문 폭·절반 높이에 맞춘다', async () => {
  const dir = workdir()
  writeFileSync(join(dir, 'a.png'), makePng(1000, 100))
  const bytes = await makeHwpx({ sections: [p('{{이미지}}', { head: secPrRun() })] })
  const { bytes: out } = await fill(bytes, { values: { 이미지: 'a.png' } }, { baseDir: dir })
  assert.match(await section0(out), /<hp:sz width="41669" [^>]*height="4166"/)
})

test('페이지 복사 + 페이지별 사진: 객체 id 가 겹치지 않는다', async () => {
  const dir = workdir()
  writeFileSync(join(dir, 'a.png'), makePng(10, 10))
  writeFileSync(join(dir, 'b.png'), makePng(20, 10))
  const { bytes: out } = await fill(await photoTemplate(), {
    pages: [{ page: 1 }, { page: 2, values: { '사진-1': 'a.png' } }, { page: 2, values: { '사진-1': 'b.png' } }],
  }, { baseDir: dir })
  const xml = await section0(out)
  assert.equal((xml.match(/<hp:pic /g) ?? []).length, 2)
  const ids = objectIds(xml)
  assert.ok(ids.length >= 4)
  assert.equal(new Set(ids).size, ids.length)
})

test('서식에 아주 큰 기존 id 가 있어도 그림 id 가 겹치지 않는다', async () => {
  const dir = workdir()
  writeFileSync(join(dir, 'a.png'), makePng(10, 10))
  const bytes = await makeHwpx({ sections: [cellTable('{{사진}}').replace('<hp:tbl id="1000"', '<hp:tbl id="2000000000"')] })
  const { bytes: out } = await fill(bytes, { values: { 사진: 'a.png' } }, { baseDir: dir })
  const ids = objectIds(await section0(out))
  assert.equal(new Set(ids).size, ids.length)
})
