import re
from pathlib import Path

REF = Path(__file__).resolve().parents[1] / "skills/ebid/references"
BAD = ("ebid-ttms", "stages/", "data/ebid-raw", "scripts/ebid/", "20120101",
       "종합관리", "스키마-명세", "T1", "T5", "T6", "S1", "S4", "관리동", "TTMS", "터널사전")


def test_core_files_exist():
    """핵심 3종이 사라지지 않았는지만 본다 — 문서를 새로 추가하는 것은 막지 않는다(부분집합 검사).

    SKILL.md 에서 규칙을 덜어내 references 로 옮기는 게 정상 운영이라, 파일 목록을 정확히
    일치시키면 문서를 추가할 때마다 테스트가 깨진다. 새 파일이 SKILL.md 에서 링크되는지는
    test_skill_md.py 가 glob 으로 본다.
    """
    assert {"ebid-필드사전.md", "문서-판독-지침.md", "소스-접근성.md"} <= {p.name for p in REF.glob("*.md")}


def test_no_project_leak():
    for p in REF.glob("*.md"):
        text = p.read_text(encoding="utf-8")
        for b in BAD:
            assert b not in text, f"{p.name}: {b}"


def test_long_files_have_toc():
    for p in REF.glob("*.md"):
        lines = p.read_text(encoding="utf-8").splitlines()
        if len(lines) > 100:
            head = "\n".join(lines[:15])
            assert re.search(r"^## (목차|Contents)", head, re.M), f"{p.name} needs TOC"


def test_no_ct_mt_jargon_in_prose():
    # 코드 표기(`CT`)는 허용, 산문 속 "CT/MT" 금지
    for p in REF.glob("*.md"):
        text = p.read_text(encoding="utf-8")
        assert "CT/MT" not in text and "MT/CT" not in text, p.name
