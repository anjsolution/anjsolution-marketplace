"""ebid 계약공개현황 검색 — 체결된 계약(수의·지명경쟁 포함)을 계약명 키워드로 찾는다.

입찰공고 검색은 별도 도구 ebid_search_common.py. 결과는 한글 키로 정규화한 JSON 배열(stdout).
--md 는 대화창용 표, --table 은 한 줄 표. 진단은 stderr.

    python <스킬폴더>/scripts/ebid_search_contract.py --keyword "터널관리" --from 20190101
    python <스킬폴더>/scripts/ebid_search_contract.py --keyword "터널" --type 용역 --md
    python <스킬폴더>/scripts/ebid_search_contract.py --keyword "VMS" --detail --md   # 건별 상세까지
    python <스킬폴더>/scripts/ebid_search_contract.py --from 20260815 --type 용역 --md  # 키워드 없이 최근 계약 전체

- 기간 미지정 시 최근 1년(체결일 기준).
- --keyword 생략 시 검색어 없이 기간 내 전체를 가져온다(요청 본문에서 cntr_nm 제외). 이때 --from 은 필수
  (없으면 종료코드 2). 건수 제한은 두지 않으므로 호출 측이 기간을 좁혀야 한다(SKILL.md 검색 규칙).
- --detail: 건마다 상세 API 를 1회 더 호출해 계약기간·발주처·담당자/연락처·낙찰업체 대표/주소/지분·
  수의근거·설계금액/예정가격/개찰일시를 `상세` 키에 붙인다. 기본 상한 30건(--detail-limit).
- 계약은 건별 웹 딥링크가 없다. 조회 화면 진입: https://ebid.ex.co.kr/default.do?menuId=NPRO20001
  필드 의미·검증 근거는 references/ebid-필드사전.md §계약공개현황.
- 상세 실패 건은 `상세: null` + `상세오류: {종류, 메시지}` 로 남고, 일부 실패면 종료코드 3(전부 실패면 1).
Exit: 0 성공 / 1 통신·응답 실패 / 2 인자·날짜 오류 / 3 상세 일부 실패
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 어느 작업 폴더에서도 _ebid 를 찾는다
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import json
from datetime import datetime
from typing import Any

from _ebid.client import EbidClient
from _ebid.errors import DATE_HINT, KoreanArgumentParser, describe_error, report_error
from _ebid.contracts import (CONTRACT_PAGE_URL, DEFAULT_DETAIL_LIMIT, MAX_RETRIES,
                             fetch_contract_detail, search_contracts)
from _ebid.normalize import (normalize_contract, normalize_contract_detail, print_table,
                             render_contract_html, render_contract_markdown, write_output,
                             build_result_filename)
from _ebid.parallel import map_parallel
from _ebid.search import NOTICE_CLASS_LABELS, resolve_date_window

SEARCH_LOOKBACK_DAYS = 365  # 대화형 검색 기본 폭 — 최근 1년


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = KoreanArgumentParser(
        description="ebid 계약공개현황 검색(수의·지명 포함 체결 원장). 입찰공고는 ebid_search_common.py")
    parser.add_argument("--keyword", default="", help="계약명에 포함될 검색어 (생략 시 기간 내 전체 — 이때 --from 필수)")
    parser.add_argument("--from", dest="date_from", help="체결일 시작 YYYYMMDD (생략 시 최근 1년)")
    parser.add_argument("--to", dest="date_to", help="체결일 종료 YYYYMMDD (생략 시 오늘)")
    parser.add_argument("--type", dest="types", nargs="+", choices=["공사", "용역", "물품"],
                        help="발주유형 필터 (생략 시 전체 — 휴게소·단가 등 다른 유형도 포함)")
    parser.add_argument("--detail", action="store_true",
                        help="건별 상세 조회(계약기간·발주처·담당자·업체 대표/지분·수의근거·설계/예정가격)를 `상세` 키에 추가")
    parser.add_argument("--detail-limit", type=int, default=DEFAULT_DETAIL_LIMIT,
                        help=f"--detail 로 상세를 붙일 최대 건수 (기본 {DEFAULT_DETAIL_LIMIT}, 체결일 최신순)")
    parser.add_argument("--table", action="store_true", help="JSON 대신 사람용 표로 출력")
    parser.add_argument("--html", action="store_true", help="JSON 대신 HTML 표(브라우저·Artifact 용)")
    parser.add_argument("--out", help="결과를 이 파일에 저장 (파일명을 직접 정할 때만. 보통은 --out-dir)")
    parser.add_argument("--out-dir", dest="out_dir",
                        help="이 폴더에 저장하고 파일명은 스크립트가 짓는다 — 호출자가 이름 규칙을 알 필요가 없다")
    parser.add_argument("--md", action="store_true",
                        help="JSON 대신 대화창용 마크다운 표로 출력 (--detail 이면 상세 열 추가)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.keyword and not args.date_from:
        print("[ebid] --keyword 없이 검색하려면 --from 이 필수입니다 (기간 내 전체를 가져오므로). "
              "예: --from 20260815 [--to 20260830] [--type 용역]", file=sys.stderr)
        return 2
    try:
        from_date, to_date = resolve_date_window(
            args.date_from, args.date_to, lookback_days=SEARCH_LOOKBACK_DAYS)
    except ValueError as exc:
        print(f"[ebid] 날짜 형식 오류 — {DATE_HINT} (입력: {str(exc).split(': ', 1)[-1]})", file=sys.stderr)
        return 2
    if from_date > to_date:
        print(f"[ebid] --from({from_date})이 --to({to_date})보다 이후입니다.", file=sys.stderr)
        return 2
    if args.detail_limit < 0:
        print("[ebid] --detail-limit 은 0 이상이어야 합니다.", file=sys.stderr)
        return 2
    if not args.date_from:
        print(f"[ebid] 기간 미지정 → 기본 최근 1년({from_date}~{to_date}, 체결일 기준) 적용. "
              f"이력·과거 사업 질의면 --from 으로 범위를 넓혀 재검색",
              file=sys.stderr)

    if not args.keyword:
        print(f"[ebid] 키워드 없음 → {from_date}~{to_date} 기간 내 전체 계약. 건수가 많으면 기간을 더 좁힐 것",
              file=sys.stderr)
    client = EbidClient(max_retries=MAX_RETRIES)
    classes = [NOTICE_CLASS_LABELS[t] for t in args.types] if args.types else [None]
    raw: list[dict[str, Any]] = []
    try:
        client.ensure_csrf_token()  # 세션·토큰은 스레드 시작 전에 확보
    except Exception as exc:
        report_error("검색 실패", exc)
        return 1
    for cls, (items, exc) in zip(classes, map_parallel(
            lambda c: search_contracts(client, keyword=args.keyword or None, from_date=from_date,
                                       to_date=to_date, notice_class=c), classes)):
        if exc is not None:
            report_error(f"검색 실패({cls or '전체'})", exc)
            return 1
        raw.extend(items or [])

    raw.sort(key=lambda it: str(it.get("cntg_date") or ""), reverse=True)
    rows = [normalize_contract(it) for it in raw]

    detail_failed: list[tuple[str, str]] = []  # (계약번호, 종류)
    detail_done = 0
    if args.detail:
        targets = list(zip(raw, rows))[:args.detail_limit]
        if len(rows) > args.detail_limit:
            print(f"[ebid] --detail 상한 {args.detail_limit}건 적용 — 전체 {len(rows)}건 중 체결일 최신순 "
                  f"{args.detail_limit}건만 상세 조회. 더 필요하면 --detail-limit 을 올리거나 기간을 좁힐 것",
                  file=sys.stderr)
        results = map_parallel(lambda it: fetch_contract_detail(client, it), [it for it, _ in targets])
        for (item, row), (detail, exc) in zip(targets, results):  # 건별 동시 조회(상한 MAX_CONCURRENCY)
            if exc is None:
                row["상세"] = normalize_contract_detail(detail)
                detail_done += 1
            else:  # 한 건 실패가 전체를 막지 않는다 — 실패 종류·건은 결과에 남긴다
                row["상세"] = None
                row["상세오류"] = describe_error(exc)
                detail_failed.append((str(row.get("계약번호")), row["상세오류"]["종류"]))
        if detail_failed:
            print(f"[ebid] 상세 실패 {len(detail_failed)}건: "
                  + ", ".join(f"{no}[{kind}]" for no, kind in detail_failed), file=sys.stderr)

    # 기간은 기본값이든 지정이든 항상 실제 날짜 범위로 낸다 — "1년" 이라고만 쓰면 언제 기준인지
    # 알 수 없고, 답변에 날짜를 붙이려면 모델이 따로 계산해야 한다(그만큼 답변이 늦어진다).
    out_path = args.out
    stamp = f"{datetime.now():%Y%m%d-%H%M}"   # md 와 JSON 이 같은 시각을 공유해 짝이 맞는다
    if not out_path and args.out_dir:
        fmt = "html" if args.html else ("md" if args.md else "json")
        out_path = str(Path(args.out_dir) / build_result_filename("계약", args.keyword, fmt, stamp=stamp))
    period = (f"{from_date[:4]}-{from_date[4:6]}-{from_date[6:]}"
              f"~{to_date[:4]}-{to_date[4:6]}-{to_date[6:]}")
    # 공고 검색과 같은 규칙 — 원본 데이터를 항상 남겨 ebid_filter.py 로 재검색 없이 추릴 수 있게 한다.
    # `상세` 는 필터가 같은 열 구성으로 렌더링하려면 알아야 한다(--detail 이면 열이 달라진다).
    payload = {
        "검색": {"키워드": args.keyword, "기간": period, "유형": args.types or [],
                 "시각": stamp, "상세": bool(args.detail)},
        "계약": rows,
    }
    if args.out_dir and not args.out:
        data_path = str(Path(args.out_dir) / build_result_filename("검색계약", args.keyword, "json", stamp=stamp))
        write_output(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", data_path, link_label="원본 데이터")
    if args.md:
        write_output(render_contract_markdown(rows, keyword=args.keyword, period_label=period,
                                              detail=args.detail), out_path, link_label="목록")
    elif args.html:
        write_output(render_contract_html(rows, keyword=args.keyword, period_label=period,
                                          detail=args.detail), out_path)
    elif args.table:
        print_table(rows)
    elif not (args.out_dir and not args.out):   # JSON 은 위에서 이미 저장했다 — 중복 출력 방지
        write_output(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", args.out)
    print(f"[ebid] keyword={args.keyword!r} types={args.types or '전체'} range={from_date}~{to_date} "
          f"count={len(rows)} detail={'on' if args.detail else 'off'} page={CONTRACT_PAGE_URL}",
          file=sys.stderr)
    if detail_failed:
        return 3 if detail_done else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
