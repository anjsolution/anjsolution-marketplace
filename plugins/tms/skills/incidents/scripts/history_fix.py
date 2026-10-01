"""장애 history 엑셀의 장애코드(D열)·조치코드(K열) 셀을 검증 후 고친다.

  python history_fix.py <엑셀> 1945 --action ORCH [--code HL100]

사용자가 고칠 값을 명시한 경우에만 쓴다. 값을 검증하고, 원본 옆에 .bak-날짜 백업을 만든 뒤
시트 XML의 해당 셀만 바꾼다(차트·매크로 보존). 엑셀에서 파일이 열려 있으면 거부한다.
고친 뒤에는 history_extract.py부터 다시 실행한다.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import history_rules as hr  # noqa: E402
from history_workbook import load_rows, text, write_cells  # noqa: E402


def fix(path, number, code=None, action=None):
    row = next((r for r in load_rows(path) if r["no"] == number), None)
    if not row:
        sys.exit(f"접수번호 {number}이(가) 엑셀에 없습니다.")
    cells, before = {}, {}
    if code:
        if not hr.is_valid_incident_code(code):
            sys.exit(f"장애코드 '{code}'는 유효하지 않습니다.")
        ref = f"D{row['excel_row']}"
        cells[ref], before[ref] = code.upper(), text(row["code"])
    if action:
        if not hr.is_valid_action_code(action):
            sys.exit(f"조치코드 '{action}'는 유효하지 않습니다.")
        ref = f"K{row['excel_row']}"
        cells[ref], before[ref] = action.upper(), text(row["action"])
    if not cells:
        sys.exit("--code 또는 --action 중 하나 이상을 지정하세요.")
    backup = write_cells(path, cells)
    return {"접수번호": number, "변경": {ref: {"이전": before[ref], "이후": v} for ref, v in cells.items()},
            "백업": backup}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("excel")
    parser.add_argument("number", type=int)
    parser.add_argument("--code", help="D열 장애코드 (예: HL100)")
    parser.add_argument("--action", help="K열 조치코드 (예: ORCH)")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    print(json.dumps(fix(args.excel, args.number, args.code, args.action), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
