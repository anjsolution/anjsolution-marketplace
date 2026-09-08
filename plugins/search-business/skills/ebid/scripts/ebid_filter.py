"""저장된 검색 결과(JSON)에서 조건에 맞는 건만 추려 md 로 다시 낸다 — 재검색 없이.

"OO 들어간 것만 정리해줘" 같은 후속 요청을 모델이 원본을 읽어 손으로 골라 쓰지 않게 하려고 만들었다.
표 형식은 검색 결과와 완전히 같다(같은 렌더러를 쓴다).

    python <스킬폴더>/scripts/ebid_filter.py --in <검색 json> --contains 건설 --out-dir <폴더>
    python <스킬폴더>/scripts/ebid_filter.py --in <검색 json> --field 상태 --contains 낙찰 --table
    python <스킬폴더>/scripts/ebid_filter.py --in <검색 json> --kind 사전공개 --contains 터널 --out-dir <폴더>
    python <스킬폴더>/scripts/ebid_filter.py --in <계약 json> --kind 계약 --contains 감리 --out-dir <폴더>

- 입력은 검색 도구가 `--out-dir` 과 함께 저장하는 원본 JSON — 공고·사전공개는 `ebid_검색_*.json`,
  계약은 `ebid_검색계약_*.json`.
- 기본 검색 대상 필드는 이름 열(공고=공고명, 사전공개=사업명, 계약=계약명). `--field` 로 다른 필드도 가능.
- 부분일치·대소문자 무시. 결과 파일명은 원본 시각을 물려받는다(어느 검색에서 나왔는지 보이게).
Exit: 0 성공 / 1 입력 파일 오류 / 2 인자 오류 / 3 조건에 맞는 건 없음(파일 안 만듦)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 어느 작업 폴더에서도 _ebid 를 찾는다
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import json
from typing import Any

from _ebid.errors import KoreanArgumentParser
from _ebid.normalize import (build_result_filename, print_table, render_contract_markdown,
                             render_notice_markdown, render_pqstd_markdown, write_output)

NAME_FIELD = {"공고": "공고명", "사전공개": "사업명", "계약": "계약명"}


def parse_args(argv: list[str] | None = None):
    parser = KoreanArgumentParser(description="저장된 ebid 검색 결과(JSON)에서 조건에 맞는 건만 추려 md 로 낸다")
    parser.add_argument("--in", dest="src", required=True, help="ebid_search_common.py 가 저장한 ebid_검색_*.json")
    parser.add_argument("--contains", required=True, help="포함할 문자열 (부분일치·대소문자 무시)")
    parser.add_argument("--field", help="검색할 필드 (기본: 공고=공고명, 사전공개=사업명)")
    parser.add_argument("--kind", choices=["공고", "사전공개", "계약"], default="공고",
                        help="거를 대상 (기본: 공고. 계약 JSON 은 `ebid_검색계약_*.json`)")
    parser.add_argument("--out-dir", dest="out_dir", help="이 폴더에 저장하고 파일명은 스크립트가 짓는다")
    parser.add_argument("--out", help="결과를 이 파일에 저장 (파일명을 직접 정할 때만)")
    parser.add_argument("--table", action="store_true", help="md 대신 사람용 표로 출력")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        data = json.loads(Path(args.src).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[ebid] 입력 파일을 읽을 수 없습니다 — {args.src}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(data, dict) or "검색" not in data:
        print("[ebid] ebid_search_common.py 가 저장한 검색 JSON 이 아닙니다 (`검색` 키 없음). "
              "`ebid_검색_*.json` 을 지정하세요.", file=sys.stderr)
        return 2

    meta = data.get("검색") or {}
    rows: list[dict[str, Any]] = data.get(args.kind) or []
    field = args.field or NAME_FIELD[args.kind]
    needle = args.contains.strip().lower()
    hits = [r for r in rows if needle in str(r.get(field) or "").lower()]
    print(f"[ebid] {args.kind} {len(rows)}건 중 {field}에 {args.contains!r} 포함 {len(hits)}건",
          file=sys.stderr)
    if not hits:
        return 3

    period = meta.get("기간") or ""
    keyword = meta.get("키워드") or ""
    # 표 제목의 검색어는 원본 검색어가 아니라 이번 필터 조건으로 쓴다 — 표가 무엇을 추린 것인지
    # 제목만 봐도 알 수 있어야 하고, 강조(굵게)도 필터 조건에 걸리는 편이 읽기 좋다.
    if args.kind == "사전공개":
        text = render_pqstd_markdown(hits, keyword=args.contains, period_label=period)
    elif args.kind == "계약":
        # `--detail` 로 뽑은 검색이면 열이 더 붙는다 — 원본과 같은 열 구성으로 렌더링한다.
        text = render_contract_markdown(hits, keyword=args.contains, period_label=period,
                                        detail=bool(meta.get("상세")))
    else:
        text = render_notice_markdown(hits, keyword=args.contains, period_label=period)

    if args.table:
        print_table(hits)
        return 0
    out_path = args.out
    if not out_path and args.out_dir:
        # 원본 시각(stamp)을 물려받아 어느 검색에서 나온 결과인지 파일명에서 보이게 한다.
        base = build_result_filename(args.kind, keyword, "md",
                                     variant=f"filter_{args.contains}", stamp=meta.get("시각"))
        path = Path(args.out_dir) / base
        n = 2
        while path.exists():   # 같은 필터를 다시 돌려도 덮어쓰지 않는다
            path = path.with_name(f"{path.stem}_{n}{path.suffix}")
            n += 1
        out_path = str(path)
    write_output(text, out_path, link_label="추린 목록")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
