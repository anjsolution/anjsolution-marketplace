"""F열(본부)·G열(터널명) 원문 → 공개 식별자 targets 매핑과 판정 기록(수준·규칙)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/incidents/scripts"))
import history_targets as ht  # noqa: E402


def leaf(code):
    return {"코드": code, "노선": "노선", "관리동": None}


# get_catalog 응답 형태 (실제 카탈로그의 이름·코드 일부)
CATALOG = {
    "version": {},
    "본부": {
        "강원본부": {"지사": {
            "양양지사": {"터널": {"서면1터널": leaf("060152"), "서면3터널": leaf("060154"),
                               "서면4터널": leaf("060155")}},
            "춘천지사": {"터널": {"동산1,동산2,북방1터널": leaf("060110")}},
        }},
        "광주전남본부": {"지사": {
            "구례지사": {"터널": {"서면1터널": leaf("027030"), "서면5,서면4,서면3터널": leaf("027070"),
                               "황전1터널": leaf("027130"), "황전2터널": leaf("027904")}},
            "보성지사": {"터널": {"강진4터널": leaf("010520")}},
            "함평지사": {"터널": {"어등산 호남대터널": leaf("012110")}},
        }},
        "대구경북본부": {"지사": {
            "청송지사": {"터널": {"남정5터널": leaf("065330"), "남정1 ,남정2터널": leaf("065331")}},
            "영천지사": {"터널": {"달전터널": leaf("020159"), "와촌터널": leaf("020150")}},
            "군위지사": {"터널": {"다부터널": leaf("055359")}},
        }},
        "대전충남본부": {"지사": {"당진지사": {"터널": {}}}},
        "부산경남본부": {"지사": {
            "경주지사": {"터널": {"문무대왕3,문무대왕4,문무대왕5,오천1터널": leaf("065020")}},
            "양산지사": {"터널": {"상동,신어산터널": leaf("600007")}},
            "서울산지사": {"터널": {}},
            "밀양지사": {"터널": {"영산터널": leaf("014400")}},
        }},
        "서울경기본부": {"지사": {"이천지사": {"터널": {"금사4,금사5터널": leaf("045560")}}}},
        "수도권본부": {"지사": {"시흥지사": {"터널": {"수리,수암터널": leaf("100390")}}}},
    },
    "시스템분류": {"ATMS": ["통합", "통합 웹", "#2", "DB"], "교통센터": [], "폴스타": [],
                 "통합플랫폼": [], "미분류": []},
}


@pytest.fixture
def catalog():
    return ht.Catalog(CATALOG)


def rules(decisions):
    return [(d["level"], d["rule"]) for d in decisions]


def test_exact_name_is_exact(catalog):
    targets, decisions = ht.map_targets("대구경북본부", "남정5", catalog)
    assert targets == [{"tunnelCode": "065330"}]
    assert rules(decisions) == [("exact", "tunnel.exact")]


@pytest.mark.parametrize("division,text,code,rule", [
    ("서울경기본부", "금사4,5", "045560", "tunnel.expanded"),
    ("강원본부", "동산1,2 북방1", "060110", "tunnel.expanded"),
    ("강원본부", "동산1-2, 북방1터널", "060110", "tunnel.expanded"),
    ("경남본부", "양북3-5", "065020", "tunnel.expanded"),
    ("대구경북본부", "남정2", "065331", "tunnel.exact"),
    ("수도권본부", "수리수암터널", "100390", "tunnel.joined"),
])
def test_rule_based_inputs_collapse_to_one_tunnel(catalog, division, text, code, rule):
    targets, decisions = ht.map_targets(division, text, catalog)
    assert targets == [{"tunnelCode": code}]
    assert rule in [d["rule"] for d in decisions]
    assert all(d["level"] in ("exact", "rule") for d in decisions)


def test_alias_is_reported_as_rule(catalog):
    _, decisions = ht.map_targets("경남본부", "양북3-5", catalog)
    assert ("rule", "tunnel.alias") in rules(decisions)


def test_same_name_uses_division_hint_else_fails(catalog):
    targets, decisions = ht.map_targets("강원본부", "서면1", catalog)
    assert targets == [{"tunnelCode": "060152"}] and ("rule", "tunnel.narrowed") in rules(decisions)
    assert ht.map_targets("전남본부", "서면1", catalog)[0] == [{"tunnelCode": "027030"}]
    targets, decisions = ht.map_targets(None, "서면1", catalog)
    assert targets == [] and ("fail", "tunnel.ambiguous") in rules(decisions)


def test_same_name_narrowed_by_memo_branch_needs_judgment(catalog):
    targets, decisions = ht.map_targets(None, "서면1", catalog, memo="구례지사 서면1터널 통신 장애")
    assert targets == [{"tunnelCode": "027030"}]
    assert ("check", "tunnel.narrowed_by_context") in rules(decisions)


def test_same_name_narrowed_by_other_tunnels_in_same_cell(catalog):
    targets, decisions = ht.map_targets(None, "강진4, 서면1", catalog)
    assert targets == [{"tunnelCode": "010520"}, {"tunnelCode": "027030"}]
    assert ("check", "tunnel.narrowed_by_context") in rules(decisions)


def test_single_substring_candidate_is_filled_as_check(catalog):
    targets, decisions = ht.map_targets(None, "호남대터널", catalog)
    assert targets == [{"tunnelCode": "012110"}]
    assert rules(decisions) == [("check", "tunnel.substring_unique")]


def test_several_substring_candidates_fail_with_candidates(catalog):
    targets, decisions = ht.map_targets("전남본부", "황전", catalog)
    assert targets == [] and decisions[0]["rule"] == "tunnel.not_found"
    assert "027130" in decisions[0]["message"] and "027904" in decisions[0]["message"]


@pytest.mark.parametrize("division,text,expected,level", [
    ("전체본부", "ATMS", [{"system": {"category": "ATMS"}}], "exact"),
    (None, "ATMS", [{"system": {"category": "ATMS"}}], "exact"),
    ("강원본부", "ATMS", [{"system": {"category": "ATMS"}, "divisionName": "강원본부"}], "exact"),
    ("경북본부", "ATMS 통합 웹", [{"system": {"category": "ATMS", "subcategory": "통합 웹"},
                               "divisionName": "대구경북본부"}], "exact"),
    ("전체본부", "ATMS#2", [{"system": {"category": "ATMS", "subcategory": "#2"}}], "exact"),
    ("전체본부", "ATMSDB", [{"system": {"category": "ATMS", "subcategory": "DB"}}], "exact"),
    ("전체본부", "통합 ATMS", [{"system": {"category": "ATMS", "subcategory": "통합"}}], "rule"),
    (None, "교통센터", [{"system": {"category": "교통센터"}}], "exact"),
])
def test_system_targets(catalog, division, text, expected, level):
    targets, decisions = ht.map_targets(division, text, catalog)
    assert targets == expected and decisions[-1]["level"] == level


def test_system_with_division_list_makes_one_target_per_division(catalog):
    targets, decisions = ht.map_targets("수도권, 강원, 경북, 경남본부", "ATMS", catalog)
    assert [t["divisionName"] for t in targets] == ["수도권본부", "강원본부", "대구경북본부", "부산경남본부"]
    assert ("rule", "system.division_list") in rules(decisions)


def test_system_with_system_name_in_division_column_needs_judgment(catalog):
    targets, decisions = ht.map_targets("교통센터", "ATMS 통합 웹", catalog)
    assert targets == [{"system": {"category": "ATMS", "subcategory": "통합 웹"}}]
    assert ("check", "system.division_not_division") in rules(decisions)


def test_system_with_unreadable_division_fails(catalog):
    targets, decisions = ht.map_targets("강원분부", "ATMS", catalog)
    assert targets == [] and ("fail", "system.division_unreadable") in rules(decisions)


@pytest.mark.parametrize("division,text,expected,rule", [
    (None, "양산지사 전체터널", [{"branchName": "양산지사"}], "branch.whole"),
    ("충남본부", "당진지사", [{"branchName": "당진지사"}], "branch.whole"),
    (None, "경북본부 전체 터널", [{"divisionName": "대구경북본부"}], "division.whole"),
    (None, "수도권 전체 터널", [{"divisionName": "수도권본부"}], "division.whole"),
    (None, "전남본부", [{"divisionName": "광주전남본부"}], "division.whole"),
])
def test_branch_and_division_patterns_are_rules(catalog, division, text, expected, rule):
    targets, decisions = ht.map_targets(division, text, catalog)
    assert targets == expected and rules(decisions) == [("rule", rule)]


def test_leftover_text_after_division_needs_judgment(catalog):
    targets, decisions = ht.map_targets(None, "강원본부 단터널", catalog)
    assert targets == [{"divisionName": "강원본부"}]
    assert rules(decisions) == [("check", "division.partial_text")]


def test_tunnels_in_parentheses_after_branch_are_mapped(catalog):
    targets, decisions = ht.map_targets("대구경북본부", "영천지사(달전,와촌)", catalog)
    assert targets == [{"tunnelCode": "020159"}, {"tunnelCode": "020150"}]
    assert rules(decisions) == [("rule", "tunnel.in_branch_list")]


def test_unknown_parenthesized_tunnel_falls_back_to_branch_as_check(catalog):
    targets, decisions = ht.map_targets(None, "영천지사(없는)", catalog)
    assert targets == [{"branchName": "영천지사"}]
    assert rules(decisions) == [("check", "branch.partial_text")]


def test_division_name_inside_tunnel_list(catalog):
    targets, decisions = ht.map_targets(None, "남정5, 강원", catalog)
    assert targets == [{"tunnelCode": "065330"}, {"divisionName": "강원본부"}]
    assert ("check", "division.in_list") in rules(decisions)


def test_all_tunnels_needs_judgment(catalog):
    targets, decisions = ht.map_targets(None, "전체 터널", catalog)
    assert targets == [{"divisionName": d} for d in CATALOG["본부"]]
    assert rules(decisions) == [("check", "all_divisions")]


def test_unknown_or_empty_text_never_guesses(catalog):
    targets, decisions = ht.map_targets("강원본부", "없는터널", catalog)
    assert targets == [] and "없는터널" in decisions[0]["message"]
    assert ht.map_targets("강원본부", None, catalog)[0] == []


def test_partial_failure_keeps_found_part_for_reference(catalog):
    targets, decisions = ht.map_targets("강원본부", "서면1, 없는1", catalog)
    assert targets == []
    partial = [d for d in decisions if d["rule"] == "tunnel.partial"]
    assert partial and partial[0]["to"] == [{"tunnelCode": "060152"}]


@pytest.mark.parametrize("text,codes", [
    ("상동-신어산", ["600007"]),
    ("신어산 상동", ["600007"]),
    ("남정1,2남정5", ["065331", "065330"]),
])
def test_separators(catalog, text, codes):
    assert ht.map_targets(None, text, catalog)[0] == [{"tunnelCode": c} for c in codes]


def test_hyphen_between_names_needs_judgment(catalog):
    targets, decisions = ht.map_targets(None, "남정5-남정2", catalog)
    assert targets == [{"tunnelCode": "065330"}, {"tunnelCode": "065331"}]
    assert ("check", "tunnel.name_hyphen") in rules(decisions)
    # 두 이름이 한 복합 터널이면 구간 여부를 묻지 않는다
    targets, decisions = ht.map_targets(None, "상동-신어산", catalog)
    assert targets == [{"tunnelCode": "600007"}]
    assert "tunnel.name_hyphen" not in [d["rule"] for d in decisions]
    assert "tunnel.name_hyphen" not in [d["rule"] for d in ht.map_targets("경남본부", "양북3-5", catalog)[1]]


def test_full_name_match_does_not_hide_compound_part_in_hinted_division(catalog):
    assert ht.map_targets("전남본부", "서면3-5", catalog)[0] == [{"tunnelCode": "027070"}]
    assert ht.map_targets("강원본부", "서면3", catalog)[0] == [{"tunnelCode": "060154"}]


def test_consistency_checks(catalog):
    found = ht.consistency_checks("강원본부", "", [{"tunnelCode": "045560"}], catalog)
    assert [d["rule"] for d in found] == ["division.mismatch"]
    # O열 장애 내용의 지사와 매핑된 지사가 다르면 입력 오류 가능성을 알린다
    found = ht.consistency_checks("경북본부", "경북본부 군위지사 다부터널 장애", [{"tunnelCode": "065330"}], catalog)
    assert [d["rule"] for d in found] == ["memo.branch_mismatch"]
    # 터널이 없는 옛 지사명(서울산지사)은 대조하지 않는다
    assert ht.consistency_checks(None, "서울산지사 영산터널", [{"tunnelCode": "014400"}], catalog) == []


def test_catalog_file_is_required(tmp_path):
    with pytest.raises(SystemExit, match="get_catalog"):
        ht.load_catalog(tmp_path / "missing.json")
