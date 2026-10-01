# doc-template

저장된 문서 양식에 값을 채워 문서를 만들어 주는 플러그인이다. v0.1.0 은 한글 양식용 `hwpx` 스킬과 사진 분석·방문 기록용 `manage` 스킬을 제공한다.
`{{필드}}` 자리와 사진 자리에 값·사진을 채워 hwpx 와 PDF 를 만들고, 원본 페이지를 골라 반복할 수 있다(사진대지 등).

## 설치

마켓플레이스 등록 후:

```
/plugin install doc-template@anjsolution          # Claude Code
codex plugin add doc-template@anjsolution         # Codex
```

설치 후에는 "이 양식에 값 채워줘", "사진대지 만들어줘" 처럼 평소대로 요청하면 된다.

## 요구사항

- Node 18 이상
- 첫 실행 때 의존성을 자동 설치한다(인터넷 필요, 1회).
- PDF 출력은 Edge 또는 Chrome 이 필요하다(`CHROME_PATH` 로 지정 가능). hwpx 만 만들 때는 필요 없다.

## 명령 요약

```bash
node skills/hwpx/scripts/hwpx.mjs scan   <서식.hwpx>                 # 토큰 목록
node skills/hwpx/scripts/hwpx.mjs pages  <서식.hwpx>                 # 페이지별 토큰
node skills/hwpx/scripts/hwpx.mjs fill   <서식.hwpx> <값.json> -o <결과.hwpx>
node skills/hwpx/scripts/hwpx.mjs export <서식.hwpx> <값.json> -o <결과.pdf> [--hwpx <결과.hwpx>]
```

값 JSON 형식과 작업 순서는 `skills/hwpx/SKILL.md`, 규칙 상세는 `skills/hwpx/references/` 에 있다.

## manage 스킬 — 사진 메타데이터 분석

사진 폴더·파일의 촬영 날짜·위치·크기·용량을 한 번에 뽑는다(읽기 전용, 설치할 것 없음). "사진 촬영 날짜 확인해줘" 처럼 요청하면 된다.

```bash
node skills/manage/scripts/analyze-image.mjs <사진 폴더|파일> ... [--list <목록.txt>] [--recursive|-r] [--json]
```

- 없는 정보는 "없음"으로만 표시한다(파일명·수정 시각으로 추측하지 않는다). 카카오톡으로 받은 사진은 날짜·위치가 지워져 있는 경우가 많다.
- 위치(GPS)는 민감 정보라 사용자가 요청하지 않으면 문서에 넣지 않는다.
- 절차와 결과 해석은 `skills/manage/references/analyze_image.md`.

### 현장 사진 방문 기록 (임시 위치)

TTMS 구축 현장 사진의 GPS·촬영 시각으로 "언제 어디에 다녀왔는지" 방문 목록을 만들고, 방문마다 장소를 물어 확인한다("어디 다녀왔는지 사진으로 정리해줘"). 주소 변환(카카오·VWorld)은 선택이며 사용자 동의 후에만 쓴다. TTMS 구축 전용 플러그인으로 이전 예정이라 `ttms_construction_project/` 폴더로 모아 두었다.

```bash
node skills/manage/scripts/ttms_construction_project/photo-visits.mjs <사진 폴더|파일> ... [-r] [--gap-min 60] [--radius-m 500] [--geocode kakao|vworld] [--json]
```

- 절차는 `skills/manage/references/ttms_construction_project/ttms_photo_doc_location_data.md`.

**현장 사진으로 사진대지 만들기** (`references/ttms_construction_project/ttms_photo_doc_make.md`): 사진 분석 → 방문(시간대·위치)별 묶기 → 설명 달기 → hwpx 사진대지 채우기. 관리동 등록·위치 검토·좌표 채우기는 제공 예정.

## 서식 작성 방법 요약

- 한글에서 `{{필드명}}` 을 **한 번에 이어서** 타이핑한다(중간에 서식을 바꾸면 토큰이 쪼개진다).
- 사진 자리는 키 이름에 `사진` 또는 `이미지` 를 넣고, 그 문단을 가운데 정렬해 두면 사진이 가운데에 놓인다.
- 반복할 페이지는 쪽 나눔으로 나눈다.
- 편집 후 `scan` 으로 쪼개진 토큰이 없는지 확인한다.

## 하지 않는 것

원본 양식 수정, 사진 압축, 화면 미리보기, 표 행 단위 반복은 이번 버전에 없다.
이미지 압축과 템플릿 관리(찾기·가져오기·값 기억)는 이후 `manage` 스킬에 더해진다.

## 라이선스 고지

- 한글 문서 처리·PDF 렌더에 외부 패키지 [kordoc](https://github.com/chrisryugj/kordoc)(MIT, chrisryugj/kordoc, 버전 4.13.1 고정)을 사용한다. kordoc 은 일부 Apache-2.0 파생 코드를 포함한다. 번들해서 배포할 때는 해당 `LICENSE`·`NOTICE` 를 함께 넣어야 한다.
- 토큰 규칙과 일부 처리 로직은 사내 `hwpx-editor` 에서 이식했다.
- 그 밖에 jszip, @xmldom/xmldom, puppeteer-core 를 사용한다.
