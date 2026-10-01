import { test } from 'node:test'
import assert from 'node:assert/strict'
import JSZip from '../skills/hwpx/scripts/node_modules/jszip/lib/index.js'
import { readHwpx, readText, writeHwpx, addBinItem, listManifestIds } from '../skills/hwpx/scripts/lib/package.mjs'
import { parseXml, serializeXml, children, descendants, closest } from '../skills/hwpx/scripts/lib/dom.mjs'
import { makeHwpx, p } from './helpers/make-hwpx.mjs'

test('readHwpx 는 구역 이름을 순서대로 준다', async () => {
  const { sectionNames } = await readHwpx(await makeHwpx({ sections: [p('a'), p('b')] }))
  assert.deepEqual(sectionNames, ['Contents/section0.xml', 'Contents/section1.xml'])
})

test('구역이 없으면 실패', async () => {
  const zip = new JSZip(); zip.file('mimetype', 'application/hwp+zip')
  await assert.rejects(readHwpx(await zip.generateAsync({ type: 'nodebuffer' })), /sectionN/)
})

test('writeHwpx 는 mimetype 을 첫 항목·무압축으로 쓴다', async () => {
  const { zip } = await readHwpx(await makeHwpx({ sections: [p('a')] }))
  zip.file('BinData/x.png', Buffer.from([1]))
  const out = await writeHwpx(zip)
  assert.equal(out.subarray(30, 38).toString(), 'mimetype')   // 첫 로컬 헤더의 파일명
  assert.equal(out.readUInt16LE(8), 0)                        // 압축 방식 0 = STORE
})

test('addBinItem 은 매니페스트에 항목을 추가한다', async () => {
  const { zip } = await readHwpx(await makeHwpx({ sections: [p('a')] }))
  await addBinItem(zip, { id: 'image1', href: 'BinData/image1.png', mediaType: 'image/png' })
  assert.ok((await listManifestIds(zip)).includes('image1'))
  assert.match(await readText(zip, 'Contents/content.hpf'), /href="BinData\/image1.png"[^>]*isEmbeded="1"/)
})

test('dom 도우미', () => {
  const doc = parseXml('<hs:sec xmlns:hs="S" xmlns:hp="P"><hp:p><hp:run><hp:t>x</hp:t></hp:run></hp:p></hs:sec>')
  const [para] = children(doc.documentElement, 'p')
  const [t] = descendants(para, 't')
  assert.equal(closest(t, 'p'), para)
  assert.match(serializeXml(doc), /<hp:t>x<\/hp:t>/)
})
