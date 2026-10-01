import JSZip from '../../skills/hwpx/scripts/node_modules/jszip/lib/index.js'
import { deflateSync } from 'node:zlib'

const NS_ATTRS =
  'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" ' +
  'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" ' +
  'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"'

let pid = 0
export const secPrRun = () =>
  '<hp:run charPrIDRef="0"><hp:secPr id="" textDirection="HORIZONTAL">' +
  '<hp:pagePr landscape="WIDELY" width="59528" height="84188" gutterType="LEFT_ONLY">' +
  '<hp:margin header="4252" footer="4252" gutter="0" left="8504" right="8504" top="5668" bottom="4252"/>' +
  '</hp:pagePr></hp:secPr><hp:ctrl><hp:colPr id="" type="NEWSPAPER" layout="LEFT" colCount="1" sameSz="1" sameGap="0"/></hp:ctrl></hp:run>'

export const p = (text, { pageBreak = 0, head = '' } = {}) =>
  `<hp:p id="${pid++}" paraPrIDRef="0" styleIDRef="0" pageBreak="${pageBreak}" columnBreak="0" merged="0">` +
  head +
  `<hp:run charPrIDRef="0"><hp:t>${text}</hp:t></hp:run>` +
  '<hp:linesegarray><hp:lineseg textpos="0" vertpos="0" vertsize="1000" textheight="1000" baseline="850" spacing="600" horzpos="0" horzsize="42520" flags="393216"/></hp:linesegarray>' +
  '</hp:p>'

let tid = 1000
export const cellTable = (text, { width = 40000, height = 20000, margin = 500, hasMargin = 1, pageBreak = 0 } = {}) =>
  `<hp:p id="${pid++}" paraPrIDRef="0" styleIDRef="0" pageBreak="${pageBreak}" columnBreak="0" merged="0"><hp:run charPrIDRef="0">` +
  `<hp:tbl id="${tid++}" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="0" rowCnt="1" colCnt="1" cellSpacing="0" borderFillIDRef="1" noAdjust="0">` +
  `<hp:sz width="${width}" widthRelTo="ABSOLUTE" height="${height}" heightRelTo="ABSOLUTE" protect="0"/>` +
  '<hp:inMargin left="510" right="510" top="141" bottom="141"/>' +
  `<hp:tr><hp:tc name="" header="0" hasMargin="${hasMargin}" protect="0" editable="0" dirty="0" borderFillIDRef="1">` +
  '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER">' +
  `<hp:p id="${pid++}" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="0"><hp:t>${text}</hp:t></hp:run></hp:p>` +
  '</hp:subList><hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>' +
  `<hp:cellSz width="${width}" height="${height}"/>` +
  `<hp:cellMargin left="${margin}" right="${margin}" top="${margin}" bottom="${margin}"/></hp:tc></hp:tr></hp:tbl>` +
  '</hp:run></hp:p>'

export async function makeHwpx({ sections }) {
  const zip = new JSZip()
  zip.file('mimetype', 'application/hwp+zip', { compression: 'STORE' })
  zip.file('META-INF/container.xml',
    '<?xml version="1.0" encoding="UTF-8"?><ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container"><ocf:rootfiles><ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/></ocf:rootfiles></ocf:container>')
  const items = sections.map((_, i) => `<opf:item id="section${i}" href="Contents/section${i}.xml" media-type="application/xml"/>`).join('')
  zip.file('Contents/content.hpf',
    '<?xml version="1.0" encoding="UTF-8"?><opf:package xmlns:opf="http://www.idpf.org/2007/opf/"><opf:metadata/>' +
    `<opf:manifest><opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>${items}</opf:manifest>` +
    '<opf:spine><opf:itemref idref="header" linear="yes"/></opf:spine></opf:package>')
  zip.file('Contents/header.xml', '<?xml version="1.0" encoding="UTF-8"?><hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"/>')
  sections.forEach((body, i) =>
    zip.file(`Contents/section${i}.xml`, `<?xml version="1.0" encoding="UTF-8"?><hs:sec ${NS_ATTRS}>${body}</hs:sec>`))
  return zip.generateAsync({ type: 'nodebuffer', compression: 'DEFLATE' })
}

// 1x1 이상 PNG — 헤더 크기만 의미 있다
export function makePng(w, h) {
  const crcTable = Array.from({ length: 256 }, (_, n) => {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    return c >>> 0
  })
  const crc = (buf) => {
    let c = 0xffffffff
    for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8)
    return (c ^ 0xffffffff) >>> 0
  }
  const chunk = (type, data) => {
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length)
    const td = Buffer.concat([Buffer.from(type), data])
    const c = Buffer.alloc(4); c.writeUInt32BE(crc(td))
    return Buffer.concat([len, td, c])
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4)
  ihdr[8] = 8; ihdr[9] = 2
  const raw = Buffer.alloc((w * 3 + 1) * h)
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0)),
  ])
}

// 헤더만 있는 JPEG — SOI, (APP1 EXIF Orientation), SOF0, EOI
export function makeJpeg(w, h, orientation) {
  const parts = [Buffer.from([0xff, 0xd8])]
  if (orientation) {
    const tiff = Buffer.alloc(26)
    tiff.write('MM', 0); tiff.writeUInt16BE(42, 2); tiff.writeUInt32BE(8, 4)
    tiff.writeUInt16BE(1, 8)                     // 항목 1개
    tiff.writeUInt16BE(0x0112, 10); tiff.writeUInt16BE(3, 12); tiff.writeUInt32BE(1, 14)
    tiff.writeUInt16BE(orientation, 18)
    const body = Buffer.concat([Buffer.from('Exif\0\0', 'binary'), tiff])
    const len = Buffer.alloc(2); len.writeUInt16BE(body.length + 2)
    parts.push(Buffer.from([0xff, 0xe1]), len, body)
  }
  const sof = Buffer.alloc(17)
  sof.writeUInt16BE(17, 0); sof[2] = 8; sof.writeUInt16BE(h, 3); sof.writeUInt16BE(w, 5); sof[7] = 3
  parts.push(Buffer.from([0xff, 0xc0]), sof, Buffer.from([0xff, 0xd9]))
  return Buffer.concat(parts)
}
