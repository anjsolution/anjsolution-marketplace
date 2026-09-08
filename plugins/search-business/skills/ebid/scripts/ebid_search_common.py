"""ebid 입찰공고 검색 — 공사·용역·물품 공고를 키워드로 찾는다.

계약공개현황(수의·지명 포함 체결 원장)은 별도 도구 ebid_search_contract.py.
결과는 한글 키로 정규화한 JSON 배열(stdout). --md 는 대화창용 표, --table 은 한 줄 표. 진단은 stderr.

    python <스킬폴더>/scripts/ebid_search_common.py --keyword "구내통신" --from 20260101
    python <스킬폴더>/scripts/ebid_search_common.py --keyword "VMS" --type 공사 물품 --table
    python <스킬폴더>/scripts/ebid_search_common.py --keyword "ITS" --md   # 대화창용
    python <스킬폴더>/scripts/ebid_search_common.py --from 20260815 --type 용역 --md   # 키워드 없이 최근 공고 전체

- 기간 미지정 시 최근 1년. 공고번호 조회에는 기간 개념이 없다(ebid_result / ebid_fetch).
- --keyword 생략 시 검색어 없이 기간 내 전체를 가져온다(요청 본문에서 noti_nm 제외). 이때 --from 은 필수
  (없으면 종료코드 2). 건수 제한은 두지 않으므로 호출 측이 기간을 좁혀야 한다(SKILL.md 검색 규칙).
- 출력은 "아는 필드는 한글 키로 정규화 + 나머지 원본 필드 passthrough".
  필드 의미·상태코드·딥링크 규칙은 references/ebid-필드사전.md.
Exit: 0 성공 / 1 통신·응답 실패 / 2 인자·날짜 오류
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
from _ebid.errors import DATE_HINT, KoreanArgumentParser, report_error
from _ebid.normalize import (normalize_notice, normalize_pqstd, print_table, render_notice_html,
                             render_notice_markdown, render_notice_markdown_compact,
                             render_pqstd_markdown, write_output, build_result_filename)
from _ebid.parallel import map_parallel
from _ebid.pqstd import PQSTD_CLASS_LABELS, fetch_pqstd_list
from _ebid.search import NOTICE_CLASS_LABELS, STATUS_FILTER_OVERRIDE, resolve_date_window

MAX_RETRIES = 2
SEARCH_LOOKBACK_DAYS = 365  # 대화형 검색 기본 폭 — 최근 1년

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = KoreanArgumentParser(description="ebid 입찰공고 검색(공사·용역·물품). 계약공개현황은 ebid_search_contract.py")
    parser.add_argument("--keyword", default="", help="공고명에 포함될 검색어 (생략 시 기간 내 전체 — 이때 --from 필수)")
    parser.add_argument("--from", dest="date_from", help="시작일 YYYYMMDD (생략 시 최근 1년)")
    parser.add_argument("--to", dest="date_to", help="종료일 YYYYMMDD (생략 시 오늘)")
    parser.add_argument(
        "--type", dest="types", nargs="+", default=["공사", "용역", "물품"],
        choices=["공사", "용역", "물품"],
        help="발주유형 (기본: 공사 용역 물품 전부)",
    )
    parser.add_argument("--table", action="store_true", help="JSON 대신 사람용 표로 출력")
    parser.add_argument("--html", action="store_true", help="JSON 대신 HTML 표(브라우저·Artifact 용, 공고명 링크)")
    parser.add_argument("--out", help="결과를 이 파일에 저장 (파일명을 직접 정할 때만. 보통은 --out-dir)")
    parser.add_argument("--out-dir", dest="out_dir",
                        help="이 폴더에 저장하고 파일명은 스크립트가 짓는다 — 호출자가 이름 규칙을 알 필요가 없다")
    parser.add_argument("--md", action="store_true",
                        help="JSON 대신 대화창용 마크다운 표로 출력 (발주유형별 표 + 공고명 딥링크)")
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
    if not args.date_from:
        print(f"[ebid] 기간 미지정 → 기본 최근 1년({from_date}~{to_date}) 적용. "
              f"이력·과거 사업 질의면 --from 으로 범위를 넓혀 재검색",
              file=sys.stderr)

    if not args.keyword:
        print(f"[ebid] 키워드 없음 → {from_date}~{to_date} 기간 내 전체 공고. 건수가 많으면 기간을 더 좁힐 것",
              file=sys.stderr)
    overrides: dict[str, Any] = {"arr_status": STATUS_FILTER_OVERRIDE}
    if args.keyword:
        overrides["noti_nm"] = args.keyword
    client = EbidClient(max_retries=MAX_RETRIES)
    rows: list[dict[str, Any]] = []
    try:
        client.ensure_csrf_token()  # 세션·토큰은 스레드 시작 전에 확보 (없으면 403)
    except Exception as exc:
        report_error("검색 실패", exc)
        return 1

    # 경로는 "입찰공고 유형별" + "사전공개 유형별" 두 계열이다. 사전공개는 별도 API·별도 식별자라
    # 옵션으로 켜고 끄지 않고 같은 검색에 얹는다 — 어차피 유형별 호출이 필요해 병렬 레인만 늘어난다.
    # 공사는 사전공개 메뉴 자체가 없어 자동으로 빠진다.
    notice_lanes = [("공고", label) for label in args.types]
    pqstd_lanes = [("사전공개", label) for label in args.types if label in PQSTD_CLASS_LABELS]

    def fetch(lane: tuple[str, str]) -> list[dict[str, Any]]:
        kind, label = lane
        if kind == "사전공개":
            return fetch_pqstd_list(client, notice_class=PQSTD_CLASS_LABELS[label],
                                    from_date=from_date, to_date=to_date, keyword=args.keyword)
        items, _st, _url = client.fetch_bid_notice_list(
            notice_class=NOTICE_CLASS_LABELS[label], from_noti_date=from_date,
            to_noti_date=to_date, payload_overrides=overrides)
        return items

    lanes = notice_lanes + pqstd_lanes
    pq_rows: list[dict[str, Any]] = []
    for (kind, label), (items, exc) in zip(lanes, map_parallel(fetch, lanes)):  # 경로별 동시 조회
        if exc is not None:
            report_error(f"검색 실패({kind} {label})", exc)
            return 1
        if kind == "사전공개":
            pq_rows.extend(normalize_pqstd(it) for it in items or [])
        else:
            rows.extend(normalize_notice(it) for it in items or [])

    rows.sort(key=lambda r: r.get("공고일") or "", reverse=True)
    pq_rows.sort(key=lambda r: r.get("공개일") or "", reverse=True)
    # 기간은 기본값이든 지정이든 항상 실제 날짜 범위로 낸다 — "1년" 이라고만 쓰면 언제 기준인지
    # 알 수 없고, 답변에 날짜를 붙이려면 모델이 따로 계산해야 한다(그만큼 답변이 늦어진다).
    out_path = args.out
    stamp = f"{datetime.now():%Y%m%d-%H%M}"   # 요약본·상세본이 같은 시각을 공유해 짝이 맞는다
    if not out_path and args.out_dir:
        fmt = "html" if args.html else ("md" if args.md else "json")
        out_path = str(Path(args.out_dir) / build_result_filename("공고", args.keyword, fmt, stamp=stamp))
    period = (f"{from_date[:4]}-{from_date[4:6]}-{from_date[6:]}"
              f"~{to_date[:4]}-{to_date[4:6]}-{to_date[6:]}")
    # 원본 데이터(JSON)는 표시 형식과 무관하게 항상 남긴다 — 나중에 "OO 만 골라줘" 같은 요청을
    # 재검색 없이 ebid_filter.py 로 처리하기 위한 입력이다. 이미 메모리에 있는 rows 를 쓰는 것뿐이라
    # 추가 요청이 없다. 검색 조건도 같이 담는다 — 없으면 필터 결과의 표 제목을 재현할 수 없다.
    payload = {
        "검색": {"키워드": args.keyword, "기간": period, "유형": args.types, "시각": stamp},
        "공고": rows,
        "사전공개": pq_rows,
    }
    if args.out_dir and not args.out:
        data_path = str(Path(args.out_dir) / build_result_filename("검색", args.keyword, "json", stamp=stamp))
        write_output(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", data_path, link_label="원본 데이터")
    # 사전공개는 공고와 열이 달라 같은 표에 못 섞는다 — 파일 자체를 나눈다.
    pq_md = render_pqstd_markdown(pq_rows, keyword=args.keyword, period_label=period)
    if args.md:
        if args.out_dir and not args.out:
            # 훑어보기용 요약본을 함께 낸다. 같은 rows 를 다시 렌더링할 뿐이라 추가 요청이 없다.
            brief = Path(args.out_dir) / build_result_filename(
                "공고", args.keyword, "md", variant="summarize", stamp=stamp)
            write_output(render_notice_markdown_compact(rows, keyword=args.keyword, period_label=period),
                         str(brief), link_label="목록")
            write_output(render_notice_markdown(rows, keyword=args.keyword, period_label=period),
                         out_path, link_label="목록(상세)")
            if pq_md:
                pq_path = str(Path(args.out_dir) / build_result_filename(
                    "사전공개", args.keyword, "md", stamp=stamp))
                write_output(pq_md, pq_path, link_label="사전공개")
        else:
            write_output(render_notice_markdown(rows, keyword=args.keyword, period_label=period)
                         + ("\n" + pq_md if pq_md else ""), out_path)
    elif args.html:
        write_output(render_notice_html(rows, keyword=args.keyword, period_label=period), out_path)
    elif args.table:
        print_table(rows)
        if pq_rows:
            print_table(pq_rows)
    elif not (args.out_dir and not args.out):   # JSON 은 위에서 이미 저장했다 — 중복 출력 방지
        write_output(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", args.out)
    print(f"[ebid] keyword={args.keyword!r} types={args.types} range={from_date}~{to_date} "
          f"count={len(rows)} 사전공개={len(pq_rows)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
