import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/ebid/scripts"
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from _ebid import pqstd  # noqa: E402


class _FakeResponse:
    status_code = 200

    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeSession:
    def __init__(self, data=None):
        self.data = data if data is not None else []
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "payload": json, "headers": headers})
        return _FakeResponse(self.data)


class _FakeClient:
    timeout_seconds = 30

    def __init__(self, data=None):
        self.session = _FakeSession(data)

    def ensure_csrf_token(self):
        return "x-csrf-token", "TOKEN"


def test_payload_omits_usergubun():
    """`usergubun` 을 실으면 키워드 검색이 2.5~3.1초로 고정 지연된다 — 빼도 결과가 같아서 뺐다.

    화면은 "C" 를 보내므로 무심코 되돌리기 쉬운 자리다(실측 근거는 pqstd.py 독스트링).
    """
    client = _FakeClient()
    pqstd.fetch_pqstd_list(client, notice_class="SV", from_date="20250908",
                           to_date="20260908", keyword="실시설계")
    payload = client.session.calls[0]["payload"]
    assert "usergubun" not in payload
    assert payload == {"s_write_date": "20250908", "e_write_date": "20260908",
                       "cls": "SV", "biz_nm": "실시설계"}


def test_keyword_is_optional_and_menucode_follows_class():
    client = _FakeClient()
    pqstd.fetch_pqstd_list(client, notice_class="MT", from_date="20260101", to_date="20260908")
    call = client.session.calls[0]
    assert "biz_nm" not in call["payload"]            # 키워드 없으면 필터 자체를 안 보낸다
    assert call["headers"]["menucode"] == "NPRO13003"  # 물품 사전공개 화면
    assert call["url"].endswith("/ui/sp/expro/pqstd/findListPqstd.do")


def test_construction_class_is_rejected():
    """공사(CT)는 사전공개 메뉴 자체가 없다 — 조용히 빈 결과를 주지 말고 오류로 알린다."""
    with pytest.raises(ValueError, match="용역·물품"):
        pqstd.fetch_pqstd_list(_FakeClient(), notice_class="CT",
                               from_date="20260101", to_date="20260908")


def test_non_list_response_becomes_empty():
    client = _FakeClient(data={"error": "x"})
    assert pqstd.fetch_pqstd_list(client, notice_class="SV",
                                  from_date="20260101", to_date="20260908") == []
