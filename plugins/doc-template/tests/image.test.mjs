import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readImageInfo, orientationInfo, fitBox, buildPicXml } from '../skills/hwpx/scripts/lib/image.mjs'
import { makePng, makeJpeg } from './helpers/make-hwpx.mjs'

test('PNG 크기', () => {
  assert.deepEqual(readImageInfo(makePng(30, 20)), { type: 'png', width: 30, height: 20, orientation: 1 })
})

test('JPEG 크기와 EXIF 방향', () => {
  assert.deepEqual(readImageInfo(makeJpeg(400, 300, 6)), { type: 'jpg', width: 400, height: 300, orientation: 6 })
  assert.equal(readImageInfo(makeJpeg(400, 300)).orientation, 1)
})

test('모르는 형식은 실패', () => {
  assert.throws(() => readImageInfo(Buffer.from('hello world!')), /지원하지 않는/)
})

test('방향 값 해석', () => {
  assert.deepEqual(orientationInfo(1), { angle: 0, swap: false, mirrored: false })
  assert.deepEqual(orientationInfo(6), { angle: 90, swap: true, mirrored: false })
  assert.deepEqual(orientationInfo(8), { angle: 270, swap: true, mirrored: false })
  assert.deepEqual(orientationInfo(3), { angle: 180, swap: false, mirrored: false })
  assert.equal(orientationInfo(5).mirrored, true)
})

test('비율 유지 최대 크기', () => {
  assert.deepEqual(fitBox({ boxW: 1000, boxH: 1000, imgW: 400, imgH: 200 }), { w: 1000, h: 500 })
  assert.deepEqual(fitBox({ boxW: 1000, boxH: 300, imgW: 400, imgH: 200 }), { w: 600, h: 300 })
  assert.deepEqual(fitBox({ boxW: 1000, boxH: 1000, imgW: 400, imgH: 200, maxW: 500 }), { w: 500, h: 250 })
})

test('EXIF 6 은 90° + 가로세로 바꿔 맞춤', () => {
  const info = readImageInfo(makeJpeg(400, 300, 6))
  const o = orientationInfo(info.orientation)
  const [w, h] = o.swap ? [info.height, info.width] : [info.width, info.height]
  const box = fitBox({ boxW: 3000, boxH: 2000, imgW: w, imgH: h })   // 세로 사진 300x400
  assert.deepEqual(box, { w: 1500, h: 2000 })
  const xml = buildPicXml({ id: 9, instid: 10, binId: 'image1', pxW: 400, pxH: 300, dispW: box.w, dispH: box.h, angle: o.angle })
  assert.match(xml, /<hp:rotationInfo angle="90"/)
  assert.match(xml, /<hp:sz width="2000" [^>]*height="1500"/)   // 회전 전 그림 크기 = 표시 크기의 가로세로 바꿈
  assert.match(xml, /binaryItemIDRef="image1"/)
  assert.match(xml, /treatAsChar="1"/)
})
