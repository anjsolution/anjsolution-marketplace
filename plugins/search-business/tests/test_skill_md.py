import re
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills/ebid/SKILL.md"
REFERENCES = SKILL.parent / "references"


def test_frontmatter_and_line_length():
    """전체 길이는 재지 않는다.

    행 수 상한(120줄) → 글자 수 상한(10,000자) 순으로 재봤는데 둘 다 우회를 유도했다.
    행 수 때는 한 줄에 규칙을 몰아넣어 345자짜리 줄이 생겼고, 글자 수 때는 기능을 추가할
    때마다 문서를 깎아내는 압박이 생겼다. 문서가 무거워지는 걸 막는 진짜 수단은
    "자주 쓰는 규칙만 SKILL.md, 나머지는 references" 라는 원칙이지 숫자 상한이 아니다.
    줄 길이만 남긴다 — 판단이 안 들어가고, 실제 가독성 사고를 잡는다.
    """
    text = SKILL.read_text(encoding="utf-8")
    fm = text.split("---")[1]
    assert re.search(r"^name: ebid$", fm, re.M)
    assert "description:" in fm and "공고 검색" in fm
    # 줄 길이는 본문만 본다 — 프론트매터 description 은 YAML 스칼라라 줄바꿈이 불가능하다.
    body = text.split("---", 2)[2]
    longest = max(len(l) for l in body.splitlines())
    assert longest <= 300, f"{longest}자짜리 줄 — 한 줄에 규칙을 몰아넣지 말 것"


def test_description_is_yaml_safe():
    """description 이 `*` 로 시작하면 YAML 이 앵커 참조로 읽어 프론트매터가 통째로 깨진다.

    깨지면 스킬 목록에 설명 대신 H1 제목이 뜨고 자동 탐색이 아예 동작하지 않는다 — 실제로
    겪었는데 기존 검사(문자열 포함 여부)로는 잡히지 않았다.
    """
    fm = SKILL.read_text(encoding="utf-8").split("---")[1]
    value = re.search(r"^description:\s*(.+)$", fm, re.M).group(1).strip()
    assert value[0] not in "*&!|>%@`{}[]", f"YAML 특수문자로 시작: {value[:20]!r}"


def test_links_all_references():
    """references 문서가 고아가 되지 않게 SKILL.md 에서 전부 링크되는지만 본다.

    본문 문구를 검사하던 test_rules_present 는 걷어냈다 — "최근 1년"·"kordoc" 같은 표현을
    박제해서 규칙을 references 로 옮기거나 다듬는 것 자체를 막고 있었다. 구조가 깨지는 것은
    막되(링크 누락·프론트매터 파손), 무슨 문장을 쓸지는 강제하지 않는다.
    """
    text = SKILL.read_text(encoding="utf-8")
    for f in REFERENCES.glob("*.md"):
        assert f"references/{f.name}" in text, f"{f.name} 이 SKILL.md 에서 링크되지 않음"
