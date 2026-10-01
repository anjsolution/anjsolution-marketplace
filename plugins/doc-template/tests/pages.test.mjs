import { test } from 'node:test'
import assert from 'node:assert/strict'
import { listPages } from '../skills/hwpx/scripts/lib/pages.mjs'
import { makeHwpx, p, cellTable, secPrRun } from './helpers/make-hwpx.mjs'

test('쪽 나눔으로 페이지를 나눈다', async () => {
  const bytes = await makeHwpx({ sections: [
    p('{{공사명}}', { head: secPrRun() }) + p('{{모델명}}') +
    cellTable('{{사진-1}}', { pageBreak: 1 }) + p('{{내용-1}}'),
  ] })
  const { pages, warnings } = await listPages(bytes)
  assert.deepEqual(pages.map((x) => [x.page, x.fields.map((f) => f.name)]), [
    [1, ['공사명', '모델명']],
    [2, ['사진-1', '내용-1']],
  ])
  assert.equal(pages[1].fields[0].image, true)
  assert.deepEqual(warnings, [])
})

test('쪽 나눔이 표 안에만 있으면 경고', async () => {
  const inner = p('{{a}}', { pageBreak: 1 })
  const bytes = await makeHwpx({ sections: [p('x') + cellTable('y').replace('<hp:t>y</hp:t>', '<hp:t>y</hp:t>') .replace('</hp:subList>', `${inner}</hp:subList>`)] })
  const { warnings } = await listPages(bytes)
  assert.match(warnings[0], /표 안/)
})

test('구역이 둘이면 구역마다 페이지 번호가 이어진다', async () => {
  const bytes = await makeHwpx({ sections: [p('{{a}}'), p('{{b}}')] })
  const { pages } = await listPages(bytes)
  assert.deepEqual(pages.map((x) => [x.page, x.section]), [[1, 0], [2, 1]])
})
