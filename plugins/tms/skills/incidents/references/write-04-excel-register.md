# 장애 history 엑셀 행 등록 (초안 추출 → 검토·수정 → 순차 등록)

[쓰기 공통 절차](write-01-common.md), [신규 장애 등록](write-02-incident.md),
[대응·조치 등록](write-03-history.md)을 함께 따른다. 이 문서는 엑셀 행을 등록할 때의 순서만 더한다.

사용자가 **등록할 접수번호를 지정**한 경우에만 진행한다("1945~1950번 TMS에 등록해줘").
비교 결과에서 미등록 행을 발견했다는 이유만으로 등록을 시작하지 않는다. 여러 건을 받아도 한 건씩
순서대로 처리하며, 결과를 확인하지 않고 여러 건을 한꺼번에 보내는 자동 일괄 등록은 보류 상태다.

## 1. 카탈로그 캐시 확인

대상 매핑은 [catalog 스킬](../../catalog/SKILL.md)의 캐시(`~/.anjsolution/tms/catalog.json`)를 쓴다.
세션에서 처음이면 `get_catalog_version`으로 캐시 버전을 대조하고, 다르거나 캐시에 `시스템분류`가
없으면 `get_catalog`를 다시 받아 원본 그대로 저장한다. 스크립트는 캐시가 없거나 낡은 형식이면 멈춘다.

## 2. 초안 추출

```bash
python scripts/excel_history.py extract <엑셀> <접수번호…> > <작업폴더>/drafts.json
```

작업 폴더는 `~/.anjsolution/tms/excel-drafts/<날짜>/`처럼 플러그인·Git 폴더 밖에 둔다(장애 내용 포함).
초안 한 건은 `incident`(create_incident 입력, `targets` 포함), `responses`, `resolution`,
`review`(등록을 막는 문제), `target_notes`(확인용 경고)를 가진다.

- F열(본부)·G열(터널명) 원문은 공개 식별자로 바뀐다. 약식·복합·범위 표기(`금사4,5`, `동산1-2, 북방1`),
  본부 별칭(`경남본부`→부산경남본부), 지사·본부 전체(`양산지사 전체터널`), 시스템(`ATMS 통합 웹`)을 해석한다.
- 하나로 정해지지 않으면 `targets`를 비우고 `review`에 사유와 **후보**를 남긴다. 동명 터널을 F열 본부로도
  가리지 못한 경우, 카탈로그에 없는 표기(`황전`처럼 1·2·3 중 어느 것인지 모르는 경우)가 대표적이다.
- `target_notes`는 F열 본부와 터널의 현재 소속이 다를 때의 경고다. 조직 개편(예: 수도권→서울경기)
  흔적이 대부분이라 등록을 막지 않지만 사용자에게 알린다.

## 3. 검토·수정

`review`가 있는 건은 사용자에게 사유와 후보를 보여 주고 **사용자가 정한 값**으로 JSON을 고친다.
후보가 하나뿐이어도 스스로 골라 채우지 않는다. 고칠 수 있는 곳은 다음과 같다.

- 대상: `incident.targets`를 공개 식별자로 바꾼다(형식은 [신규 장애 등록](write-02-incident.md)의 표).
- 장애·조치 분류: 엑셀 원본까지 고치려면 `fix`(비교 문서의 엑셀 수정 규칙)를 쓰고 다시 추출한다.
  이번 등록에만 반영하려면 JSON의 분류 값을 고친다.
- 대응 경과: 시각이 없는 줄은 사용자에게 시각을 받아 `responseAt`에 +09:00 KST로 넣는다.

`ready`·`review`는 고친 뒤 다시 계산되므로 손으로 바꾸지 않는다.

## 4. 재판정

```bash
python scripts/excel_history.py validate <작업폴더>/drafts.json
```

건마다 `ready`, `review`, `notes`, `requests`를 준다. `ready: true`인 건만 등록한다.
`requests`는 도구별 요청 본문이다(null 제외). `create_incident`에는 `idempotency_key`를,
대응·조치 요청에는 등록 결과의 `incidentCode`와 각각의 `idempotency_key`를 더해 보낸다.
`notes`(복구일자 없음, 소속 경고 등)는 등록 전에 사용자에게 알린다.

## 5. 순차 등록

지정된 접수번호 순서대로 한 건씩 다음을 끝낸 뒤 다음 건으로 넘어간다.

1. 같은 `legacyReceiptNo`가 이미 원격에 있는지 확인한다(비교 문서의 `check`). 있으면 건너뛴다.
2. `create_incident` — 공통 절차대로 UUID·입력을 기록한 뒤 전송한다.
3. 대응이 있으면 `add_incident_responses`, 조치가 있으면 `add_incident_resolution`을 이어서 보낸다.
   작업마다 UUID를 따로 만든다.
4. 결과를 작업 기록에 남긴다.

결과가 불명확한 건(timeout·감사 오류 등)이 나오면 **그 자리에서 멈추고** 상태를 보고한다. 나머지를
계속할지는 사용자가 정한다. 접수번호 중복(409)이면 이미 등록된 건으로 보고 원격을 확인한다.

## 6. 결과 보고

접수번호 → 장애코드, 등록·건너뜀·보류 사유를 표로 보고한다. `review`로 남긴 건과 `notes` 경고도 함께 적는다.
