# ttms_construction_project — TTMS 구축 전용 기능 (임시 위치)

이 폴더와 `scripts/ttms_construction_project/`, `templates/ttms_construction_project/` 는 **TTMS 구축 업무에만 쓰는 기능**을 모아 둔 곳이다.
TTMS 구축 전용 플러그인이 생기면 **두 폴더를 통째로 그쪽으로 옮길 후보**이며, 그때까지 doc-template 의 manage 스킬 안에서 먼저 만들어 쓴다.

범용 기능(사진 메타데이터 분석 `analyze_image`, 양식 채우기 `hwpx` 스킬)은 이 폴더에 두지 않는다. 여기 문서는 그 범용 기능을 TTMS 구축 업무 순서에 맞게 엮는다.

## 들어 있는 것

자료 종류별로 묶는다. 새 종류가 생기면 `### 3-2.` 처럼 항목을 추가하고 문서 이름에 그 종류의 접두어를 붙인다(예: 사진대지는 `ttms_photo_doc_`). 번호는 manage `SKILL.md` 의 3장 번호와 맞춘다.

### 3-1. 서버 입고(공장 검수)·서버 납품 사진대지 — `ttms_photo_doc_*`

| 문서 | 하는 일 | 스크립트 |
|---|---|---|
| `ttms_photo_doc_location_data.md` | 현장 사진의 GPS·촬영 시각으로 방문(언제 어디에) 목록을 만들고 장소를 확인받는다 | `scripts/ttms_construction_project/photo-visits.mjs` |
| `ttms_photo_doc_types.md` | 사진대지 종류(서버 입고·납품)별 장소, 필수 사진, 촬영 순서 — 업무 지식 | — |
| `ttms_photo_doc_make.md` | 현장 사진으로 사진대지(입고·납품·설치 등)를 만든다. 사진 분석 → 묶기·설명 → hwpx 채우기, 설치 장소 위치 정보 정리(예정) | — (기존 스크립트 조합) |

템플릿: `templates/ttms_construction_project/server_receiving_photo_sheet*.hwpx`, `server_delivery_photo_sheet*.hwpx`

## 옮길 때 체크리스트

1. `references/`·`scripts/`·`templates/` 아래 `ttms_construction_project/` 세 폴더를 새 플러그인의 같은 자리로 옮긴다.
2. `photo-visits.mjs` 가 import 하는 `scripts/analyze-image.mjs` 를 함께 복사한다(플러그인끼리 파일을 참조하지 않는다).
3. 이 폴더 문서의 실행 경로(`${CLAUDE_PLUGIN_ROOT}/skills/manage/...`)를 새 위치로 바꾼다.
4. 사진대지 채우기는 계속 doc-template 의 `hwpx` 스킬을 호출한다(양식 채우기는 범용 기능으로 남는다).
5. doc-template `manage/SKILL.md` 의 목록·트리거에서 이 폴더 항목을 뺀다.
