"""ebid 응답 정규화 — 아는 필드는 한글 키로, 나머지는 원본 그대로 통과(passthrough).

코드→라벨 매핑은 codes.json 한 곳에서 읽는다. 필드 의미·검증 근거는
references/ebid-필드사전.md.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .client import BASE_URL

CODES: dict[str, Any] = json.loads((Path(__file__).with_name("codes.json")).read_text(encoding="utf-8"))
CLASS_LABEL_BY_CODE: dict[str, str] = CODES["발주유형"]
PROG_STS_EXACT: dict[str, str] = CODES["상태정확"]
# 개찰이 끝나 결과를 조회할 수 있는 상태들 (낙찰 확정 전 단계 포함)
PROG_STS_CLOSED = ("낙찰", "유찰", "재공고", "개찰완료", "적격심사중", "협상중")
# 계약방법 코드표 = 사이트 공통코드 PE080*/BID_USE_YN (CTA·CTE·CTH·CTL). PE075* 실시간 조회는 빈 응답이라
# 제거했다(2026-08-30 실측) — 새 코드가 passthrough 로 나타나면 PE080 을 다시 조회해 여기에 추가한다.
CPT_TERMS_LABELS: dict[str, str] = CODES["계약방법"]
AREA_LABELS: dict[str, str] = CODES["지역"]
NOTICE_CONSTANT_FIELDS: set[str] = set(CODES["제외필드"])
DEEPLINK_MENU: dict[str, str] = CODES["딥링크메뉴"]
RESULT_DEEPLINK_MENU: dict[str, str] = CODES["결과딥링크메뉴"]


def build_notice_deeplink(item: dict[str, Any]) -> str:
    """공고 화면(em-sp-bid-noti-*)이 상세로 직행하는 조건은 noti_id·noti_cont_id·noti_no·bid_no·bid_rev
    5개 전부 — 하나라도 빠지면 조용히 목록 화면. g2b/part/remicon 은 화면이 읽지 않아 뺐다(2026-08-30 실측)."""
    menu_id = DEEPLINK_MENU.get(item.get("noti_cls") or "")
    if not menu_id or not item.get("noti_id") or not item.get("noti_cont_id"):
        return ""
    return (f"{BASE_URL}/default.do?menuId={menu_id}"
            f"&noti_id={item.get('noti_id')}&noti_cont_id={item.get('noti_cont_id')}"
            f"&noti_no={item.get('noti_no')}&bid_no={item.get('bid_no') or 1}"
            f"&bid_rev={item.get('bid_rev') or 1}")


def build_result_deeplink(item: dict[str, Any]) -> str:
    """개찰결과 화면(menuId 끝자리 001→002)으로 가는 딥링크. 5개 필수 파라미터는 공고 딥링크와 동일 —
    화면(menuId)만 결과 계열로 바꾼다. 링크 조립 자체는 상태와 무관하게 항상 가능하다(noti_id 등은
    공고 등록 시점에 이미 부여됨) — 상태별로 실제 뭐가 보이는지는 사용자 실측(2026-09-08) 기록만
    남겨둔다. 상태에 따라 링크 자체를 만들지 말지는 나누지 않는다.

    - 낙찰/유찰: 002가 001보다 유효(낙찰자·낙찰률 등은 002에만 있음).
    - 취소공고: 001·002 둘 다 "현재 유효하지 않은 공고"로 뜨고, 취소사유는 001 하단에만 나옴.
      002 쪽 공고번호에는 `-1` 같은 접미번호가 붙는다(내부 식별자 체계 차이로 추정, 원인 미상).
    - 재공고(개찰 전): 002도 열리지만 "본 건은 재공고된 건입니다" 안내 + 이전 차수 참가업체
      정보가 섞여 나올 수 있다 — 최종 결과로 오독하지 않게 주의.
    - 공고중·개찰완료·적격심사중·협상중·정정공고중: 아직 사용자 실측 미완료(2026-09-08 기준)."""
    menu_id = RESULT_DEEPLINK_MENU.get(item.get("noti_cls") or "")
    if not menu_id or not item.get("noti_id") or not item.get("noti_cont_id"):
        return ""
    return (f"{BASE_URL}/default.do?menuId={menu_id}"
            f"&noti_id={item.get('noti_id')}&noti_cont_id={item.get('noti_cont_id')}"
            f"&noti_no={item.get('noti_no')}&bid_no={item.get('bid_no') or 1}"
            f"&bid_rev={item.get('bid_rev') or 1}")

def prog_sts_label(code: str | None) -> str:
    if not code:
        return ""
    # 매핑에 없으면 코드를 그대로 돌려준다. 첫글자로 추측하면 조용히 틀린 라벨이 붙는다
    # (U 계열이 낙찰/유찰/재공고/재입찰중으로 갈리는 것을 놓친 전례가 있다).
    return PROG_STS_EXACT.get(code, code)

def fmt_dt(value: Any) -> str:
    """'202603261400' → '2026-03-26 14:00' (그 외 형식은 그대로)."""
    s = str(value or "")
    if len(s) == 12 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:]}"
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s

def normalize_notice(item: dict[str, Any], cpt_labels: dict[str, str] | None = None) -> dict[str, Any]:
    """아는 필드만 한글 키로 정규화하고, 나머지 원본 필드는 그대로 통과시킨다.

    화이트리스트 방식은 area(지역) 유실 사고의 원인 — 정규화에
    소비되지 않은 필드는 버리지 않고 원본 키 그대로 덧붙인다. 그래야 API 에
    새 필드가 생겨도 자동으로 노출된다. 제외는 NOTICE_CONSTANT_FIELDS 만.
    """
    cpt_labels = CPT_TERMS_LABELS if cpt_labels is None else cpt_labels
    sts = item.get("prog_sts") or ""
    sts_label = prog_sts_label(sts)
    cpt = item.get("cpt_terms") or ""
    area = item.get("area") or ""
    row = {
        "구분": "입찰공고",
        "발주유형": CLASS_LABEL_BY_CODE.get(item.get("noti_cls"), item.get("noti_cls")),
        "공고번호": item.get("noti_no"),
        "공고명": item.get("noti_nm"),
        "지역": AREA_LABELS.get(area, area),
        "지역코드": area,
        "공고일": fmt_dt(item.get("noti_date")),
        "상태": sts_label,
        "상태코드": sts,
        "입찰단계": "사전공개(입찰공고 전)" if sts_label == "사전공개"
        else ("취소됨" if sts_label == "취소공고"
              else ("입찰 마감(결과 조회 가능)" if sts_label in PROG_STS_CLOSED
                    else "입찰 진행 중")),
        "계약방법": cpt_labels.get(cpt, cpt),
        "계약방법코드": cpt,
        "제한유형코드": item.get("lmtcpt_apply_bas_cd") or "",
        "업종": item.get("bid_shpr1") or "",
        "PQ여부": item.get("pq_yn") or "",
        "설계금액원": item.get("dsgng_amt"),
        "입찰마감일시": fmt_dt(item.get("bid_end_dt")),
        "개찰일시": fmt_dt(item.get("open_dt")),
        "차수": item.get("bid_rev"),
        "딥링크": build_notice_deeplink(item),
        "결과딥링크": build_result_deeplink(item),
    }
    consumed = {
        "noti_cls", "noti_no", "noti_nm", "area", "noti_date", "prog_sts",
        "cpt_terms", "lmtcpt_apply_bas_cd", "dsgng_amt", "bid_end_dt", "open_dt",
        "bid_rev", "pq_yn",
        # bid_shpr1_ct/_sv 는 bid_shpr1 과 전 건 동일값(프로파일링 184건) — 업종으로 소비
        "bid_shpr1", "bid_shpr1_ct", "bid_shpr1_sv",
    }
    row.update({k: v for k, v in item.items()
                if k not in consumed and k not in NOTICE_CONSTANT_FIELDS})
    return row

def normalize_contract(item: dict[str, Any]) -> dict[str, Any]:
    """normalize_notice 와 같은 원칙 — 정규화 안 된 원본 필드는 그대로 통과."""
    stl = str(item.get("stl_noti_no") or "")
    row = {
        "구분": "계약",
        "발주유형": CLASS_LABEL_BY_CODE.get(item.get("noti_cls"), item.get("noti_cls")),
        "계약명": item.get("cntr_nm"),
        "체결일": fmt_dt(item.get("cntg_date")),
        "계약방법": item.get("g2b_snd_cpt_terms"),
        "계약금액원": item.get("cntr_amt"),
        "업체명": item.get("com_nm"),
        "사업자번호": item.get("biz_no"),
        "계약번호": stl,
        "연결공고번호": stl[:-2] if len(stl) > 2 else stl,
        # 주관부서 = 실수요 부서("시설처 전기부" 등) — 계약부서(재무부 류 행정 부서)와 구분
        "주관부서": item.get("svsn_dept_nm"),
        "계약부서": item.get("cntr_dept_nm"),
    }
    consumed = {"noti_cls", "cntr_nm", "cntg_date", "g2b_snd_cpt_terms", "cntr_amt",
                "com_nm", "biz_no", "stl_noti_no", "svsn_dept_nm", "cntr_dept_nm"}
    row.update({k: v for k, v in item.items() if k not in consumed})
    return row

def _join_phone(*parts: Any) -> str:
    return "-".join(str(x) for x in parts if x)


def normalize_contract_detail(detail: dict[str, Any]) -> dict[str, Any]:
    """findInfoCntrOpnDetail 응답(6섹션)을 한글 키 한 겹으로 편다.

    bidInfo·cntrBasInfo 가 없는 건(희망수량 등)은 해당 키가 None/"" 로 남는다.
    필드 근거는 references/ebid-필드사전.md §계약 상세 API.
    """
    opn = detail.get("cntrOpnDetail") or {}
    dept = detail.get("deptAddr") or {}
    bid = detail.get("bidInfo") or {}
    bas = detail.get("cntrBasInfo") or {}
    sw = detail.get("getSwYn") or {}
    vendors = detail.get("repVdInfo") or []
    sd, ed = fmt_dt(opn.get("cntr_sd")), fmt_dt(opn.get("cntr_ed"))
    clause, cause = opn.get("jhhm") or "", opn.get("claus_cd_etc_cause") or ""
    return {
        "계약기간": f"{sd}~{ed}" if sd or ed else "",
        "계약일수": opn.get("cntr_day"),
        "발주처": opn.get("poor") or "",
        "수의근거": " — ".join(x for x in (clause, cause) if x),
        "수의근거코드": opn.get("claus_cd") or "",
        "담당자": dept.get("chr_nm") or "",
        "담당부서전화": _join_phone(dept.get("chr_dept_phone_no1"), dept.get("chr_dept_phone_no2"),
                                   dept.get("chr_dept_phone_no3")),
        "담당부서주소": (dept.get("chr_dept_addr") or "").strip(),
        "담당부서우편번호": _join_phone(dept.get("chr_dept_post_no1"), dept.get("chr_dept_post_no2")),
        "계약업체상세": [{
            "업체명": v.get("vd_nm") or "", "대표자": v.get("rep_nm") or "",
            "주소": (v.get("dtl_addr") or "").strip(), "전화": v.get("phone_no") or "",
            "지분율": v.get("shar_rate") or "",
        } for v in vendors],
        # 아래는 bidInfo / cntrBasInfo — 전자수의 포함 대부분 채워짐, 희망수량은 bidInfo 없음
        "설계금액원": bid.get("dsgng_amt"),
        "예정가격원": bas.get("expt_amt"),
        "개찰일시": fmt_dt(bid.get("open_dt")),
        "경쟁방법": bid.get("cpt_terms_str") or "",
        "제한기준": bid.get("lmtcpt_apply_bas_cd_str") or "",
        "낙찰방법": bid.get("stl_terms_str") or "",
        "PQ": bid.get("pq_type_str") or "",
        "공고명": bas.get("noti_nm") or "",
        "공고일": fmt_dt(bas.get("noti_date")),
        "SW계약여부": sw.get("sw_yn") or "",
    }


def print_table(rows: list[dict[str, Any]]) -> None:
    for r in rows:
        if r["구분"] == "입찰공고":
            amt = f"{r['설계금액원']:,}" if r.get("설계금액원") else "-"
            print(f"[{r['발주유형']}] {r['공고번호']} | {r['지역'] or '-'} | {r['공고일']}"
                  f" | {r['상태']} | {r['계약방법']} | 설계 {amt}원 | {r['공고명']}")
        else:
            amt = f"{r['계약금액원']:,}" if r.get("계약금액원") else "-"
            print(f"[계약/{r['발주유형']}] {r['체결일']} | {r['주관부서'] or '-'}"
                  f" | {r['계약방법']} | {amt}원 | 공고 {r['연결공고번호']}"
                  f" | {r['계약명']} | {r['업체명']}")


def _md_escape(text: Any) -> str:
    """마크다운 표 셀·링크 텍스트용 이스케이프 — `|` ·`[`·`]`·`_` 를 보호한다.

    `_` 는 특히 링크 라벨에서 중요하다: Claude Code 터미널이 라벨 안의 이스케이프 안 된
    `_` 를 기울임 시도로 오인해 `[라벨](url)` 링크 문법 전체를 깨고 URL 원문을 그대로
    노출한다(실측, 백틱으로 감싸는 건 효과 없음 — 반드시 `\\_` 이스케이프라야 한다).
    """
    return (str(text or "")
            .replace("|", "\\|")
            .replace("[", "\\[")
            .replace("]", "\\]")
            .replace("_", "\\_"))


def _highlight_html(escaped_name: str, keyword: str | None) -> str:
    """HTML 표용 강조 — 마크다운의 `**` 대신 `<strong>`. 규칙은 `_highlight` 와 같다."""
    kw = _esc(keyword or "").strip()
    if not kw:
        return escaped_name
    return re.sub(f"({re.escape(kw)})", r"<strong>\1</strong>", escaped_name, flags=re.IGNORECASE)


def _highlight(escaped_name: str, keyword: str | None) -> str:
    """이미 이스케이프된 공고명에서 검색어를 굵게 만든다.

    마크다운 링크 라벨 안에서도 강조가 먹는다(`[a **b** c](url)`). 이스케이프를 먼저 하고
    같은 규칙으로 이스케이프한 검색어를 찾는 이유는, `_md_escape` 가 `_`·`[` 를 바꾸면서
    글자 위치가 밀리기 때문이다 — 원문 기준으로 찾으면 엉뚱한 자리에 `**` 가 붙는다.
    대소문자는 구분하지 않는다(ebid 검색 자체가 그렇다).
    """
    kw = _md_escape(keyword or "").strip()
    if not kw:
        return escaped_name
    return re.sub(f"({re.escape(kw)})", r"**\1**", escaped_name, flags=re.IGNORECASE)


def _biz_no(value: Any) -> str:
    """사업자번호 10자리를 000-00-00000 로. 10자리 숫자가 아니면 원문 그대로."""
    digits = str(value or "").strip()
    if len(digits) == 10 and digits.isdigit():
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    return digits or "-"


def _amount(value: Any) -> str:
    return f"{value:,}" if isinstance(value, int) else (str(value) if value else "-")


def _table_title(label: str, keyword: str, period_label: str, n: int) -> str:
    if not keyword:
        what = "전체 계약" if label == "계약" else "전체 공고"
        return f"### [{label}] {what} ({period_label}, {n}건)\n"
    return f"### [{label}] '{keyword}' 검색 결과 ({period_label}, {n}건)\n"


def _empty_line(keyword: str, period_label: str) -> str:
    return (f"'{keyword}' 검색 결과 없음 ({period_label})." if keyword
            else f"검색 결과 없음 ({period_label}, 키워드 없음).")


def render_notice_markdown(rows: list[dict[str, Any]], *, keyword: str, period_label: str) -> str:
    """입찰공고 검색 결과 → 발주유형(공사·용역·물품)별 표. 공고명=공고(001) 딥링크, 상태=결과(002)
    딥링크(개찰 전·취소공고 등 결과가 없는 상태는 링크 없이 텍스트만 — build_result_deeplink 참고)."""
    out: list[str] = []
    for label in ("공사", "용역", "물품"):
        group = [r for r in rows if r.get("발주유형") == label]
        if not group:
            continue
        out.append(_table_title(label, keyword, period_label, len(group)))
        out.append("| 공고번호 | 지역 | 공고명(공고링크) | 설계금액 | 계약방법 | 공고일 | 상태(결과링크) |")
        out.append("|---|---|---|---:|---|---|---|")
        for r in group:
            name = _highlight(_md_escape(r.get("공고명")), keyword)
            link = f"[{name}]({r['딥링크']})" if r.get("딥링크") else name
            sts = _md_escape(r.get("상태"))
            sts_link = f"[{sts}]({r['결과딥링크']})" if r.get("결과딥링크") else sts
            out.append(f"| {r.get('공고번호')} | {_md_escape(r.get('지역'))} | {link} | {_amount(r.get('설계금액원'))}"
                       f" | {_md_escape(r.get('계약방법'))} | {r.get('공고일')} | {sts_link} |")
        out.append("")
    if not out:
        out.append(_empty_line(keyword, period_label))
    return "\n".join(out).rstrip() + "\n"


def render_notice_markdown_compact(rows: list[dict[str, Any]], *, keyword: str, period_label: str) -> str:
    """공고 검색 결과 → 공고일·공고번호·공고명·상태 네 열만. 훑어보기용 요약본.

    상세본과 같은 데이터를 열만 줄여 다시 렌더링한다(검색은 이미 끝났으니 비용은 밀리초).
    공고명=공고(001) 딥링크, 상태=결과(002) 딥링크 — 열이 아니라 링크라 폭을 차지하지 않으면서
    바로 열어볼 수 있다. 발주유형 제목은 유지한다. 열에서 유형을 뺐으므로 제목마저 없애면
    공사·물품 구분이 사라진다.
    """
    out: list[str] = []
    for label in ("공사", "용역", "물품"):
        group = [r for r in rows if r.get("발주유형") == label]
        if not group:
            continue
        out.append(_table_title(label, keyword, period_label, len(group)))
        out.append("| 공고일 | 공고번호 | 공고명(공고링크) | 상태(결과링크) |")
        out.append("|---|---|---|---|")
        for r in group:
            name = _highlight(_md_escape(r.get("공고명")), keyword)
            link = f"[{name}]({r['딥링크']})" if r.get("딥링크") else name
            sts = _md_escape(r.get("상태"))
            sts_link = f"[{sts}]({r['결과딥링크']})" if r.get("결과딥링크") else sts
            out.append(f"| {r.get('공고일')} | {r.get('공고번호')} | {link} | {sts_link} |")
        out.append("")
    if not out:
        out.append(_empty_line(keyword, period_label))
    return "\n".join(out).rstrip() + "\n"


def render_contract_markdown(rows: list[dict[str, Any]], *, keyword: str, period_label: str,
                             detail: bool = False) -> str:
    """계약공개현황 검색 결과 → 단일 표. detail=True 면 `상세` 키의 항목을 열로 덧붙인다."""
    if not rows:
        return _empty_line(keyword, period_label) + "\n"
    out = [_table_title("계약", keyword, period_label, len(rows))]
    if detail:
        out.append("| 구분 | 공고번호 | 계약명 | 계약방법 | 계약업체 | 대표자 | 총계약금액 | 예정가격 | 체결일"
                   " | 계약기간 | 발주처 | 담당자 | 수의근거 |")
        out.append("|---|---|---|---|---|---|---:|---:|---|---|---|---|---|")
    else:
        out.append("| 구분 | 공고번호 | 계약명 | 계약방법 | 사업자번호 | 계약업체 | 총계약금액 | 체결일 |")
        out.append("|---|---|---|---|---|---|---:|---|")
    for r in rows:
        head = (f"| {_md_escape(r.get('발주유형'))} | {r.get('연결공고번호') or '-'} | {_highlight(_md_escape(r.get('계약명')), keyword)}"
                f" | {_md_escape(r.get('계약방법'))}")
        if not detail:
            out.append(f"{head} | {_biz_no(r.get('사업자번호'))} | {_md_escape(r.get('업체명'))}"
                       f" | {_amount(r.get('계약금액원'))} | {r.get('체결일')} |")
            continue
        d = r.get("상세") or {}
        reps = ", ".join(f"{v['대표자']}({v['지분율']})" if v.get("지분율") else v["대표자"]
                         for v in d.get("계약업체상세") or [] if v.get("대표자"))
        contact = d.get("담당자") or ""
        if d.get("담당부서전화"):
            contact = f"{contact} ({d['담당부서전화']})".strip()
        out.append(f"{head} | {_md_escape(r.get('업체명'))} | {_md_escape(reps) or '-'}"
                   f" | {_amount(r.get('계약금액원'))} | {_amount(d.get('예정가격원'))} | {r.get('체결일')}"
                   f" | {d.get('계약기간') or '-'} | {_md_escape(d.get('발주처')) or '-'} | {_md_escape(contact) or '-'}"
                   f" | {_md_escape(d.get('수의근거')) or '-'} |")
    out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---------- HTML (Artifact·브라우저용) ----------
import html as _html

_HTML_STYLE = """<style>
:root{--fg:#1a1a1a;--muted:#666;--line:#ddd;--head:#f3f4f6;--link:#0b57d0;--bg:#fff}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--fg:#e6e6e6;--muted:#9a9a9a;--line:#333;--head:#1f2937;--link:#8ab4f8;--bg:#111}}
:root[data-theme="dark"]{--fg:#e6e6e6;--muted:#9a9a9a;--line:#333;--head:#1f2937;--link:#8ab4f8;--bg:#111}
body{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,"Malgun Gothic",sans-serif;margin:0;padding:20px}
h1{font-size:18px;margin:0 0 4px}h2{font-size:15px;margin:22px 0 8px}
p.meta{color:var(--muted);margin:0 0 14px;font-size:13px}
.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:720px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{background:var(--head);position:sticky;top:0}td.num{text-align:right;white-space:nowrap}td.nw{white-space:nowrap}
a{color:var(--link);text-decoration:none}a:hover{text-decoration:underline}
</style>"""


def _esc(v: Any) -> str:
    return _html.escape(str(v if v is not None else ""))


def _html_doc(title: str, meta: str, sections: list[str]) -> str:
    t, m = _html.escape(title, quote=False), _html.escape(meta, quote=False)  # 본문 텍스트는 따옴표 보존
    return (f"<title>{t}</title>\n{_HTML_STYLE}\n<h1>{t}</h1>\n"
            f"<p class=\"meta\">{m}</p>\n" + "\n".join(sections) + "\n")


def _html_table(headers: list[str], rows: list[list[str]], num_cols: set[int] = frozenset(),
                nowrap_cols: set[int] = frozenset()) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = []
    for r in rows:
        cells = []
        for i, c in enumerate(r):
            cls = " class=\"num\"" if i in num_cols else (" class=\"nw\"" if i in nowrap_cols else "")
            cells.append(f"<td{cls}>{c}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<div class=\"wrap\"><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def render_notice_html(rows: list[dict[str, Any]], *, keyword: str, period_label: str) -> str:
    """입찰공고 검색 결과 → 발주유형별 HTML 표(공고명 = 공고(001) 딥링크 <a>, 상태 = 결과(002) 딥링크 <a>)."""
    sections: list[str] = []
    for label in ("공사", "용역", "물품"):
        group = [r for r in rows if r.get("발주유형") == label]
        if not group:
            continue
        body = []
        for r in group:
            name = _highlight_html(_esc(r.get("공고명")), keyword)
            link = f"<a href=\"{_esc(r['딥링크'])}\" target=\"_blank\" rel=\"noopener\">{name}</a>" if r.get("딥링크") else name
            sts = _esc(r.get("상태"))
            sts_link = (f"<a href=\"{_esc(r['결과딥링크'])}\" target=\"_blank\" rel=\"noopener\">{sts}</a>"
                        if r.get("결과딥링크") else sts)
            body.append([_esc(r.get("공고번호")), _esc(r.get("지역")), link, _esc(_amount(r.get("설계금액원"))),
                         _esc(r.get("계약방법")), _esc(r.get("공고일")), sts_link])
        sections.append(f"<h2>[{_esc(label)}] {len(group)}건</h2>" + _html_table(
            ["공고번호", "지역", "공고명(공고링크)", "설계금액", "계약방법", "공고일", "상태(결과링크)"], body, num_cols={3}, nowrap_cols={0, 5}))
    title = f"'{keyword}' 공고 검색" if keyword else "전체 공고"
    meta = f"기간 {period_label} · 총 {len(rows)}건 · 공고명 클릭 = ebid 상세 (새 탭)"
    if not sections:
        sections.append("<p>검색 결과 없음</p>")
    return _html_doc(title, meta, sections)


def render_contract_html(rows: list[dict[str, Any]], *, keyword: str, period_label: str,
                         detail: bool = False) -> str:
    """계약공개현황 검색 결과 → 단일 HTML 표 (detail=True 면 상세 열 추가)."""
    if detail:
        headers = ["구분", "공고번호", "계약명", "계약방법", "계약업체", "대표자", "총계약금액", "예정가격", "체결일",
                   "계약기간", "발주처", "담당자", "수의근거"]
        num = {6, 7}
    else:
        headers = ["구분", "공고번호", "계약명", "계약방법", "사업자번호", "계약업체", "총계약금액", "체결일"]
        num = {6}
    body = []
    for r in rows:
        head = [_esc(r.get("발주유형")), _esc(r.get("연결공고번호") or "-"),
                _highlight_html(_esc(r.get("계약명")), keyword), _esc(r.get("계약방법"))]
        if not detail:
            body.append(head + [_esc(_biz_no(r.get("사업자번호"))), _esc(r.get("업체명")),
                                _esc(_amount(r.get("계약금액원"))), _esc(r.get("체결일"))])
            continue
        d = r.get("상세") or {}
        reps = ", ".join(f"{v['대표자']}({v['지분율']})" if v.get("지분율") else v["대표자"]
                         for v in d.get("계약업체상세") or [] if v.get("대표자"))
        contact = d.get("담당자") or ""
        if d.get("담당부서전화"):
            contact = f"{contact} ({d['담당부서전화']})".strip()
        body.append(head + [_esc(r.get("업체명")), _esc(reps or "-"), _esc(_amount(r.get("계약금액원"))),
                            _esc(_amount(d.get("예정가격원"))), _esc(r.get("체결일")), _esc(d.get("계약기간") or "-"),
                            _esc(d.get("발주처") or "-"), _esc(contact or "-"), _esc(d.get("수의근거") or "-")])
    title = f"'{keyword}' 계약 검색" if keyword else "전체 계약"
    meta = (f"기간 {period_label}(체결일) · 총 {len(rows)}건 · 건별 링크 없음 — 조회 화면: "
            f"{BASE_URL}/default.do?menuId=NPRO20001")
    section = _html_table(headers, body, num_cols=num, nowrap_cols={1, 8 if detail else 7}) if rows else "<p>검색 결과 없음</p>"
    return _html_doc(title, meta, [section])


def write_output(text: str, out_path: str | None, link_label: str = "링크") -> None:
    """--out 이 있으면 파일에 쓰고 stdout 에는 아무것도 내지 않는다(대화 컨텍스트 절약). 없으면 stdout."""
    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        # 완성된 마크다운 링크를 같이 찍는다 — 호출자가 링크 규칙(절대경로·%20·%28·라벨
        # 이스케이프)을 알 필요 없이 이 줄을 그대로 답변에 복사하면 된다.
        print(f"[ebid] 저장: {p.resolve()}", file=sys.stderr)
        print(f"[ebid] {link_label}: {md_file_link(p.name, p)}", file=sys.stderr)
    else:
        print(text, end="")


def file_url(path: Any) -> str:
    """로컬 경로 → `file:///` URL.

    **먼저 절대경로로 만든다.** 상대경로(`./ebid-out/x.md`)를 그대로 붙이면
    `file:///ebid-out/x.md` 라는 엉뚱한 절대 URL 이 되어 링크가 열리지 않는다 —
    CLI 기본값이 `./ebid-out` 이라 실제로 매니페스트에서 이 사고가 났었다.
    Windows 역슬래시는 `/` 로 바꾸고, UNC(`\\\\server\\share`)는 호스트를 살려 `file://server/share` 로 둔다.
    """
    text = str(Path(path).resolve()).replace("\\", "/")
    if text.startswith("//"):          # UNC — 슬래시 두 개가 호스트 구분자다
        return "file:" + text
    return "file:///" + text.lstrip("/")


def md_file_link(label: Any, path: Any) -> str:
    r"""경로를 마크다운 링크로. 사용자 안내는 백틱 문자열이 아니라 이걸로 준다.

    실측으로 정한 규칙이다(Claude Code 터미널·앱 양쪽에서 조합별로 확인):

    1. URL 을 `<...>` 로 **감싸지 않는다.** CommonMark 는 허용하지만 앱이 감싼 링크를 열지 못한다.
    2. **공백을 `%20` 으로** 인코딩한다. 감싸지 않은 링크 주소는 공백에서 끝나므로, 인코딩하지
       않으면 터미널에서 아예 링크가 되지 않고 원문 그대로 찍힌다(앱은 관대하지만 둘 다 만족시킨다).
       공고명은 거의 다 공백을 포함한다.
    3. **괄호를 `%28`·`%29` 로** 인코딩한다. 마크다운 링크는 `](...)` 라서 파서가 경로 안의 괄호를
       중첩으로 센다. 짝이 맞으면 되감기가 맞아 열리지만, 짝이 안 맞는 `(` 가 하나라도 있으면
       맨 끝 `)` 를 링크 종료가 아니라 경로의 일부로 먹어 경로가 틀어진다.
    4. **라벨의 `[`·`]`·`_` 는 `\[`·`\]`·`\_` 로 이스케이프한다**(`_md_escape`). 특히 `_` —
       이스케이프 안 하면 Claude Code 터미널이 링크 문법 자체를 깨고 URL 원문을 노출한다.
       한글·URL 안의 대괄호는 그대로 둔다 — 양쪽에서 정상이고 읽을 수 있는 편이 낫다.
    """
    url = file_url(path).replace("(", "%28").replace(")", "%29").replace(" ", "%20")
    return f"[{_md_escape(label)}]({url})"


def build_result_filename(kind: str, keyword: str | None, suffix: str = "md", *,
                          variant: str | None = None, stamp: str | None = None) -> str:
    """검색 결과 파일명을 만든다 — `ebid_<공고|계약>_<키워드>_<YYYYMMDD-HHMM>.<확장자>`.

    호출자가 이름을 짓지 않게 하려고 스크립트로 옮겼다. 규칙이 문서와 코드 양쪽에 있으면
    한쪽만 고쳐지는 사고가 난다(링크 문법에서 여러 번 겪었다).

    - 접두사에 괄호를 쓰지 않는다. 링크 URL 의 괄호는 매번 인코딩해야 해서 읽기 어려워진다.
    - 키워드의 공백·경로 금지문자는 `_` 로, 키워드가 없으면 `전체`.
    - 같은 분에 두 번 실행하면 이름이 겹치므로 초까지 붙인다(호출부가 충돌 시 재요청).
    """
    clean = re.sub(r"[^\w가-힣.-]+", "_", str(keyword or "").strip()).strip("_") or "전체"
    stamp = stamp or f"{datetime.now():%Y%m%d-%H%M}"
    tail = f"{variant}_{stamp}" if variant else stamp
    return f"ebid_{kind}_{clean}_{tail}.{suffix}"
