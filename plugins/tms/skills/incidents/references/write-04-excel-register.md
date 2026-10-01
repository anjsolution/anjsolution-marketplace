# 장애 history 엑셀 행 등록 (점검 → 판단·수정 → 검증 → 묶음 병렬 등록)

[쓰기 공통 절차](write-01-common.md), [신규 장애 등록](write-02-incident.md),
[대응·조치 등록](write-03-history.md)을 함께 따른다. 이 문서는 엑셀 행을 등록할 때의 순서만 더한다.

사용자가 **등록할 접수번호를 지정**한 경우에만 진행한다("1945~1950번 TMS에 등록해줘").
비교·점검 결과에서 미등록 행을 발견했다는 이유만으로 등록을 시작하지 않는다. 여러 건은 아래 4단계의
묶음 단위로 처리한다.

## 1. 점검

[엑셀 행 점검](read-04-excel-review.md)으로 `source.json`과 `drafts.json`을 만들고 판정 기록을 검토한다.
등록 전에 원격에 같은 접수번호가 없는지 [비교](read-03-excel-compare.md)의 `locate`·`check`로 확인한다.
`check`가 "중복 의심"(접수번호 없이 같은 시각에 등록된 원격 장애)을 내면 그 행은 등록하지 않고,
원격 장애에 접수번호를 넣어야 한다고 보고한다.

## 2. 판단·수정

`drafts.json`을 고친다. 원본(`source.json`)은 고치지 않는다.

- `checks`: 판단을 마친 건에 `"checksReviewed": true`와 `"judgmentNote": "판단 근거"`를 적는다.
  판단을 바꿔 값을 고쳤다면 고친 값과 근거를 함께 적는다.
- `blockers`: **사용자가 정한 값**으로 해당 칸을 고친다. 후보가 하나뿐이어도 스스로 채우지 않는다.
  - 대상: `incident.targets`를 공개 식별자로 바꾼다(형식은 [신규 장애 등록](write-02-incident.md)의 표).
  - 분류 코드: 이번 등록에만 반영하려면 JSON의 분류 값을 고친다. 엑셀 원본까지 고치려면
    `history_fix.py <엑셀> <접수번호> --code/--action <값>`을 쓰고 점검 1단계부터 다시 한다.
    이 스크립트는 값을 검증하고 백업을 만든 뒤 해당 셀만 바꾼다. 엑셀이 열려 있으면 닫아 달라고 안내한다.
  - 대응 경과: 시각이 없는 줄은 사용자에게 시각을 받아 `responseAt`에 +09:00 KST로 넣는다.
- `ready`·`blockers`·`checks`는 손으로 지우지 않는다. 검증 단계가 현재 값으로 다시 판정한다.

## 3. 검증

```bash
python scripts/history_validate.py drafts.json > requests.json
```

건마다 `ready`, `blockers`, `pendingChecks`(판단 표시가 없는 check), `notes`, `requests`를 준다.
`ready: true`인 건만 등록한다. `notes`(복구일자 없음 등)는 등록 전에 사용자에게 알린다.
`requests`는 null을 뺀 도구 입력이다. `add_incident_responses`는 도구 1회 최대 건수로 나눈 목록이다.

## 4. 묶음 병렬 등록

건끼리는 서로 의존하지 않으므로 묶음(5~10건) 단위로 병렬 전송한다. 전송 전에 건마다 장애·대응·조치
UUID를 모두 만들어 요청 기록에 저장한다. 묶음 하나는 두 번에 나눠 보낸다.

1. 묶음의 `create_incident`를 한 번에 함께 보낸다. `requests.create_incident`에 `idempotency_key`를 더한다.
2. 성공한 건의 `incidentCode`로 각 건의 `add_incident_responses`(목록 순서대로)와
   `add_incident_resolution`을 한 번에 함께 보낸다. 같은 건의 대응 목록이 여러 개면 순서대로 보낸다.
3. 결과(접수번호 → 장애코드, 단계별 성공 여부)를 작업 기록에 남긴다.

묶음 안에서 결과가 불명확하거나 실패한 건이 있으면 **다음 묶음으로 넘어가지 않고** 상태를 보고한다.
같은 묶음의 다른 건은 이미 전송됐을 수 있으므로 건별로 조회해 실제 반영 여부를 확인한다.
재시도는 저장한 같은 UUID와 입력으로 하며, 장애만 등록되고 대응·조치가 빠진 건은 대응·조치만 보낸다.
접수번호 중복(409)이면 이미 등록된 건으로 보고 원격을 확인한다.

## 5. 결과 보고

접수번호 → 장애코드, 등록·건너뜀·보류 사유를 표로 보고한다. 판단한 check와 그 근거, 남은 blockers도 함께 적는다.
