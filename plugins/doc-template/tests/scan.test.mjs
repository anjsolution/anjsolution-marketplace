import { test } from 'node:test'
import assert from 'node:assert/strict'
import { isImageKey, isImagePath } from '../skills/hwpx/scripts/lib/tokens.mjs'
import { scan } from '../skills/hwpx/scripts/lib/scan.mjs'
import { makeHwpx, p } from './helpers/make-hwpx.mjs'

test('이미지 키 판별', () => {
  assert.ok(isImageKey('사진-1'))
  assert.ok(isImageKey('직인 이미지'))
  assert.ok(!isImageKey('공사명'))
})

test('이미지 경로 판별', () => {
  assert.ok(isImagePath('a/b.JPG'))
  assert.ok(isImagePath({ path: 'x.png' }))
  assert.ok(!isImagePath('박스 전체'))
  assert.ok(!isImagePath(''))
})

test('scan 은 필드·횟수·이미지 여부를 준다', async () => {
  const bytes = await makeHwpx({ sections: [p('{{공사명}} / {{ 공사명 }}') + p('{{사진-1}}')] })
  const r = await scan(bytes)
  assert.deepEqual(r.fields, [
    { name: '공사명', count: 2, image: false },
    { name: '사진-1', count: 1, image: true },
  ])
  assert.deepEqual(r.broken, [])
})

test('쪼개진 토큰은 broken 으로 보고', async () => {
  const bytes = await makeHwpx({ sections: [p('{{공사')] })
  assert.deepEqual((await scan(bytes)).broken, ['{{공사'])
})

test('XML 이스케이프된 키를 되돌린다', async () => {
  const bytes = await makeHwpx({ sections: [p('{{A&amp;B}}')] })
  assert.equal((await scan(bytes)).fields[0].name, 'A&B')
})
