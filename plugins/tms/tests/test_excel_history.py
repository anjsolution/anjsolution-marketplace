"""장애 history 엑셀 → 등록 초안·미등록 판별·코드 수정이 이관 규칙대로 동작하는지 확인한다."""
import importlib.util
import json
import zipfile
from datetime import datetime
from pathlib import Path

import openpyxl
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "skills/incidents/scripts/excel_history.py"
spec = importlib.util.spec_from_file_location("excel_history", SCRIPT)
eh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eh)

HEADER = ["접수번호", "처리완료", "보고서", "장애코드", "접수일자", "본부", "터널명", "접수자",
          "신고자소속", "신고자", "조치코드", "복구일자", "처리자", "소요", "장애내용",
          "대응경과", "원인", "조치", "비고"]


def row(no, overrides=None):
    base = {1: no, 2: "처리", 4: "HL100", 5: datetime(2026, 6, 22, 9, 30), 6: "대구경북본부",
            7: "남정5", 8: "현준도", 9: "대구경북 대보정보통신", 10: "윤시태", 11: "ORCH",
            12: datetime(2026, 6, 22, 9, 54), 13: "윤시태", 15: "TTMS서버 다운",
            16: "6/21 16:48 서버 다운 발생\n09:30 팀장 문의\n추가 설명\n09:54 재기동 후 해소",
            17: "내부 온도 상승", 18: "재기동 후 해소"}
    base.update(overrides or {})
    return [base.get(i) for i in range(1, len(HEADER) + 1)]


@pytest.fixture
def workbook(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "장애 history"
    ws.append(HEADER)
    ws.append(row(1))
    ws.append(row(2, {4: "SL320", 11: "OXBS", 16: "없음", 12: None, 18: None}))
    ws.append(row(4, {4: None, 5: datetime(2026, 6, 23, 8, 48), 16: "시각 없는 메모"}))
    path = tmp_path / "history.xlsx"
    wb.save(path)
    return path


def run(capsys, *argv):
    eh.main([str(a) for a in argv])
    return json.loads(capsys.readouterr().out)


def test_extract_matches_migration_rules(workbook):
    draft = eh.build({r["no"]: r for r in eh.load_rows(workbook)}[1])
    assert draft["incident"] == {
        "legacyReceiptNo": 1, "receivedAt": "2026-06-22T09:30:00+09:00",
        "receiverName": "현준도", "reporterName": "윤시태",
        "reporterOrganization": "대구경북 대보정보통신", "category": "HARDWARE",
        "location": "ADMIN_SERVER", "deviceCategory": "SERVER", "controllerSubType": None,
        "memo": "TTMS서버 다운"}
    assert [(r["responseAt"], r["content"]) for r in draft["responses"]] == [
        ("2026-06-21T16:48:00+09:00", "서버 다운 발생"),
        ("2026-06-22T09:30:00+09:00", "팀장 문의\n추가 설명"),
        ("2026-06-22T09:54:00+09:00", "재기동 후 해소")]
    assert draft["resolution"]["method"] == "REBOOT"
    assert draft["target_text"] == {"본부": "대구경북본부", "터널명": "남정5"}
    assert draft["ready"] is True


def test_invalid_codes_block_without_guessing(workbook):
    rows = {r["no"]: r for r in eh.load_rows(workbook)}
    two = eh.build(rows[2])
    assert two["incident"]["controllerSubType"] == "LCS"
    assert two["responses"] == []
    assert two["resolution"]["method"] is None
    assert two["ready"] is False and "K열" in two["review"][0]
    four = eh.build(rows[4])
    assert four["incident"]["category"] is None
    assert four["responses"][0]["responseAt"] is None
    assert [m[:2] for m in four["review"]] == ["D열", "P열"]


def test_pending_uses_last_remote_receipt_and_flags_duplicates(workbook, tmp_path, capsys):
    remote = tmp_path / "remote.json"
    remote.write_text(json.dumps({"목록": [
        {"장애코드": "HL100-a", "접수번호": None, "접수일시": "2026-06-23T08:48:00+09:00", "메모": "UI"},
        {"장애코드": "HL100-b", "접수번호": 1, "접수일시": "2026-06-22T09:30:00+09:00", "메모": "첫",
         "대응기록수": 2, "조치완료": False},
    ]}), encoding="utf-8")
    out = run(capsys, "pending", workbook, "--remote", remote)
    assert out["기준_접수번호"] == 1
    assert out["결번"] == [3]
    assert out["등록_가능"] == []
    assert [r["접수번호"] for r in out["수정_필요"]] == [2, 4]
    assert out["중복_확인"][0]["같은시각_엑셀"] == [4]
    assert out["대응조치_추가분"] == [
        {"접수번호": 1, "장애코드": "HL100-b", "추가": "대응", "엑셀": 3, "원격": 2},
        {"접수번호": 1, "장애코드": "HL100-b", "추가": "조치"}]


def test_pending_requires_receipt_field_or_after(workbook, tmp_path, capsys):
    remote = tmp_path / "remote.json"
    remote.write_text(json.dumps({"목록": [{"장애코드": "X", "접수일시": "2026-01-01"}]}),
                      encoding="utf-8")
    with pytest.raises(SystemExit):
        eh.main(["pending", str(workbook), "--remote", str(remote)])
    out = run(capsys, "pending", workbook, "--remote", remote, "--after", 2)
    assert [r["접수번호"] for r in out["수정_필요"]] == [4]


def test_fix_patches_only_target_cell(workbook, capsys):
    before = zipfile.ZipFile(workbook)
    before_parts = {n: before.read(n) for n in before.namelist()}
    before.close()
    with pytest.raises(SystemExit):
        eh.main(["fix", str(workbook), "2", "--action", "OXBS"])
    out = run(capsys, "fix", workbook, 2, "--action", "orbs", "--code", "SL320")
    assert out["변경"] == {"K3": {"이전": "OXBS", "이후": "ORBS"},
                          "D3": {"이전": "SL320", "이후": "SL320"}}
    assert Path(out["백업"]).exists()
    rows = {r["no"]: r for r in eh.load_rows(workbook)}
    assert rows[2]["action"] == "ORBS" and rows[1]["action"] == "ORCH"
    assert eh.build(rows[2])["ready"] is True
    after = zipfile.ZipFile(workbook)
    changed = [n for n in after.namelist() if after.read(n) != before_parts.get(n)]
    after.close()
    # workbook.xml은 calcPr가 있을 때만 재계산 표시로 바뀐다
    assert "xl/worksheets/sheet1.xml" in changed
    assert set(changed) <= {"xl/workbook.xml", "xl/worksheets/sheet1.xml"}


def test_method_other_is_allowed():
    assert eh.parse_action_code("OOCH") == (
        {"target": "OTHER", "method": "OTHER", "access": "ONSITE", "type": "HARDWARE"}, None)


def test_number_specs():
    assert eh.parse_numbers(["1940-1942", "5,7"]) == [1940, 1941, 1942, 5, 7]
