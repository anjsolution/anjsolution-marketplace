"""엑셀 F열(본부)·G열(터널명) 원문 → create_incident 공개 식별자 targets 매핑 규칙."""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/incidents/scripts"
spec = importlib.util.spec_from_file_location("excel_targets", SCRIPTS / "excel_targets.py")
et = importlib.util.module_from_spec(spec)
sys.modules["excel_targets"] = et
spec.loader.exec_module(et)


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
        "광주전남본부": {"지사": {"구례지사": {"터널": {
            "서면1터널": leaf("027030"), "서면5,서면4,서면3터널": leaf("027070")}}}},
        "대구경북본부": {"지사": {"청송지사": {"터널": {
            "남정5터널": leaf("065330"), "남정1 ,남정2터널": leaf("065331")}}}},
        "대전충남본부": {"지사": {"당진지사": {"터널": {}}}},
        "부산경남본부": {"지사": {
            "경주지사": {"터널": {"문무대왕3,문무대왕4,문무대왕5,오천1터널": leaf("065020")}},
            "양산지사": {"터널": {"상동,신어산터널": leaf("600007")}},
        }},
        "서울경기본부": {"지사": {"이천지사": {"터널": {"금사4,금사5터널": leaf("045560")}}}},
        "수도권본부": {"지사": {}},
    },
    "시스템분류": {"ATMS": ["통합", "통합 웹", "#2", "DB"], "교통센터": [], "폴스타": [],
                 "통합플랫폼": [], "미분류": []},
}


@pytest.fixture
def catalog():
    return et.Catalog(CATALOG)


def test_short_tunnel_name_maps_to_code(catalog):
    assert et.map_targets("대구경북본부", "남정5", catalog) == ([{"tunnelCode": "065330"}], [])


@pytest.mark.parametrize("division,text,code", [
    ("서울경기본부", "금사4,5", "045560"),
    ("강원본부", "동산1,2 북방1", "060110"),
    ("강원본부", "동산1-2, 북방1터널", "060110"),
    ("경남본부", "양북3-5", "065020"),
    ("대구경북본부", "남정2", "065331"),
])
def test_compound_and_alias_inputs_collapse_to_one_tunnel(catalog, division, text, code):
    assert et.map_targets(division, text, catalog) == ([{"tunnelCode": code}], [])


def test_same_name_tunnel_uses_division_or_goes_to_review(catalog):
    assert et.map_targets("강원본부", "서면1", catalog) == ([{"tunnelCode": "060152"}], [])
    assert et.map_targets("전남본부", "서면1", catalog) == ([{"tunnelCode": "027030"}], [])
    targets, problems = et.map_targets(None, "서면1", catalog)
    assert targets == []
    assert "여러" in problems[0] and "060152" in problems[0] and "027030" in problems[0]


@pytest.mark.parametrize("division,text,expected", [
    ("전체본부", "ATMS", [{"system": {"category": "ATMS"}}]),
    (None, "ATMS", [{"system": {"category": "ATMS"}}]),
    ("강원본부", "ATMS", [{"system": {"category": "ATMS"}, "divisionName": "강원본부"}]),
    ("경북본부", "ATMS 통합 웹", [{"system": {"category": "ATMS", "subcategory": "통합 웹"},
                               "divisionName": "대구경북본부"}]),
    ("전체본부", "ATMS#2", [{"system": {"category": "ATMS", "subcategory": "#2"}}]),
    ("전체본부", "통합 ATMS", [{"system": {"category": "ATMS", "subcategory": "통합"}}]),
    (None, "교통센터", [{"system": {"category": "교통센터"}}]),
])
def test_system_targets(catalog, division, text, expected):
    assert et.map_targets(division, text, catalog) == (expected, [])


def test_system_target_with_unreadable_division_goes_to_review(catalog):
    targets, problems = et.map_targets("수도권, 강원, 경북, 경남본부", "ATMS", catalog)
    assert targets == [] and "F열" in problems[0]


@pytest.mark.parametrize("division,text,expected", [
    (None, "양산지사 전체터널", [{"branchName": "양산지사"}]),
    ("충남본부", "당진지사", [{"branchName": "당진지사"}]),
    (None, "경북본부 전체 터널", [{"divisionName": "대구경북본부"}]),
    (None, "수도권 전체 터널", [{"divisionName": "수도권본부"}]),
    (None, "전남본부", [{"divisionName": "광주전남본부"}]),
])
def test_branch_and_division_patterns(catalog, division, text, expected):
    assert et.map_targets(division, text, catalog) == (expected, [])


def test_all_tunnels_means_every_division(catalog):
    targets, problems = et.map_targets(None, "전체 터널", catalog)
    assert problems == []
    assert targets == [{"divisionName": d} for d in CATALOG["본부"]]


def test_unknown_or_empty_text_never_guesses(catalog):
    targets, problems = et.map_targets("강원본부", "없는터널", catalog)
    assert targets == [] and "없는터널" in problems[0]
    assert et.map_targets("강원본부", None, catalog) == ([], ["G열 터널명 없음"])


def test_partial_failure_in_compound_reports_and_maps_nothing(catalog):
    targets, problems = et.map_targets("강원본부", "서면1, 없는1", catalog)
    assert targets == [] and "없는1" in problems[0]


def test_components_written_apart_map_exactly(catalog):
    assert et.map_targets("부산경남본부", "신어산 상동", catalog) == ([{"tunnelCode": "600007"}], [])


def test_fuzzy_candidates_are_only_suggested(catalog):
    # 이관 도구는 앞 두 글자(상동)로 자동 매핑했지만, 스킬은 후보로만 제시한다
    targets, problems = et.map_targets("부산경남본부", "상동신어산", catalog)
    assert targets == []
    assert "600007" in problems[0] and "후보" in problems[0]


def test_catalog_file_is_required(tmp_path):
    with pytest.raises(SystemExit, match="get_catalog"):
        et.load_catalog(tmp_path / "missing.json")


def test_full_name_match_does_not_hide_compound_part_in_hinted_division(catalog):
    # 강원 양양의 '서면3터널'(정식명)만 보고 멈추면 전남 구례의 복합 터널을 놓친다
    assert et.map_targets("전남본부", "서면3-5", catalog) == ([{"tunnelCode": "027070"}], [])
    assert et.map_targets("강원본부", "서면3", catalog) == ([{"tunnelCode": "060154"}], [])
    targets, problems = et.map_targets(None, "서면3", catalog)
    assert targets == [] and "060154" in problems[0] and "027070" in problems[0]


def test_division_mismatch_is_a_warning_not_a_block(catalog):
    targets, problems = et.map_targets("강원본부", "금사4,5", catalog)
    assert (targets, problems) == ([{"tunnelCode": "045560"}], [])
    assert et.division_notes("강원본부", targets, catalog) == [
        "F열 본부 '강원본부'와 금사4,금사5터널의 현재 소속(서울경기본부)이 다름 — 조직 개편 또는 입력 오류 확인"]
    assert et.division_notes("경북본부", [{"tunnelCode": "065330"}], catalog) == []
    assert et.division_notes(None, targets, catalog) == []
