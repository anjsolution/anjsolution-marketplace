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


def test_locate_groups_numbers_by_received_date(workbook, capsys):
    out = run(capsys, "locate", workbook, "1-4")
    assert out["조회"] == [
        {"from": "2026-06-22", "to": "2026-06-22", "접수번호": [1, 2]},
        {"from": "2026-06-23", "to": "2026-06-23", "접수번호": [4]}]
    assert out["엑셀에_없거나_접수일_없음"] == [3]


def test_check_judges_presence_by_receipt_number(workbook, tmp_path, capsys):
    remote = tmp_path / "bydate.json"
    remote.write_text(json.dumps([
        {"목록": [{"장애코드": "HL100-a", "접수번호": 1, "접수일시": "2026-06-22T09:30:00+09:00"}]},
        {"목록": [{"장애코드": "HL100-b", "접수번호": None, "접수일시": "2026-06-23T08:48:00+09:00"}]},
    ]), encoding="utf-8")
    out = run(capsys, "check", workbook, "1,2,4", "--remote", remote)
    assert out[0] == {"접수번호": 1, "판정": "있음", "장애코드": "HL100-a", "접수일시_일치": True}
    assert out[1]["판정"] == "없음"
    assert out[2]["판정"] == "중복 의심" and out[2]["원격_후보"] == ["HL100-b"]


def test_method_other_is_allowed():
    assert eh.parse_action_code("OOCH") == (
        {"target": "OTHER", "method": "OTHER", "access": "ONSITE", "type": "HARDWARE"}, None)


def test_number_specs():
    assert eh.parse_numbers(["1940-1942", "5,7"]) == [1940, 1941, 1942, 5, 7]


CATALOG = {"version": {}, "본부": {
    "강원본부": {"지사": {}},
    "대구경북본부": {"지사": {"청송지사": {"터널": {
        "남정5터널": {"코드": "065330", "노선": "동해선(포항-영덕)", "관리동": "남정5터널 관리동"}}}}},
    "서울경기본부": {"지사": {"이천지사": {"터널": {
        "금사4,금사5터널": {"코드": "045560", "노선": "중부내륙선", "관리동": None}}}}},
}, "시스템분류": {"ATMS": ["통합", "통합 웹", "#2", "DB"], "교통센터": []}}


@pytest.fixture
def catalog_file(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(CATALOG, ensure_ascii=False), encoding="utf-8")
    return path


def test_extract_maps_targets_to_public_identifiers(workbook, catalog_file, capsys):
    out = run(capsys, "extract", workbook, "1", "--catalog", catalog_file)
    assert out[0]["incident"]["targets"] == [{"tunnelCode": "065330"}]
    assert out[0]["target_notes"] == []
    assert out[0]["ready"] is True


def test_extract_requires_catalog_cache(workbook, tmp_path):
    with pytest.raises(SystemExit, match="get_catalog"):
        eh.main(["extract", str(workbook), "1", "--catalog", str(tmp_path / "none.json")])


def test_unmapped_target_blocks_ready_and_mismatch_only_warns(tmp_path, catalog_file, capsys):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "장애 history"
    ws.append(HEADER)
    ws.append(row(1, {7: "없는터널"}))
    ws.append(row(2, {6: "강원본부", 7: "금사4,5"}))
    ws.append(row(3, {6: "전체본부", 7: "ATMS 통합 웹"}))
    path = tmp_path / "targets.xlsx"
    wb.save(path)
    one, two, three = run(capsys, "extract", path, "1-3", "--catalog", catalog_file)
    assert one["ready"] is False and one["incident"]["targets"] == []
    assert any("없는터널" in r for r in one["review"])
    assert two["ready"] is True and two["incident"]["targets"] == [{"tunnelCode": "045560"}]
    assert "서울경기본부" in two["target_notes"][0]
    assert three["incident"]["targets"] == [{"system": {"category": "ATMS", "subcategory": "통합 웹"}}]


def test_pending_marks_unmapped_targets_only_with_catalog(workbook, tmp_path, catalog_file, capsys):
    remote = tmp_path / "remote.json"
    remote.write_text(json.dumps({"목록": [{"장애코드": "X", "접수번호": 0}]}), encoding="utf-8")
    out = run(capsys, "pending", workbook, "--remote", remote, "--catalog", catalog_file)
    assert [r["접수번호"] for r in out["등록_가능"]] == [1]


def test_validate_rechecks_edited_json_and_builds_requests(workbook, tmp_path, catalog_file, capsys):
    drafts = run(capsys, "extract", workbook, "1,2,4", "--catalog", catalog_file)
    # 검토자가 JSON을 고친다: 2번 조치코드 해석 불가 → 방법을 직접 지정, 4번 대상을 없는 코드로 바꿈
    drafts[1]["resolution"]["method"] = "REBOOT"
    drafts[2]["incident"]["targets"] = [{"tunnelCode": "999999"}]
    edited = tmp_path / "drafts.json"
    edited.write_text(json.dumps(drafts, ensure_ascii=False), encoding="utf-8")
    one, two, four = run(capsys, "validate", edited, "--catalog", catalog_file)

    assert one["ready"] is True and one["review"] == []
    create = one["requests"]["create_incident"]
    assert create["targets"] == [{"tunnelCode": "065330"}]
    assert "controllerSubType" not in create and None not in create.values()
    assert "idempotency_key" not in create
    assert [r["responseAt"] for r in one["requests"]["add_incident_responses"]["responses"]] == [
        "2026-06-21T16:48:00+09:00", "2026-06-22T09:30:00+09:00", "2026-06-22T09:54:00+09:00"]
    assert one["requests"]["add_incident_resolution"]["method"] == "REBOOT"

    assert two["ready"] is True  # 저장된 review가 아니라 현재 값으로 다시 판정한다
    assert any("resolvedAt" in n for n in two["notes"])  # 복구일자 없음은 경고만
    assert two["requests"]["add_incident_responses"] is None
    assert "remarks" not in two["requests"]["add_incident_resolution"]

    assert four["ready"] is False
    assert any("999999" in r for r in four["review"])
    assert any("category" in r for r in four["review"])


@pytest.mark.parametrize("target,needle", [
    ({"system": {"category": "ATMS"}, "tunnelCode": "065330"}, "시스템"),
    ({"system": {"category": "ATM"}}, "ATM"),
    ({"branchName": "없는지사"}, "없는지사"),
    ({"tunnelId": 1}, "tunnelId"),
    ({}, "비어"),
])
def test_validate_rejects_bad_targets(workbook, tmp_path, catalog_file, capsys, target, needle):
    drafts = run(capsys, "extract", workbook, "1", "--catalog", catalog_file)
    drafts[0]["incident"]["targets"] = [target]
    edited = tmp_path / "drafts.json"
    edited.write_text(json.dumps(drafts, ensure_ascii=False), encoding="utf-8")
    (one,) = run(capsys, "validate", edited, "--catalog", catalog_file)
    assert one["ready"] is False and any(needle in r for r in one["review"])
