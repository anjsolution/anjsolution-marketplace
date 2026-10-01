// hwpx-editor docs/기능-명세.md §1 과 같은 규칙
export const TOKEN = /\{\{\s*([^{}\s][^{}]*?)\s*\}\}/g
export const tokenRe = () => new RegExp(TOKEN.source, 'g')

export const isImageKey = (name) => /사진|이미지/.test(name)

const IMAGE_EXT = /\.(jpe?g|png|bmp|gif)$/i
export function isImagePath(value) {
  const path = value && typeof value === 'object' ? value.path : value
  return typeof path === 'string' && IMAGE_EXT.test(path.trim())
}

export const unescapeXml = (s) =>
  s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, '&')
