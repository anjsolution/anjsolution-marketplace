"""SKILL.md 프론트매터가 폴더명과 어긋나면 스킬이 잘못된 이름으로 노출된다."""
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SKILLS = sorted(d for d in (PLUGIN / "skills").iterdir() if d.is_dir())


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} 프론트매터 없음"
    body = text.split("---\n", 2)[1]
    out = {}
    for line in body.splitlines():
        if ": " in line and not line.startswith(" "):
            k, v = line.split(": ", 1)
            out[k] = v
    return out


def test_expected_skills_present():
    assert [d.name for d in SKILLS] == ["catalog", "incidents"]


def test_frontmatter_name_matches_directory():
    for d in SKILLS:
        assert _frontmatter(d / "SKILL.md")["name"] == d.name


def test_description_is_trigger_oriented():
    """설명이 없거나 짧으면 모델이 스킬을 못 고른다."""
    for d in SKILLS:
        desc = _frontmatter(d / "SKILL.md")["description"]
        assert len(desc) > 80, (d.name, len(desc))
        assert "트리거" in desc, d.name
