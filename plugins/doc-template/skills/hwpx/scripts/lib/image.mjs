export const HWP_PER_MM = 7200 / 25.4
export const HWP_PER_PX = 75            // 96dpi 기준
export const MEDIA = { jpg: 'image/jpeg', png: 'image/png', gif: 'image/gif', bmp: 'image/bmp' }

function jpegInfo(b) {
  let orientation = 1
  let i = 2
  while (i + 4 <= b.length) {
    if (b[i] !== 0xff) { i++; continue }
    const marker = b[i + 1]
    if (marker === 0xd8 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) { i += 2; continue }
    if (marker === 0xd9) break
    const len = b.readUInt16BE(i + 2)
    if (marker === 0xe1 && b.toString('binary', i + 4, i + 10) === 'Exif\0\0') {
      orientation = exifOrientation(b.subarray(i + 10, i + 2 + len)) ?? orientation
    }
    if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker)) {
      return { type: 'jpg', width: b.readUInt16BE(i + 7), height: b.readUInt16BE(i + 5), orientation }
    }
    i += 2 + len
  }
  throw new Error('지원하지 않는 이미지 형식입니다 (JPEG 크기를 읽지 못함).')
}

function exifOrientation(t) {
  const le = t.toString('binary', 0, 2) === 'II'
  const u16 = (o) => (le ? t.readUInt16LE(o) : t.readUInt16BE(o))
  const u32 = (o) => (le ? t.readUInt32LE(o) : t.readUInt32BE(o))
  const ifd = u32(4)
  const n = u16(ifd)
  for (let k = 0; k < n; k++) {
    const e = ifd + 2 + k * 12
    if (u16(e) === 0x0112) return u16(e + 8)
  }
  return null
}

export function readImageInfo(b) {
  if (b.length >= 24 && b.readUInt32BE(0) === 0x89504e47)
    return { type: 'png', width: b.readUInt32BE(16), height: b.readUInt32BE(20), orientation: 1 }
  if (b.length >= 4 && b[0] === 0xff && b[1] === 0xd8) return jpegInfo(b)
  if (b.length >= 10 && b.toString('ascii', 0, 3) === 'GIF')
    return { type: 'gif', width: b.readUInt16LE(6), height: b.readUInt16LE(8), orientation: 1 }
  if (b.length >= 26 && b.toString('ascii', 0, 2) === 'BM')
    return { type: 'bmp', width: b.readInt32LE(18), height: Math.abs(b.readInt32LE(22)), orientation: 1 }
  throw new Error('지원하지 않는 이미지 형식입니다 (jpg·png·gif·bmp 만 가능).')
}

const ORIENT = {
  1: [0, false, false], 2: [0, false, true], 3: [180, false, false], 4: [180, false, true],
  5: [90, true, true], 6: [90, true, false], 7: [270, true, true], 8: [270, true, false],
}
export function orientationInfo(o) {
  const [angle, swap, mirrored] = ORIENT[o] ?? ORIENT[1]
  return { angle, swap, mirrored }
}

export function fitBox({ boxW, boxH, imgW, imgH, maxW, maxH }) {
  const W = Math.min(boxW, maxW ?? Infinity)
  const H = Math.min(boxH, maxH ?? Infinity)
  const s = Math.min(W / imgW, H / imgH)
  return { w: Math.floor(imgW * s), h: Math.floor(imgH * s) }
}

export function buildPicXml({ id, instid, binId, pxW, pxH, dispW, dispH, angle }) {
  const swap = angle === 90 || angle === 270
  const w = swap ? dispH : dispW         // 회전 전 그림 크기
  const h = swap ? dispW : dispH
  const orgW = pxW * HWP_PER_PX
  const orgH = pxH * HWP_PER_PX
  const rad = (angle * Math.PI) / 180
  const cos = Math.round(Math.cos(rad) * 1e6) / 1e6
  const sin = Math.round(Math.sin(rad) * 1e6) / 1e6
  return (
    `<hp:pic id="${id}" zOrder="0" numberingType="PICTURE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" href="" groupLevel="0" instid="${instid}" reverse="0">` +
    `<hp:offset x="0" y="0"/><hp:orgSz width="${orgW}" height="${orgH}"/><hp:curSz width="${w}" height="${h}"/>` +
    '<hp:flip horizontal="0" vertical="0"/>' +
    `<hp:rotationInfo angle="${angle}" centerX="${Math.floor(w / 2)}" centerY="${Math.floor(h / 2)}" rotateimage="1"/>` +
    '<hp:renderingInfo><hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>' +
    `<hc:scaMatrix e1="${w / orgW}" e2="0" e3="0" e4="0" e5="${h / orgH}" e6="0"/>` +
    `<hc:rotMatrix e1="${cos}" e2="${-sin}" e3="0" e4="${sin}" e5="${cos}" e6="0"/></hp:renderingInfo>` +
    `<hc:img binaryItemIDRef="${binId}" bright="0" contrast="0" effect="REAL_PIC" alpha="0"/>` +
    `<hp:imgRect><hc:pt0 x="0" y="0"/><hc:pt1 x="${orgW}" y="0"/><hc:pt2 x="${orgW}" y="${orgH}"/><hc:pt3 x="0" y="${orgH}"/></hp:imgRect>` +
    `<hp:imgClip left="0" right="${orgW}" top="0" bottom="${orgH}"/>` +
    '<hp:inMargin left="0" right="0" top="0" bottom="0"/>' +
    `<hp:imgDim dimwidth="${orgW}" dimheight="${orgH}"/><hp:effects/>` +
    `<hp:sz width="${w}" widthRelTo="ABSOLUTE" height="${h}" heightRelTo="ABSOLUTE" protect="0"/>` +
    '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>' +
    '<hp:outMargin left="0" right="0" top="0" bottom="0"/></hp:pic>'
  )
}
