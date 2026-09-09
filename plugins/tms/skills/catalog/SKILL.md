---
name: catalog
description: TMS 터널·노선·본부/지사/관리동·유지보수 업체 마스터 데이터를 다룰 때 쓴다. 트리거 — "터널 몇 개야", "이 터널 어느 지사야", "OO본부 터널 목록", "터널명 정식 명칭이 뭐야", "노선별 터널 현황", 그리고 다른 TMS 조회 결과에 본부·지사를 붙여야 할 때. 장애 이력 자체를 묻는 질문은 incidents 스킬.
---

# catalog — 터널·조직 마스터 데이터

## 캐시 파일로 재사용한다
`~/.anjsolution/tms/catalog.json` — `get_catalog` 응답을 `version` 포함 원본 그대로 저장한다.

1. 파일이 있으면 필요한 부분만 꺼내 쓴다
2. 세션에서 처음이면 `get_catalog_version` 으로 파일의 `version` 과 대조한다
3. 다르거나 파일이 없으면 `get_catalog` 를 부르고 **응답을 그대로 파일에 저장한다**
4. 이후 툴 호출은 이름 대신 `codes[]` 를 쓴다

플러그인 설치 폴더는 설치 시 복사되므로 쓰기 대상이 아니다.

## 알아둘 것
- 연장·서버 수는 카탈로그에 없다 — `search_tunnels` 로 조회한다
- 관리동은 `null` 인 터널이 많다 (서버 보유 터널 위주로 지정되는 정상 상태)
- 본부/지사 미지정은 예약 키 `"(미지정)"` 아래에 온다
- 이름이 캐시와 안 맞으면 근사 매칭하지 말고 못 찾았다고 보고한다

## 도구가 실패하면
| 증상 | 뜻 | 안내 |
|---|---|---|
| 도구가 하나도 안 보임 | 플러그인 미설치 · MCP 미등록 | 아래 설치 안내 |
| 이 스킬 도구만 안 보임 | 권한 미부여 — **권한 없는 도구는 목록에 나오지 않는다** | **터널·조직 마스터 조회 권한** 을 Ai-Ops 에 요청 |
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
