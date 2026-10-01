# XML 직접 편집

스크립트가 처리하지 못하는 서식(쪼개진 토큰, 쪽 나눔이 애매한 페이지, 구역이 여러 개, 특이한 그림 배치)을 고칠 때 쓴다.

## 절차
1. 서식을 **작업 폴더에 복사**해 압축을 푼다. 원본 서식은 수정하지 않는다.
2. `Contents/section*.xml` 을 고친다(토큰 run 합치기, 쪽 나눔 삽입 등).
3. 다시 묶을 때 `mimetype` 을 **첫 항목·무압축(STORE)** 으로 둔다. 아니면 한글이 파일을 거부한다.
4. `scan` 으로 다시 검사해 `broken` 이 비었는지, 기대한 토큰이 모두 잡히는지 확인한 뒤 `fill` 을 진행한다. 쪽 나눔을 고쳤다면 `pages` 도 확인한다.
5. 고친 서식을 사용자에게 알린다. 계속 쓸 서식이면 원본을 바꿀지는 사용자가 정한다.

## 구조 요점
- 본문은 `Contents/sectionN.xml`. 최상위 문단은 `hp:p`.
- 쪽 나눔은 최상위 `hp:p` 의 `pageBreak="1"` 속성이다. 이 문단부터 새 페이지가 시작된다. 표 안 문단의 `pageBreak` 는 페이지 경계로 쓰이지 않는다.
- 글자는 `hp:p` > `hp:run` > `hp:t`. 토큰이 쪼개졌다면 `{{`, 필드명, `}}` 가 서로 다른 `hp:run`/`hp:t` 에 나뉘어 있다. 첫 `hp:t` 에 합치고 나머지 run 은 비운다(서식 속성은 첫 run 것을 쓴다).
- 표는 `hp:tbl` > `hp:tr` > `hp:tc`. 셀 크기는 `hp:cellSz`, 셀 여백은 `hp:cellMargin`(셀이 `hasMargin="0"` 이면 표의 `hp:inMargin`).
- 구역 정의 `secPr`(용지·여백)은 **첫 문단**에 들어 있다. 쪽 나눔을 넣거나 문단을 옮길 때 지우거나 다른 문단으로 옮기지 않는다.
- 조판 캐시 `hp:linesegarray` 는 글자를 바꾼 문단에서는 지운다.
- 그림 등록은 `BinData/` 파일 + `Contents/content.hpf` 의 `opf:item`.

## 다시 묶기 (Node 한 줄)
스크립트 폴더(`skills/hwpx/scripts`)의 `lib/package.mjs` 가 `mimetype` 을 첫 항목·STORE 로 두고 묶는다.
고친 section 파일을 복사본 서식 zip 에 반영한 뒤 `writeHwpx` 로 저장한다.

```bash
node --input-type=module -e "
import fs from 'node:fs'
const { readHwpx, writeHwpx } = await import('file:///<스크립트 폴더>/lib/package.mjs')
const { zip } = await readHwpx(fs.readFileSync('<서식 복사본>.hwpx'))
zip.file('Contents/section0.xml', fs.readFileSync('<고친 section0.xml>', 'utf8'))
fs.writeFileSync('<고친 서식>.hwpx', await writeHwpx(zip))
"
```

`<스크립트 폴더>` 는 `hwpx.mjs` 가 있는 폴더의 절대 경로다(Windows 는 `C:/...` 형태). 의존성이 설치된 뒤(첫 실행 후)에 쓴다.
