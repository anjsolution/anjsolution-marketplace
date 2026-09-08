"""구매규격 사전공개(pqstd) 목록 조회 — 입찰공고 전 단계의 규격 공개 건.

입찰공고 API(`findListBidNoti.do`)와 **완전히 다른 계열**이다. 식별자도 다르고(공고는 UUID 2개+
번호 3종, 여기는 `spec_id` UUID 하나) 발주유형도 용역·물품만 있다(공사는 사전공개 메뉴 자체가 없음).

실측(2026-09-08):
- `cls` 는 필수 — 생략하거나 null 이면 200 이지만 빈 배열이 온다. 유형별로 따로 호출해야 한다.
- `biz_nm` 을 실으면 서버가 사업명으로 필터한다(공고 검색의 `noti_nm` 과 같은 역할).
- **`usergubun` 은 보내지 않는다.** 화면은 항상 `"C"` 를 보내는데, `biz_nm`(키워드)과 같이 실으면
  응답이 **2.5~3.1초**로 고정 지연된다(건수·기간과 무관 — 0건도 2.5초). 빼면 **0.1~0.8초**.
  결과는 완전히 같다: SV/MT × 키워드 5종 × 기간별 7개 조합에서 `spec_id` 집합 전부 일치
  (0건·24건·74건·188건·288건 케이스 포함, 2026-09-08 실측). 서버가 사용자구분과 이름검색을
  같이 받으면 비싼 경로를 타는 것으로 보이나 원인은 미상.
- 목록 응답에 예산액은 없다 — `asgn_budget_amt` 는 상세 API(`findInfoPqstdDetail.do`)에만 있고,
  그건 건당 요청 1회가 더 든다. 목록 검색에서는 목록이 주는 것만 낸다.
"""

from __future__ import annotations

from typing import Any

from .client import BASE_URL, DEFAULT_URL, EbidClient

PQSTD_LIST_PATH = "/ui/sp/expro/pqstd/findListPqstd.do"
PQSTD_LIST_URL = BASE_URL + PQSTD_LIST_PATH
# 사전공개 화면 메뉴코드 — 공고(*001)·결과(*002) 에 이어지는 *003 계열. 공사(CT)는 없다.
PQSTD_CLASS_MENU_CODES: dict[str, str] = {"SV": "NPRO12003", "MT": "NPRO13003"}
PQSTD_CLASS_LABELS: dict[str, str] = {"용역": "SV", "물품": "MT"}


def fetch_pqstd_list(
    client: EbidClient,
    *,
    notice_class: str,
    from_date: str,
    to_date: str,
    keyword: str = "",
) -> list[dict[str, Any]]:
    """사전공개 목록 조회. notice_class 는 SV/MT (CT 는 사전공개가 없어 ValueError)."""
    cls = str(notice_class).strip().upper()
    menu_code = PQSTD_CLASS_MENU_CODES.get(cls)
    if not menu_code:
        raise ValueError(f"사전공개가 없는 발주유형입니다: {notice_class} (용역·물품만 가능)")
    csrf_header_name, csrf_token = client.ensure_csrf_token()
    # usergubun 은 일부러 뺀다 — 화면은 "C" 를 보내지만 키워드와 같이 실으면 20배 느려진다(독스트링)
    payload: dict[str, Any] = {
        "s_write_date": from_date,
        "e_write_date": to_date,
        "cls": cls,
    }
    if keyword:
        payload["biz_nm"] = keyword
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE_URL,
        "Referer": DEFAULT_URL,
        "menucode": menu_code,
        csrf_header_name: csrf_token,
    }
    response = client.session.post(
        PQSTD_LIST_URL, json=payload, headers=headers, timeout=client.timeout_seconds)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else []
