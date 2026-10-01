"""장애 history 엑셀에서 지정한 접수번호 행의 원본 셀 값을 JSON으로 추출한다 (1단계).

  python history_extract.py <엑셀> 1945-1950 1952 > source.json

해석·매핑은 하지 않는다. 셀 값은 그대로 두고 일시(E·L열)만 +09:00 KST 문자열로 적는다.
다음 단계는 history_map.py다. 엑셀 셀을 고쳤다면 이 단계부터 다시 실행한다.
"""
import argparse
import json
import os
import sys
from datetime import datetime, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from history_workbook import COLUMNS, SHEET, kst, load_rows, parse_numbers  # noqa: E402


def cell_value(value):
    if isinstance(value, datetime):
        return kst(value)
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def extract(path, numbers):
    by_no = {}
    duplicates = set()
    for row in load_rows(path):
        if row["no"] in by_no:
            duplicates.add(row["no"])
        by_no.setdefault(row["no"], row)
    rows, missing = [], []
    for n in numbers:
        row = by_no.get(n)
        if not row:
            missing.append(n)
            continue
        rows.append({"receiptNo": n, "excelRow": row["excel_row"],
                     "cells": {label: cell_value(row[key]) for key, label in COLUMNS.values()
                               if key != "no"}})
    return {"workbook": os.path.abspath(str(path)), "sheet": SHEET,
            "extractedAt": kst(datetime.now()), "rows": rows,
            "missing": missing, "duplicateReceiptNos": sorted(duplicates & set(numbers))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("excel")
    parser.add_argument("numbers", nargs="+", help="예: 1945-1950 1952 또는 1,2,3")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(extract(args.excel, parse_numbers(args.numbers)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
