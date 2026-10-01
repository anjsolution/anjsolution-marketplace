"""장애 history 엑셀 → 원본 추출 → 매핑 → 검증, 원격 비교, 셀 수정이 이관 규칙대로 동작하는지 확인한다."""
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/incidents/scripts"))
import history_compare  # noqa: E402
import history_extract  # noqa: E402
import history_fix  # noqa: E402
import history_map  # noqa: E402
import history_rules as hr  # noqa: E402
import history_validate  # noqa: E402

HEADER = ["접수번호", "처리완료", "보고서", "장애코드", "접수일자", "본부", "터널명", "접수자",
          "신고자소속", "신고자", "조치코드", "복구일자", "처리자", "소요", "장애내용",
          "대응경과", "원인", "조치", "비고"]


def row(no, overrides=None):
    base = {1: no, 2: "처리", 4: "HL100", 5: datetime(2026, 6, 22, 9, 30), 6: "대구경북본부",
            7: "남정5", 8: "현준도", 9: "대구경북 대보정보통신", 10: "윤시태", 11: "OOCH",
            12: datetime(2026, 6, 22, 9, 54), 13: "윤시태", 15: "청송지사 남정5터널 TTMS서버 다운",
            16: "6/21 16:48 서버 다운 발생\n09:30 팀장 문의\n추가 설명\n09:54 재기동 후 해소",
            17: "내부 온도 상승", 18: "재기동 후 해소"}
    base.update(overrides or {})
    return [base.get(i) for i in range(1, len(HEADER) + 1)]


def make_workbook(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "장애 history"
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


@pytest.fixture
def workbook(tmp_path):
    return make_workbook(tmp_path / "history.xlsx", [
        row(1),
        row(2, {4: "SL320", 11: "OXBS", 16: "없음", 12: None, 18: None}),
        row(4, {4: None, 5: datetime(2026, 6, 23, 8, 48), 16: "시각 없는 메모"}),
    ])


CATALOG = {"version": {"tunnels": {"row_count": 2}}, "본부": {
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


def run(module, capsys, *argv):
    module.main([str(a) for a in argv])
    return json.loads(capsys.readouterr().out)


def write_json(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


# ── 1단계: 원본 추출 ─────────────────────────────────────────────────

def test_extract_keeps_raw_cells_without_interpretation(workbook, capsys):
    out = run(history_extract, capsys, workbook, "1,2,3")
    assert out["missing"] == [3]
    first = out["rows"][0]
    assert first["receiptNo"] == 1 and first["excelRow"] == 2
    cells = first["cells"]
    assert cells["D_장애코드"] == "HL100" and cells["K_조치코드"] == "OOCH"
    assert cells["E_접수일자"] == "2026-06-22T09:30:00+09:00"
    assert cells["P_대응경과"].startswith("6/21 16:48")
    assert "incident" not in first  # 해석은 매핑 단계에서만 한다


# ── 2단계: 매핑 ─────────────────────────────────────────────────────

def mapped(workbook, catalog_file, tmp_path, capsys, numbers="1,2,4"):
    source = write_json(tmp_path, "source.json", run(history_extract, capsys, workbook, numbers))
    return run(history_map, capsys, source, "--catalog", catalog_file)


def test_map_builds_draft_matching_migration_rules(workbook, catalog_file, tmp_path, capsys):
    out = mapped(workbook, catalog_file, tmp_path, capsys)
    one = out["drafts"][0]
    assert one["incident"] == {
        "legacyReceiptNo": 1, "receivedAt": "2026-06-22T09:30:00+09:00",
        "receiverName": "현준도", "reporterName": "윤시태",
        "reporterOrganization": "대구경북 대보정보통신", "category": "HARDWARE",
        "location": "ADMIN_SERVER", "deviceCategory": "SERVER", "controllerSubType": None,
        "memo": "청송지사 남정5터널 TTMS서버 다운", "targets": [{"tunnelCode": "065330"}]}
    assert [(r["responseAt"], r["content"]) for r in one["responses"]] == [
        ("2026-06-21T16:48:00+09:00", "서버 다운 발생"),
        ("2026-06-22T09:30:00+09:00", "팀장 문의\n추가 설명"),
        ("2026-06-22T09:54:00+09:00", "재기동 후 해소")]
    assert one["resolution"]["method"] == "OTHER"  # 방법 O(기타)
    assert one["ready"] is True and one["blockers"] == [] and one["checks"] == []
    assert [d["rule"] for d in one["decisions"]] == ["progress.continuation"]


def test_map_separates_blockers_checks_and_summary(workbook, catalog_file, tmp_path, capsys):
    out = mapped(workbook, catalog_file, tmp_path, capsys)
    _, two, four = out["drafts"]
    assert two["incident"]["controllerSubType"] == "LCS"
    assert two["responses"] == [] and two["resolution"]["method"] is None
    assert any("K열" in b for b in two["blockers"])
    assert four["incident"]["category"] is None
    assert any("D열" in b for b in four["blockers"]) and any("P열" in b for b in four["blockers"])
    summary = out["summary"]
    assert summary["ready"] == [1] and summary["blocked"] == [2, 4]
    assert summary["byRule"]["action_code.invalid"] == {"level": "fail", "receiptNos": [2]}
    assert list(summary["byRule"])[0] in {r for r, e in summary["byRule"].items() if e["level"] == "fail"}


def test_map_reports_judgment_items(tmp_path, catalog_file, capsys):
    path = make_workbook(tmp_path / "t.xlsx", [
        row(1, {6: "강원본부", 7: "금사4,5", 15: "이천지사 금사4,5터널 장애"}),
        row(2, {6: "전체본부", 7: "ATMS 통합 웹"}),
        row(3, {7: "없는터널"}),
        row(4, {12: datetime(2026, 6, 21, 9, 0)}),
    ])
    out = mapped(path, catalog_file, tmp_path, capsys, "1-4")
    one, two, three, four = out["drafts"]
    assert one["incident"]["targets"] == [{"tunnelCode": "045560"}]
    assert one["ready"] is False and not one["blockers"]
    assert any("서울경기본부" in c for c in one["checks"])  # F열 본부와 현재 소속 다름
    assert two["incident"]["targets"] == [{"system": {"category": "ATMS", "subcategory": "통합 웹"}}]
    assert three["incident"]["targets"] == [] and any("없는터널" in b for b in three["blockers"])
    assert any("복구일자" in c for c in four["checks"])  # 복구가 접수보다 이름
    assert out["summary"]["needsJudgment"] == [1, 4]
    assert out["summary"]["divisionMismatch"] == {"강원본부 → 서울경기본부": [1]}


# ── 3단계: 검증 ─────────────────────────────────────────────────────

def test_validate_rechecks_edits_and_requires_check_review(workbook, catalog_file, tmp_path, capsys):
    out = mapped(workbook, catalog_file, tmp_path, capsys)
    drafts = out["drafts"]
    drafts[1]["resolution"]["method"] = "REBOOT"            # 사용자가 정한 조치 방법
    drafts[2]["incident"]["targets"] = [{"tunnelCode": "999999"}]
    drafts[0]["checks"] = ["예시 판단 항목"]                   # 판단 전이면 막힌다
    assert drafts[1]["checks"]                                 # 2번은 복구일자 없음 판단 항목이 있다
    drafts[1]["checksReviewed"] = True
    result = run(history_validate, capsys, write_json(tmp_path, "d.json", out), "--catalog", catalog_file)
    one, two, four = result["results"]
    assert one["ready"] is False and one["pendingChecks"] == ["예시 판단 항목"]
    assert two["ready"] is True and any("resolvedAt" in n for n in two["notes"])
    assert four["ready"] is False and any("999999" in b for b in four["blockers"])

    drafts[0]["checksReviewed"] = True
    drafts[0]["judgmentNote"] = "사용자 확인"
    result = run(history_validate, capsys, write_json(tmp_path, "d.json", out), "--catalog", catalog_file)
    one = result["results"][0]
    assert one["ready"] is True and one["judgmentNote"] == "사용자 확인"
    create = one["requests"]["create_incident"]
    assert create["targets"] == [{"tunnelCode": "065330"}] and create["legacyReceiptNo"] == 1
    assert "controllerSubType" not in create and None not in create.values()
    assert [len(b["responses"]) for b in one["requests"]["add_incident_responses"]] == [3]
    assert one["requests"]["add_incident_resolution"]["method"] == "OTHER"
    assert result["summary"]["ready"] == [1, 2]


def test_validate_batches_long_response_lists(tmp_path, catalog_file, capsys):
    lines = "\n".join(f"{9 + i // 60:02d}:{i % 60:02d} 경과 {i}" for i in range(45))
    path = make_workbook(tmp_path / "long.xlsx", [row(1, {16: lines})])
    out = mapped(path, catalog_file, tmp_path, capsys, "1")
    assert "responses.batched" in [d["rule"] for d in out["drafts"][0]["decisions"]]
    result = run(history_validate, capsys, write_json(tmp_path, "d.json", out), "--catalog", catalog_file)
    batches = result["results"][0]["requests"]["add_incident_responses"]
    assert [len(b["responses"]) for b in batches] == [20, 20, 5]


@pytest.mark.parametrize("target,needle", [
    ({"system": {"category": "ATMS"}, "tunnelCode": "065330"}, "시스템"),
    ({"system": {"category": "ATM"}}, "ATM"),
    ({"branchName": "없는지사"}, "없는지사"),
    ({"tunnelId": 1}, "tunnelId"),
    ({}, "비어"),
])
def test_validate_rejects_bad_targets(workbook, tmp_path, catalog_file, capsys, target, needle):
    out = mapped(workbook, catalog_file, tmp_path, capsys, "1")
    out["drafts"][0]["incident"]["targets"] = [target]
    result = run(history_validate, capsys, write_json(tmp_path, "d.json", out), "--catalog", catalog_file)
    one = result["results"][0]
    assert one["ready"] is False and any(needle in b for b in one["blockers"])


def test_validate_enforces_length_limits(workbook, tmp_path, catalog_file, capsys):
    out = mapped(workbook, catalog_file, tmp_path, capsys, "1")
    out["drafts"][0]["incident"]["reporterName"] = "가" * 51
    result = run(history_validate, capsys, write_json(tmp_path, "d.json", out), "--catalog", catalog_file)
    assert any("reporterName" in b for b in result["results"][0]["blockers"])


# ── 원격 비교 ────────────────────────────────────────────────────────

def test_pending_uses_last_remote_receipt_and_flags_duplicates(workbook, tmp_path, capsys):
    remote = write_json(tmp_path, "remote.json", {"목록": [
        {"장애코드": "HL100-a", "접수번호": None, "접수일시": "2026-06-23T08:48:00+09:00", "메모": "UI"},
        {"장애코드": "HL100-b", "접수번호": 1, "접수일시": "2026-06-22T09:30:00+09:00", "메모": "첫",
         "대응기록수": 2, "조치완료": False},
    ]})
    out = run(history_compare, capsys, "pending", workbook, "--remote", remote)
    assert out["기준_접수번호"] == 1 and out["결번"] == [3]
    assert [r["접수번호"] for r in out["엑셀에만_있음"]] == [2, 4]
    assert out["중복_확인"][0]["같은시각_엑셀"] == [4]
    assert out["중복_확인"][0]["판정"] == "엑셀 행과 같은 장애 의심"
    assert out["대응조치_추가분"] == [
        {"접수번호": 1, "장애코드": "HL100-b", "추가": "대응", "엑셀": 3, "원격": 2},
        {"접수번호": 1, "장애코드": "HL100-b", "추가": "조치"}]


def test_pending_requires_receipt_field_or_after(workbook, tmp_path, capsys):
    remote = write_json(tmp_path, "remote.json", {"목록": [{"장애코드": "X", "접수일시": "2026-01-01"}]})
    with pytest.raises(SystemExit):
        history_compare.main(["pending", str(workbook), "--remote", str(remote)])
    out = run(history_compare, capsys, "pending", workbook, "--remote", remote, "--after", 2)
    assert [r["접수번호"] for r in out["엑셀에만_있음"]] == [4]


def test_locate_and_check(workbook, tmp_path, capsys):
    out = run(history_compare, capsys, "locate", workbook, "1-4")
    assert out["조회"] == [
        {"from": "2026-06-22", "to": "2026-06-22", "접수번호": [1, 2]},
        {"from": "2026-06-23", "to": "2026-06-23", "접수번호": [4]}]
    assert out["엑셀에_없거나_접수일_없음"] == [3]
    remote = write_json(tmp_path, "bydate.json", [
        {"목록": [{"장애코드": "HL100-a", "접수번호": 1, "접수일시": "2026-06-22T09:30:00+09:00"}]},
        {"목록": [{"장애코드": "HL100-b", "접수번호": None, "접수일시": "2026-06-23T08:48:00+09:00"}]},
    ])
    out = run(history_compare, capsys, "check", workbook, "1,2,4", "--remote", remote)
    assert out[0] == {"접수번호": 1, "판정": "있음", "장애코드": "HL100-a", "접수일시_일치": True}
    assert out[1]["판정"] == "없음"
    assert out[2]["판정"] == "중복 의심" and out[2]["원격_후보"] == ["HL100-b"]


# ── 셀 수정 ──────────────────────────────────────────────────────────

def test_fix_patches_only_target_cell(workbook, capsys):
    with zipfile.ZipFile(workbook) as z:
        before = {n: z.read(n) for n in z.namelist()}
    with pytest.raises(SystemExit):
        history_fix.main([str(workbook), "2", "--action", "OXBS"])
    out = run(history_fix, capsys, workbook, 2, "--action", "orbs", "--code", "SL320")
    assert out["변경"] == {"D3": {"이전": "SL320", "이후": "SL320"}, "K3": {"이전": "OXBS", "이후": "ORBS"}}
    assert Path(out["백업"]).exists()
    with zipfile.ZipFile(workbook) as z:
        changed = [n for n in z.namelist() if z.read(n) != before.get(n)]
    assert "xl/worksheets/sheet1.xml" in changed
    assert set(changed) <= {"xl/workbook.xml", "xl/worksheets/sheet1.xml"}
    cells = run(history_extract, capsys, workbook, "2")["rows"][0]["cells"]
    assert cells["K_조치코드"] == "ORBS"


# ── 규칙 단위 ────────────────────────────────────────────────────────

def test_code_rules():
    assert hr.parse_action_code("OOCH")[0] == {"target": "OTHER", "method": "OTHER",
                                               "access": "ONSITE", "type": "HARDWARE"}
    assert hr.parse_action_code("-")[1][0]["rule"] == "action_code.missing"
    fields, found = hr.parse_incident_code("SL320, SL330")
    assert fields["controllerSubType"] == "LCS" and found[0]["rule"] == "incident_code.multiple"
    assert hr.parse_incident_code("SL300")[1][0]["level"] == "fail"


def test_progress_year_rollover_is_a_check():
    responses, found = hr.split_progress("12/31 23:50 발생\n1/1 00:10 조치",
                                         datetime(2026, 1, 1, 0, 0), "홍길동")
    assert responses[0]["responseAt"] == "2025-12-31T23:50:00+09:00"
    assert [d["rule"] for d in found] == ["progress.year_rollover"]
