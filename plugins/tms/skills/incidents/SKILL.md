---
name: incidents
description: 사용자의 현재 요청에 TMS(대소문자 무관)를 사용하라는 지시가 있을 때만 장애 데이터를 조회·분석하거나 신규 장애·대응 기록·조치 결과를 등록하고, 장애 history 엑셀과 비교해 특이사항을 보고한다. 트리거 — "TMS 이번 달 장애 분석해줘", "tms 서버 다운 장애 등록해줘", "TMS 이 장애에 대응 기록 추가해줘", "TMS 장애 엑셀이랑 비교해줘", "TMS에 엑셀 1945~1950번 등록해줘". TMS 명시 없는 일반 장애·서버 분석, 단순 인용, TMS 사용 제외 요청에는 사용하지 않는다. TMS 터널 소속·명칭 해석은 catalog 스킬.
---

# incidents — 장애 조회·분석, 등록, 엑셀 비교

현재 연결에서 제공되는 MCP 도구 설명·입력 스키마·Server Instructions를 기준으로 호출한다.
이 스킬은 업무 진행 순서와 결과 안내를 보완한다. 필드명·enum·페이지 제한은 여기서 복제하지 않는다.

## 요청에 맞는 문서만 읽기

| 요청 | 읽을 문서 |
|---|---|
| 장애 목록·상세·대응/조치 이력 조회 | [read-01-search](references/read-01-search.md) |
| 건수·비교·원인·대응 패턴 분석 | [read-02-analysis](references/read-02-analysis.md) |
| 장애 history 엑셀과 원격 비교(미등록·중복·추가분) | [read-03-excel-compare](references/read-03-excel-compare.md) |
| 엑셀 행 점검(원본 추출·매핑·이상 데이터 판단) | [read-04-excel-review](references/read-04-excel-review.md) |
| 신규 장애 등록 | [write-01-common](references/write-01-common.md)과 [write-02-incident](references/write-02-incident.md) |
| 지정한 엑셀 행 등록 | [read-04-excel-review](references/read-04-excel-review.md), [write-01-common](references/write-01-common.md), [write-02-incident](references/write-02-incident.md), [write-04-excel-register](references/write-04-excel-register.md) |
| 기존 장애에 대응 기록·조치 결과 등록 | [write-01-common](references/write-01-common.md)과 [write-03-history](references/write-03-history.md) |
| 등록 결과 불명·재시도 | [write-01-common](references/write-01-common.md) |

읽기만 요청받았다면 쓰기 문서는 읽지 않는다. 조회·비교 결과에서 장애를 발견했다고 등록을 시작하지 않는다.
쓰기는 신규 장애 등록(`create_incident`), 대응 기록 추가(`add_incident_responses`),
최초 조치 등록(`add_incident_resolution`)만 지원한다. 기존 장애·대응·조치의 수정과 삭제는
실행 범위에 없으며 웹 화면에서 처리하도록 안내한다. 엑셀 행은 사용자가 지정한 건만 점검·판단을
거쳐 묶음 단위로 등록한다. 비교 결과만 보고 여러 건을 자동으로 일괄 등록하는 것은 보류 상태다.

## 연결과 권한

해당 작업의 도구가 현재 연결에 있는지 확인한다. 스킬 설치가 도구 실행 권한을 부여하지 않는다.
읽기는 장애 조회 권한, 등록은 `tms:incidents:write`와 OAuth 승인이 필요하다.
도구가 없으면 연결·권한 상태를 확인하고, 권한이 필요하면 Ai-Ops 요청을 안내한다.
서버 배포 뒤에도 도구나 입력 필드가 예전 그대로 보이면 클라이언트가 이전 목록을 들고 있을 수 있다.
"서버가 지원하지 않는다"고 단정하지 말고 MCP 재연결이나 새 세션을 안내한다.
401은 인증 상태, 403은 scope/현재 권한을 확인한다. 권한을 추가로 받았다면 OAuth 추가 동의가
필요하며 기존 토큰의 단순 갱신으로 승인 scope가 늘어나지는 않는다. 설치·연결은 플러그인 README를 따른다.

도구 간 식별은 공개 식별자로 한다. 신규 장애 대상은 터널코드·장치번호·본부/지사명·시스템 분류,
기존 장애는 장애코드다. 내부 숫자 ID를 만들거나 추측해 입력하지 않는다.
사용자에게는 기본적으로 내부 ID·요청 UUID를 생략하고 장애코드·명칭·내용으로 안내한다.
