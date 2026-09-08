import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/ebid/scripts"
sys.path.insert(0, str(SCRIPTS))

import ebid_filter  # noqa: E402

SEARCH_JSON = {
    "검색": {"키워드": "실시설계", "기간": "2025-01-01~2025-12-31",
             "유형": ["공사", "용역", "물품"], "시각": "20260908-2002"},
    "공고": [
        {"발주유형": "용역", "공고번호": "202506507", "공고명": "2025년 건설사업 교통관리시스템 실시설계",
         "지역": "본사", "공고일": "2025-07-02", "상태": "낙찰", "설계금액원": 1018530000,
         "계약방법": "일반경쟁", "딥링크": "https://ebid.ex.co.kr/x", "결과딥링크": "https://ebid.ex.co.kr/y"},
        {"발주유형": "용역", "공고번호": "202502756", "공고명": "장성4터널 등 3개소 환기시설 실시설계",
         "지역": "광주전남본부", "공고일": "2025-03-28", "상태": "취소공고", "설계금액원": 78903000,
         "계약방법": "일반경쟁", "딥링크": "", "결과딥링크": ""},
    ],
    "사전공개": [
        {"발주유형": "물품", "사업명": "광암터널 도로열선시스템 구매", "기관권역": "서울경기본부",
         "공개일": "2026-09-08", "딥링크": "https://ebid.ex.co.kr/z"},
    ],
}


def _write(tmp_path: Path) -> str:
    p = tmp_path / "ebid_검색_실시설계_20260908-2002.json"
    p.write_text(json.dumps(SEARCH_JSON, ensure_ascii=False), encoding="utf-8")
    return str(p)


def test_filter_notices_by_name(tmp_path):
    """이름 열 부분일치가 기본 — '건설' 이 든 공고만 남는다."""
    src = _write(tmp_path)
    assert ebid_filter.main(["--in", src, "--contains", "건설", "--out-dir", str(tmp_path)]) == 0
    # 파일명은 원본 시각을 물려받는다 — 어느 검색에서 나온 결과인지 이름만 봐도 보이게
    out = tmp_path / "ebid_공고_실시설계_filter_건설_20260908-2002.md"
    text = out.read_text(encoding="utf-8")
    assert "202506507" in text and "202502756" not in text
    assert "**건설**" in text                                  # 표 강조는 필터 조건에 걸린다
    assert "'건설' 검색 결과 (2025-01-01~2025-12-31, 1건)" in text  # 기간은 원본 JSON 의 검색 조건에서
    assert "상태(결과링크)" in text                             # 검색 결과와 같은 렌더러


def test_filter_by_other_field_and_kind(tmp_path):
    src = _write(tmp_path)
    assert ebid_filter.main(["--in", src, "--field", "상태", "--contains", "취소",
                             "--out-dir", str(tmp_path)]) == 0
    assert (tmp_path / "ebid_공고_실시설계_filter_취소_20260908-2002.md").exists()

    assert ebid_filter.main(["--in", src, "--kind", "사전공개", "--contains", "터널",
                             "--out-dir", str(tmp_path)]) == 0
    pq = (tmp_path / "ebid_사전공개_실시설계_filter_터널_20260908-2002.md").read_text(encoding="utf-8")
    assert "사업명(사전공개링크) | 기관권역 | 공개일" in pq   # 사전공개는 사전공개 표로 렌더


def test_filter_does_not_overwrite(tmp_path):
    """같은 필터를 다시 돌려도 덮어쓰지 않는다 — 검색 결과 파일 규칙과 같다."""
    src = _write(tmp_path)
    ebid_filter.main(["--in", src, "--contains", "건설", "--out-dir", str(tmp_path)])
    ebid_filter.main(["--in", src, "--contains", "건설", "--out-dir", str(tmp_path)])
    assert (tmp_path / "ebid_공고_실시설계_filter_건설_20260908-2002_2.md").exists()


def test_exit_codes(tmp_path):
    src = _write(tmp_path)
    assert ebid_filter.main(["--in", src, "--contains", "없는키워드", "--out-dir", str(tmp_path)]) == 3
    assert ebid_filter.main(["--in", str(tmp_path / "없다.json"), "--contains", "x"]) == 1
    bad = tmp_path / "rows.json"
    bad.write_text("[]", encoding="utf-8")   # 검색 메타 없는 옛 형식(배열)은 거부
    assert ebid_filter.main(["--in", str(bad), "--contains", "x"]) == 2
