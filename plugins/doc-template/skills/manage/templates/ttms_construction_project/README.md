# ttms_construction_project 템플릿

TTMS 서버 구매(설치포함) 공사 서류용 HWPX 서식 모음. `hwpx` 스킬(`hwpx.mjs fill|export`)로 `{{키}}` 를 채운다.
값 JSON 은 `pages` 로 1쪽(서버 표) 1번 + 2쪽(사진 2장 대지)을 사진 수만큼 반복해 구성한다.

| 파일 | 용도 | 단일/이중화 | 입력 키 |
|---|---|---|---|
| `server_receiving_photo_sheet.hwpx` | 서버 입고 사진 대지 (2-3-1) | 단일 | 공사명, 모델명, S/N, 사진-1, 사진-2, 내용-1, 내용-2, 위치, 날짜 |
| `server_receiving_photo_sheet_dual.hwpx` | 서버 입고 사진 대지 (2-3-1) | 이중화 (Master/Slave 2행) | 공사명, 모델명-1, S/N-1, 모델명-2, S/N-2, 사진-1, 사진-2, 내용-1, 내용-2, 위치, 날짜 |
| `server_delivery_photo_sheet.hwpx` | 서버 납품 사진 대지 (4-2-1) | 단일 | 입고 단일과 동일 |
| `server_delivery_photo_sheet_dual.hwpx` | 서버 납품 사진 대지 (4-2-1) | 이중화 (Master/Slave 2행) | 입고 이중화와 동일 |

- 사진-n 은 이미지 키(파일 경로), 나머지는 텍스트 키다. `공사명`, `위치`, `날짜` 는 한 문서에 여러 번 나오며 같은 값으로 채워진다.
- 이중화 변형은 1쪽 서버 표에 행을 하나 더 두었다 (1행 비고 `Master`, 2행 비고 `Slave`). 나머지 구성은 단일과 같다.
- 단일 파일은 사내 원본 서식(2-3-1 입고, 4-2-1 납품 사진 대지)의 복사본이고, 이중화 파일은 그 파생본이다.
- 활용 절차는 `references/ttms_construction_project/ttms_photo_doc_make.md`, 이중화 규칙은 `ttms_photo_doc_types.md`.
- 이 폴더는 이후 TTMS 전용 플러그인이 생기면 `ttms_construction_project` 폴더째 옮긴다.
- 서식에는 직인·도장 등 이미지(BinData)가 없다. 사진은 채울 때만 들어간다.
