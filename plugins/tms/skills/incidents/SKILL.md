---
name: incidents
description: TMS 장애 이력을 찾거나 세거나 분석할 때 쓴다. 트리거 — "OO터널 장애 이력", "이번 달 장애 몇 건", "본부별 장애 현황", "서버 교체한 장애 찾아줘", "장애 원인 분석해줘", "대응 이력 봐줘". 터널 소속·명칭 해석만 필요하면 catalog 스킬.
---

# incidents — 장애 이력 분석

## 찾고 센다
`search_incidents` 로 찾고 `incident_stats` 로 센다.
`group_by` 는 month·category·status·highway·division·branch·tunnel.
`keyword` 는 메모와 대응 내용을 검색하며, `총건수` 만 봐도 빈도를 알 수 있다.

`incident_stats` 를 쓸 때:
- 기간을 둘 다 생략하면 **전체 기간이 아니라 올해**다
- 한 장애가 여러 조직에 걸리면 그룹마다 세므로 **그룹 합계가 전체 건수보다 클 수 있다**
- `그룹: null` 은 미지정이다. 버리지 말고 "미지정" 으로 보고한다

## 그 밖의 축은 받아서 센다
조치방법·대응자·소요시간처럼 `group_by` 에 없는 축은 데이터를 받아 직접 집계한다.

1. 최소 범위로 거른다 (기간·본부·분류·키워드)
2. `include_history=true` 로 받는다 — `조치결과.방법` 은 `REBOOT` `REPAIR` `CONFIG` `REPLACE` `PATCH`
3. 그대로 세거나, 양이 많으면 JSON 파일로 저장해 센다

먼저 필터만 걸어 `총건수`·`전체페이지` 로 범위를 가늠한 뒤 정한다.

예 — "서버 교체하러 나간 장애가 어느 본부에 많나": `keyword=교체` 로 받아
`조치결과.방법` 이 `REPLACE` 인 것을 고르고, catalog 로 본부를 붙여 센다.

## 조직을 붙인다
결과에 본부·지사가 없다. `대상터널` 을 `', '`(쉼표+공백)로 자른 뒤 catalog 캐시로 조인한다.
이름 안의 쉼표는 정식 터널명의 일부다 — `근덕,적노,사직,남양터널` 이 터널 하나다.
`대상터널` 이 비어 있으면 응답만으로는 위치를 알 수 없다. 모른다고 답한다.
동명 터널이 있으므로 이름만으로 소속이 하나로 정해지지 않을 수 있다 — catalog 스킬을 따른다.

> 개선 예정: 응답에 조직 정보가 포함되고 `대상터널` 이 배열로 바뀐다.

## 도구가 실패하면
| 증상 | 뜻 | 안내 |
|---|---|---|
| 도구가 하나도 안 보임 | 플러그인 미설치 · MCP 미등록 | 아래 설치 안내 |
| 이 스킬 도구만 안 보임 | 권한 미부여 — **권한 없는 도구는 목록에 나오지 않는다** | **장애 이력 조회 권한** 을 Ai-Ops 에 요청 |
| 401 · 인증 요구 | 로그인 안 됨 · 토큰 만료 | `/mcp` 에서 재인증 (브라우저) |
| 403 · 권한 거부 | 권한 미부여 | 위와 같이 요청 |
| `ENOTFOUND` · 연결 불가 | DNS·회선 문제 (등록 문제가 아님) | 잠시 후 재시도, 계속되면 사내망 확인 |

권한을 새로 받았으면 `/mcp` 에서 **재인증**한다. 권한은 토큰에 담겨 발급되므로 갱신만으로는
늘어나지 않고, 이미 연결된 세션에는 도구 목록 변경이 통지되지 않는다.

설치는 **마켓플레이스 등록이 먼저**다. 터미널에서 (기본 `--scope user` = 전역):

```
claude plugin marketplace add anjsolution/plugins
claude plugin install tms@anjsolution
```

세션 안에서는 `/plugin marketplace add anjsolution/plugins` · `/plugin install tms@anjsolution`.
Codex 는 `codex plugin add tms@anjsolution`.
