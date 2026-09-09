"""매니페스트 불변식 — 세 곳의 버전·설명이 어긋나면 배포본이 깨진다."""
import json
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]


def _claude():
    return json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))


def _codex():
    return json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))


def _market():
    m = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    return next(e for e in m["plugins"] if e["name"] == "tms")


def test_version_and_description_match_in_all_three():
    c, x, e = _claude(), _codex(), _market()
    assert c["version"] == x["version"] == e["version"], (c["version"], x["version"], e["version"])
    assert c["description"] == x["description"] == e["description"]


def test_keywords_match():
    assert _claude()["keywords"] == _codex()["keywords"] == _market()["keywords"]


def test_plugin_name_is_stable():
    """name 은 설치된 사용자의 슬러그다. 바꾸면 plugin-not-found 가 된다."""
    assert _claude()["name"] == _codex()["name"] == "tms"


def test_claude_marketplace_entry():
    assert _market()["source"] == "./plugins/tms"


def test_codex_marketplace_entry():
    m = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
    e = next(p for p in m["plugins"] if p["name"] == "tms")
    assert e["source"] == {"source": "local", "path": "./plugins/tms"}
    assert e["policy"] == {"installation": "AVAILABLE", "authentication": "ON_USE"}
    assert e["category"] == "Business & Operations"


def test_mcp_manifest_is_wrapped_form():
    """Claude 는 평면형도 읽지만, Codex 가 가리키려면 mcpServers 래핑형이어야 한다."""
    mcp = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
    assert set(mcp) == {"mcpServers"}
    srv = mcp["mcpServers"]["tms-mcp"]
    assert srv["type"] == "http"
    assert srv["url"].startswith("https://")


def test_codex_manifest_points_at_mcp_file():
    x = _codex()
    assert x["mcpServers"] == "./.mcp.json"
    assert (PLUGIN / x["mcpServers"]).exists()
    assert x["skills"] == "./skills/"
    assert (PLUGIN / x["skills"]).is_dir()
