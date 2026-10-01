# ANJSOLUTION Marketplace - Plugins

ANJSOLUTION 직원용 AI 플러그인 모음입니다.

---

## 1. 준비물

Claude Code 또는 Codex 를 설치해주세요.
터미널에서 `claude` 또는 `codex` 를 입력해 실행되면 준비 완료입니다.



---

## 2. 마켓플레이스 등록 & 플러그인 설치

> **마켓플레이스(플러그인 목록)를 등록**한 후에, **원하는 플러그인을 설치**할 수 있습니다. 
> 또는 원하는 플러그인을 직접 clone 받아 사용할 수 있습니다.

### Claude 1 - Claude Code (cli)

Claude Code 를 실행한 뒤, 프롬프트에 아래 두 줄을 차례로 입력합니다.

```
/plugin marketplace add anjsolution/anjsolution-marketplace
/plugin install <플러그인이름>@anjsolution
```

### Claude 2 - Claude Desktop App

```
1. [설정 메뉴] - [사용자 지정] - [플러그인]
2. 우상단 [추가] 버튼 - [마켓플레이스 추가] - [저장소에서 추가]
3. URL: `anjsolution/anjsolution-marketplace` 입력 
4. [동기화] 버튼 클릭
5. 우상단 [찾아보기] 버튼 - [플러그인] - [개인] - `anjsolution` 선택
6. `anjsolution` 마켓플레이스에서 원하는 plugin 선택하여 설치
```

### ChatGPT 1 - codex (cli)

터미널에서 아래 두 줄을 차례로 실행합니다.

```
codex plugin marketplace add anjsolution/anjsolution-marketplace
codex plugin add <플러그인이름>@anjsolution
```

### ChatGPT 2 - ChatGPT Desktop App

```
1. [플러그인] - 우상단 [추가] 버튼 - [마켓플레이스 추가]
2. 출처: `anjsolution/anjsolution-marketplace` 입력 
3. [마켓플레이스 추가] 버튼 클릭
4. 설치된 플러그인 목록 하단의 `공개/개인용` 탭에서 `개인용` 탭으로 이동
5. `anjsolution` 마켓플레이스에서 원하는 plugin 선택하여 설치
```



---

## 3. 사용할 수 있는 플러그인

| 플러그인 | 하는 일 | 설치 |
|---|---|---|
| `search-business` | 한국도로공사 ebid 공고·계약 검색·개찰결과·첨부 수집 | `/plugin install search-business@anjsolution` |

플러그인을 설치하면 별도 명령 없이 **평소처럼 질문하면** 됩니다.
예: "○○터널 최근 장애 이력 알려줘" → 관련 플러그인이 알아서 동작합니다.

일부 플러그인은 제한된 MCP 서버를 이용하기 위해 OAuth 인증, 사내 서비스 로그인을 요구할 수 있습니다.
별도 권한이 필요하거나 설치에 문제가 있는 경우 Ai-Ops 팀에 문의해주세요.



---

## 4. 최신 상태로 갱신

플러그인이 새로 추가되거나 바뀌면 아래 한 줄만 실행하세요.
자동 동기화 옵션을 켜두면 명령어를 사용하지 않고 자동으로 갱신됩니다.

```
/plugin marketplace update anjsolution          # Claude Code
codex plugin marketplace upgrade anjsolution    # Codex
```



---

## 5. 문제가 생기면

| 증상 | 원인·해결 |
|---|---|
| 플러그인이 반응하지 않음 | `/plugin` (Claude Code) 또는 `codex plugin list` 로 설치 여부 확인 → 갱신 후 재시도 |
| 특정 플러그인 설치 시 인증 오류 | Ai-Ops 에 권한 요청 |
| 그 외 | Ai-Ops 팀 (khchoi@anjsol.co.kr) 으로 문의 |

