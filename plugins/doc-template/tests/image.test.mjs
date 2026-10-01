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
  // 한글 실측(Task 8): curSz 는 회전 전 그림 크기, sz 는 회전 후 차지하는 크기여야 똑바로 셀 안에 놓인다.
  // sz 를 회전 전 크기로 두면 한글에서 그림이 왼쪽으로 밀려 잘리고, kordoc 은 회전을 무시하고 sz 상자에 그린다.
  assert.match(xml, /<hp:curSz width="2000" height="1500"\/>/)
  assert.match(xml, /<hp:sz width="1500" [^>]*height="2000"/)
  assert.match(xml, /binaryItemIDRef="image1"/)
  assert.match(xml, /treatAsChar="1"/)
})

test('손상된 EXIF 블록은 던지지 않고 방향 1 로 처리', () => {
  const sof = Buffer.alloc(17)
  sof.writeUInt16BE(17, 0); sof[2] = 8; sof.writeUInt16BE(300, 3); sof.writeUInt16BE(400, 5); sof[7] = 3
  const jpegWith = (tiff) => {
    const body = Buffer.concat([Buffer.from('Exif\0\0', 'binary'), tiff])
    const len = Buffer.alloc(2); len.writeUInt16BE(body.length + 2)
    return Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe1]), len, body, Buffer.from([0xff, 0xc0]), sof, Buffer.from([0xff, 0xd9])])
  }
  // IFD 오프셋이 블록 밖
  const badOffset = Buffer.alloc(8); badOffset.write('MM', 0); badOffset.writeUInt16BE(42, 2); badOffset.writeUInt32BE(0xfffffff0, 4)
  assert.deepEqual(readImageInfo(jpegWith(badOffset)), { type: 'jpg', width: 400, height: 300, orientation: 1 })
  // 항목 수만 크고 내용이 잘림
  const trunc = Buffer.alloc(10); trunc.write('MM', 0); trunc.writeUInt16BE(42, 2); trunc.writeUInt32BE(8, 4); trunc.writeUInt16BE(500, 8)
  assert.equal(readImageInfo(jpegWith(trunc)).orientation, 1)
  // 너무 짧은 블록
  assert.equal(readImageInfo(jpegWith(Buffer.from('MM'))).orientation, 1)
})

test('가로·세로가 0 이하이면 거부', () => {
  assert.throws(() => readImageInfo(makePng(0, 10)), /지원하지 않는/)
  assert.throws(() => readImageInfo(makeJpeg(400, 0)), /지원하지 않는/)
  const gif = Buffer.from('GIF89a\0\0\x05\0', 'binary')
  assert.throws(() => readImageInfo(gif), /지원하지 않는/)
})

// 한글은 rotMatrix 의 이동 성분까지 써서 그린다 (Task 8 실측). 회전 전 그림의 중심을 sz 상자의 중심으로
// 옮기는 행렬이어야 90°·180°·270° 모두 셀 안 제자리에 놓인다. 이동 성분이 0 이면 원점 기준 회전이라
// 180° 와 세로 저장 + 90° 사진이 셀 밖으로 밀려났다.
test('회전 행렬은 회전 전 그림 중심을 sz 상자 중심으로 옮긴다', () => {
  const rot = (angle, dispW, dispH) => {
    const xml = buildPicXml({ id: 1, instid: 2, binId: 'image1', pxW: 400, pxH: 300, dispW, dispH, angle })
    return /<hc:rotMatrix e1="([-\d.]+)" e2="([-\d.]+)" e3="([-\d.]+)" e4="([-\d.]+)" e5="([-\d.]+)" e6="([-\d.]+)"\/>/.exec(xml).slice(1).map(Number)
  }
  // 회전 전 2000x1500 (중심 1000,750) -> 90° 후 sz 1500x2000 (중심 750,1000)
  assert.deepEqual(rot(90, 1500, 2000), [0, -1, 1500, 1, 0, 0])
  assert.deepEqual(rot(270, 1500, 2000), [0, 1, 0, -1, 0, 2000])
  assert.deepEqual(rot(180, 2000, 1500), [-1, 0, 2000, 0, -1, 1500])
  assert.deepEqual(rot(0, 2000, 1500), [1, 0, 0, 0, 1, 0])
})
