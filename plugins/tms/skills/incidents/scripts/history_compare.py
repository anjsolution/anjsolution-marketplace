"""장애 history 엑셀과 원격 TMS 조회 결과를 비교한다 (카탈로그 불필요).

  python history_compare.py pending <엑셀> --remote 최근조회.json [--after 1944]
  python history_compare.py locate  <엑셀> 1707 1708 1800-1805
  python history_compare.py check   <엑셀> 1707 1708 --remote 날짜별조회.json

pending : 원격 최근 조회(search_incidents 응답 저장본)의 마지막 접수번호 이후 엑셀에만 있는 행,
          접수번호 없는 원격 장애와 같은 날·같은 시각인 엑셀 행(중복 의심),
          조회 범위 안에서 엑셀 쪽 대응·조치가 더 많은 건, 결번을 보고한다.
locate  : 접수번호를 엑셀 접수일별로 묶어 search_incidents from/to 조회 계획을 만든다.
check   : 날짜별 조회 결과로 번호마다 있음·없음·중복 의심을 판정한다.
          엑셀 접수번호 순서가 접수일 순서와 다를 수 있어 최종 존재 확인은 이 방식으로 한다.
등록 여부 판단(코드·대상 해석)은 하지 않는다. 그것은 history_extract → history_map 단계다.
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import history_rules as hr  # noqa: E402
from history_workbook import kst, load_rows, parse_numbers, text  # noqa: E402


def load_remote(path):
    """search_incidents 응답(한 페이지·페이지 배열·목록 배열)에서 장애 목록만 모은다."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    items = []
    for page in data if isinstance(data, list) else [data]:
        items.extend(page.get("목록", []) if "목록" in page else [page])
    return items


def _received(row):
    return row["received"] if isinstance(row["received"], datetime) else None


def _summary(row):
    return {"접수번호": row["no"], "접수일시": kst(_received(row)), "터널명": text(row["tunnel"]),
            "내용": (text(row["content"]) or "")[:60]}


def pending(rows, remote_path, after):
    items = load_remote(remote_path)
    if after is None and not any("접수번호" in it for it in items):
        sys.exit("원격 조회 결과에 접수번호 필드가 없습니다. 서버 배포 전이면 --after로 마지막 접수번호를 지정하세요.")
    numbered = [it for it in items if it.get("접수번호") is not None]
    last = max(numbered, key=lambda it: it["접수번호"], default=None)
    if after is None:
        if not last:
            sys.exit("조회한 원격 장애에 접수번호가 하나도 없습니다. 조회 범위를 넓히세요.")
        after = last["접수번호"]
    todo = [r for r in rows if r["no"] > after]
    numbers = [r["no"] for r in todo]
    dup_check = []
    for it in items:
        if it.get("접수번호") is not None:
            continue
        # 접수번호 없이 등록된 원격 장애 — 엑셀 전체 행과 접수일시로 짝을 찾는다
        at = it.get("접수일시") or ""
        same = [r["no"] for r in rows if (kst(_received(r)) or "")[:10] == at[:10]]
        exact = [r["no"] for r in rows if (kst(_received(r)) or "")[:16] == at[:16]]
        dup_check.append({"원격_장애코드": it.get("장애코드"), "접수일시": at,
                          "메모": (it.get("메모") or "")[:80], "같은날_엑셀": same,
                          "같은시각_엑셀": exact,
                          "판정": "엑셀 행과 같은 장애 의심" if exact else
                                  ("같은 날 엑셀 행 있음" if same else "엑셀에 없음")})
    by_no = {r["no"]: r for r in rows}
    additions = []
    for it in numbered:
        row = by_no.get(it["접수번호"])
        if not row:
            continue
        responses, _ = hr.split_progress(row["progress"], _received(row), text(row["handler"]))
        remote_count = it.get("대응기록수") or 0
        if len(responses) > remote_count:
            additions.append({"접수번호": it["접수번호"], "장애코드": it.get("장애코드"), "추가": "대응",
                              "엑셀": len(responses), "원격": remote_count})
        has_resolution = text(row["action"]) or text(row["measure"]) or isinstance(row["resolved"], datetime)
        if has_resolution and it.get("조치완료") is False:
            additions.append({"접수번호": it["접수번호"], "장애코드": it.get("장애코드"), "추가": "조치"})
    return {
        "기준_접수번호": after,
        "원격_마지막_장애": last and {k: last.get(k) for k in ("접수번호", "장애코드", "접수일시", "메모")},
        "엑셀_마지막_접수번호": max((r["no"] for r in rows), default=None),
        "결번": sorted(set(range(after + 1, max(numbers) + 1)) - set(numbers)) if numbers else [],
        "엑셀에만_있음": [_summary(r) for r in todo],
        "중복_확인": dup_check,
        "대응조치_추가분": additions,
    }


def locate(rows, numbers):
    by_no = {r["no"]: r for r in rows}
    plan, missing = {}, []
    for n in numbers:
        received = _received(by_no[n]) if n in by_no else None
        if received:
            plan.setdefault(received.strftime("%Y-%m-%d"), []).append(n)
        else:
            missing.append(n)
    return {"조회": [{"from": day, "to": day, "접수번호": nos} for day, nos in sorted(plan.items())],
            "엑셀에_없거나_접수일_없음": missing}


def check(rows, numbers, remote_path):
    items = load_remote(remote_path)
    if not any("접수번호" in it for it in items):
        sys.exit("원격 조회 결과에 접수번호 필드가 없습니다.")
    by_remote = {it["접수번호"]: it for it in items if it.get("접수번호") is not None}
    by_no = {r["no"]: r for r in rows}
    result = []
    for n in numbers:
        at = kst(_received(by_no[n])) if n in by_no else None
        found = by_remote.get(n)
        if found:
            result.append({"접수번호": n, "판정": "있음", "장애코드": found.get("장애코드"),
                           "접수일시_일치": (found.get("접수일시") or "")[:16] == (at or "")[:16]})
            continue
        same = [it.get("장애코드") for it in items if it.get("접수번호") is None
                and at and (it.get("접수일시") or "")[:16] == at[:16]]
        result.append({"접수번호": n, "판정": "중복 의심" if same else "없음",
                       "엑셀_접수일시": at, **({"원격_후보": same} if same else {})})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pending", help="원격 마지막 접수번호 이후 엑셀에만 있는 행")
    p.add_argument("excel")
    p.add_argument("--remote", required=True, help="search_incidents 응답 저장 JSON")
    p.add_argument("--after", type=int, help="마지막 접수번호 직접 지정")
    p = sub.add_parser("locate", help="접수번호별 날짜 조회 계획")
    p.add_argument("excel")
    p.add_argument("numbers", nargs="+")
    p = sub.add_parser("check", help="날짜별 조회 결과로 접수번호 존재 판정")
    p.add_argument("excel")
    p.add_argument("numbers", nargs="+")
    p.add_argument("--remote", required=True, help="날짜별 search_incidents 응답 저장 JSON")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    rows = load_rows(args.excel)
    if args.cmd == "pending":
        result = pending(rows, args.remote, args.after)
    elif args.cmd == "locate":
        result = locate(rows, parse_numbers(args.numbers))
    else:
        result = check(rows, parse_numbers(args.numbers), args.remote)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
