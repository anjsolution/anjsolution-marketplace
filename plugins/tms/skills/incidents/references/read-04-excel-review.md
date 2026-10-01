# 장애 history 엑셀 행 점검 (원본 추출 → 매핑 → 판정)

지정한 엑셀 행을 등록 입력으로 바꿔 보면서, 원문이 어떻게 해석됐는지와 이상한 데이터를 찾는다.
이 문서는 읽기 작업이다. 점검만 요청받았다면 등록하지 않고 보고로 끝낸다.
등록까지 요청받았다면 이 점검을 마친 뒤 [엑셀 행 등록](write-04-excel-register.md)으로 넘어간다.

## 스크립트

incidents 스킬 폴더 기준 `python scripts/<이름>.py`로 실행한다. Python 3와 openpyxl이 필요하다.
작업 파일은 `~/.anjsolution/tms/excel-work/<날짜>/`처럼 플러그인·Git 폴더 밖에 둔다(장애 내용 포함).

| 단계 | 스크립트 | 입력 → 출력 |
|---|---|---|
| 1. 원본 추출 | `history_extract.py <엑셀> <접수번호…>` | 엑셀 → `source.json` (셀 값 그대로, 일시만 KST) |
| 2. 매핑 | `history_map.py source.json [--catalog <캐시>]` | 원본 → `drafts.json` (등록 초안 + 판정 기록) |

- 매핑에는 catalog 스킬의 카탈로그 캐시(`~/.anjsolution/tms/catalog.json`)가 필요하다. 세션에서 처음이면
  `get_catalog_version`으로 버전을 대조하고, 다르거나 `시스템분류`가 없으면 `get_catalog`로 교체한다.
- 원본(`source.json`)은 고치지 않는다. 엑셀 셀을 고쳤다면 1단계부터 다시 한다.

## 판정 기록 읽기

초안마다 `decisions`에 원문에서 바뀐 내용이 규칙 이름과 수준으로 남는다. 정확 일치는 기록하지 않는다.

| 수준 | 뜻 | 초안 칸 | 에이전트가 할 일 |
|---|---|---|---|
| `rule` | 정해진 규칙으로 바뀜(별칭·범위 전개 등) | — | 요약에 규칙별 건수만 적는다 |
| `check` | 등록은 가능하나 판단 필요 | `checks` | 원문·장애 내용과 대조해 판단하고 근거를 보고한다 |
| `fail` | 이 상태로는 등록 불가 | `blockers` | 사유와 후보를 보고하고 사용자 결정을 받는다 |

`drafts.json`의 `summary.byRule`은 규칙별로 접수번호를 묶는다. 같은 규칙은 한꺼번에 검토한다.
`ready`는 `blockers`와 `checks`가 모두 없는 건이다.

## check 판단 기준

판단 근거는 원문(`sourceText`), O열 장애 내용(`incident.memo`), 대응 경과다. 장애 내용에 적힌
지사·터널명이 가장 강한 근거다. 근거가 부족하면 사용자에게 묻는다.

| 규칙 | 확인할 것 |
|---|---|
| `tunnel.narrowed_by_context` | 같은 칸의 다른 터널이나 장애 내용의 지사로 동명 터널을 골랐다. 장애 내용과 맞는지 |
| `tunnel.substring_unique` | 이름 일부만 일치하는 후보가 하나뿐이라 채웠다(예: '호남대'→어등산 호남대). 같은 터널인지 |
| `tunnel.name_hyphen` | '슬치-오도재'를 두 터널로 봤다. 구간 표기라 사이 터널까지 포함해야 하는지 |
| `division.in_list` | 터널 목록 속 본부명을 본부 전체 대상으로 봤다. 정말 본부 전체 장애인지 |
| `branch.partial_text` / `division.partial_text` | 지사·본부 뒤 글자를 해석하지 못하고 전체로 매핑했다. 특정 터널로 좁힐 수 있는지 |
| `all_divisions` | '전체 터널'을 모든 본부로 매핑했다 |
| `system.division_not_division` | F열이 본부가 아니라 시스템명이라 전체 본부로 매핑했다 |
| `division.mismatch` | F열 본부와 터널의 현재 소속이 다르다. `summary.divisionMismatch`의 조합별로 조직 개편인지 사용자에게 한 번씩 묻고, 개편이면 해당 건을 함께 판단 완료로 둔다. 조직 사실은 추측하지 않는다 |
| `memo.branch_mismatch` | 장애 내용의 지사와 매핑된 지사가 다르다. G열 입력 오류일 가능성이 높다 |
| `incident_code.multiple` | D열에 코드가 여러 개라 첫 코드로 분류했다 |
| `time.*` | 복구가 접수보다 이르거나, 30일 넘게 걸렸거나, 대응 일시가 범위를 벗어났다. 날짜 오타인지 |
| `progress.year_rollover` | 연초 접수건의 12월 경과를 전년으로 해석했다 |
| `status.*` | B열 처리 상태와 조치 정보가 맞지 않는다. 조치를 등록할지 |

`fail` 중 `tunnel.not_found`·`tunnel.ambiguous`는 메시지의 후보를 사용자에게 보여 준다. 후보가 하나뿐이어도
fail이면 스스로 고르지 않는다. `tunnel.partial`은 확정된 일부 대상을 `to`에 남긴다.

## 보고

1. 요약: 전체·ready·판단 필요·등록 불가 건수, 규칙별 건수(`summary.byRule`).
2. 판단 필요: 건마다 판단 결과와 근거. 같은 규칙·같은 결론은 묶는다.
3. 등록 불가: 건마다 사유와 후보, 필요한 사용자 결정.
4. 이상 데이터: `memo.branch_mismatch`·`time.*`처럼 엑셀 입력 오류로 보이는 건은 따로 모아 알린다.
