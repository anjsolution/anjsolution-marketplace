"""장애 history 셀 해석 규칙 — 장애코드(D), 조치코드(K), 대응 경과(P), 일시(E·L).

다른 history_* 스크립트가 공용으로 쓰는 라이브러리다. 직접 실행하지 않는다.
해석할 때마다 판정 기록(decision)을 남긴다. 판정 수준은 다음 네 가지다.

  exact : 원문 그대로 해석됨
  rule  : 정해진 규칙으로 바뀜(별칭, 범위 전개 등). 결정적이지만 원문과 다르므로 요약에 보인다
  check : 등록은 가능하지만 사람이(AI 에이전트가) 판단해야 함
  fail  : 이 상태로는 등록할 수 없음
"""
import re
from datetime import datetime, timedelta

EXACT, RULE, CHECK, FAIL = "exact", "rule", "check", "fail"
LEVELS = (EXACT, RULE, CHECK, FAIL)

CATEGORY = {"S": "SOFTWARE", "H": "HARDWARE", "N": "NETWORK", "E": "ENVIRONMENTAL"}
LOCATION = {"L": "ADMIN_SERVER", "M": "TUNNEL_ADMIN", "R": "TUNNEL_DEVICE"}
DEVICE = {"1": "SERVER", "2": "NETWORK", "3": "CONTROLLER", "4": "OTHER"}
SUBTYPE = {"1": "VMS", "2": "LCS", "3": "VDS", "4": "CCTV", "5": "BROADCAST",
           "6": "EMERGENCY_PHONE", "7": "MANUAL_FIRE", "8": "OTHER"}
# 조치코드 4자리: 대상·방법·접근·유형. 방법 O(Other, 운영미숙 포함)는 2026-09-28 서버 반영.
ACTION = (("target", {"S": "SERVER", "N": "NETWORK", "M": "CONTROLLER", "O": "OTHER"}),
          ("method", {"E": "CONFIG", "R": "REBOOT", "P": "PATCH", "C": "REPLACE", "F": "REPAIR",
                      "O": "OTHER"}),
          ("access", {"A": "WIRED", "B": "REMOTE", "C": "ONSITE"}),
          ("type", {"H": "HARDWARE", "S": "SOFTWARE"}))

# 도구 입력 제한 (tms-mcp 스키마)
LIMITS = {"memo": 4000, "content": 4000, "cause": 4000, "remarks": 4000,
          "receiverName": 50, "reporterName": 50, "responderName": 50, "resolverName": 50,
          "reporterOrganization": 100}
RESPONSES_PER_CALL = 20

# "15:59 내용", "6/21 16:48 내용", "24/12/31 17:24 내용", "- 14:46 내용"
LINE_TIME = re.compile(
    r"^[\s\-○•·*]*(?:(?:(?P<y>\d{4}|\d{2})[-./])?(?P<m>\d{1,2})[-./](?P<d>\d{1,2})\s+)?"
    r"(?P<H>\d{1,2}):(?P<M>\d{2})\s*(?P<text>.*)$")
EMPTY_PROGRESS = {"없음", "-", "ㅇㅇ"}
KST_AT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?\+09:00$")


def decision(field, level, rule, source, result, message):
    return {"field": field, "level": level, "rule": rule, "from": source, "to": result,
            "message": message}


def text(value):
    value = None if value is None else str(value).strip()
    return value or None


def kst(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S+09:00") if isinstance(dt, datetime) else None


def parse_kst(value):
    """원본 추출 JSON의 일시 문자열(+09:00) → naive datetime. 해석 못 하면 None."""
    if isinstance(value, datetime):
        return value
    value = text(value)
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S+09:00", "%Y-%m-%dT%H:%M+09:00", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


# ── 장애코드 (D열) ───────────────────────────────────────────────────

def incident_code_fields(code):
    """코드 하나 → 분류 4필드. 해석 못 한 칸은 None."""
    code = (code or "").upper().strip()
    out = {"category": CATEGORY.get(code[:1]), "location": LOCATION.get(code[1:2]),
           "deviceCategory": DEVICE.get(code[2:3]), "controllerSubType": None}
    if out["deviceCategory"] == "CONTROLLER":
        out["controllerSubType"] = SUBTYPE.get(code[3:4])
    return out


def is_valid_incident_code(code):
    code = (code or "").upper().strip()
    out = incident_code_fields(code)
    return bool(re.fullmatch(r"[A-Z]{2}\d{3}", code)) and None not in (
        out["category"], out["location"], out["deviceCategory"]) and (
        out["deviceCategory"] != "CONTROLLER" or out["controllerSubType"] is not None)


def parse_incident_code(raw):
    """D열 → (분류 필드, [decision])."""
    source = text(raw)
    codes = [c.strip() for c in re.split(r"[,/\s]+", (source or "").upper()) if c.strip()]
    if not codes:
        return incident_code_fields(""), [decision(
            "incident.code", FAIL, "incident_code.missing", source, None, "D열 장애코드 없음")]
    first = codes[0]
    fields = incident_code_fields(first)
    if not is_valid_incident_code(first):
        return fields, [decision("incident.code", FAIL, "incident_code.invalid", source, first,
                                 f"D열 장애코드 '{source}' 해석 불가")]
    if len(codes) > 1:
        return fields, [decision("incident.code", CHECK, "incident_code.multiple", source, first,
                                 f"D열에 코드가 여러 개({', '.join(codes)}) — 첫 코드 {first}로 분류함")]
    return fields, [decision("incident.code", EXACT, "incident_code.exact", source, first, "")]


# ── 조치코드 (K열) ───────────────────────────────────────────────────

def action_code_fields(code):
    code = (code or "").upper().strip()
    return {key: table.get(code[i:i + 1]) if len(code) > i else None
            for i, (key, table) in enumerate(ACTION)}


def is_valid_action_code(code):
    code = (code or "").upper().strip()
    return len(code) == 4 and None not in action_code_fields(code).values()


def parse_action_code(raw):
    """K열 → (조치 분류 필드, [decision])."""
    source = text(raw)
    fields = action_code_fields(source)
    if not source or source in {"-", "--"}:
        return fields, [decision("resolution.code", FAIL, "action_code.missing", source, None,
                                 f"K열 조치코드 없음{'' if not source else f"('{source}')"} — 조치가 있는데 분류를 정할 수 없음")]
    missing = [k for k, v in fields.items() if v is None]
    if len(source) != 4 or missing:
        return fields, [decision("resolution.code", FAIL, "action_code.invalid", source, None,
                                 f"K열 조치코드 '{source}'의 {', '.join(missing) or '길이'} 해석 불가")]
    return fields, [decision("resolution.code", EXACT, "action_code.exact", source, source.upper(), "")]


# ── 대응 경과 (P열) ──────────────────────────────────────────────────

def split_progress(raw, received, handler):
    """P열 → (responses, [decision]). 시각 없는 줄은 앞 기록에 이어 붙인다."""
    source = text(raw)
    decisions, responses = [], []
    if not source:
        return responses, decisions
    if source in EMPTY_PROGRESS:
        return responses, [decision("responses", RULE, "progress.placeholder", source, [],
                                    f"P열 '{source}' — 대응 기록 없음으로 처리")]
    merged = 0
    for line in source.splitlines():
        if not line.strip():
            continue
        m = LINE_TIME.match(line)
        if m and received:
            year = int(m["y"]) if m["y"] else received.year
            year += 2000 if year < 100 else 0
            month = int(m["m"]) if m["m"] else received.month
            day = int(m["d"]) if m["d"] else received.day
            if not m["y"] and month == 12 and received.month == 1:
                year -= 1
                decisions.append(decision("responses", CHECK, "progress.year_rollover", line.strip(),
                                          f"{year}-{month:02d}-{day:02d}",
                                          f"연초 접수건의 12월 경과를 전년({year})으로 해석함"))
            try:
                at = kst(datetime(year, month, day, int(m["H"]), int(m["M"])))
            except ValueError:
                decisions.append(decision("responses", FAIL, "progress.bad_time", line.strip(), None,
                                          f"P열 대응 경과 시각 오류: '{line.strip()}'"))
                at = None
            responses.append({"responseAt": at, "content": text(m["text"]) or line.strip(),
                              "responderName": handler})
        elif responses:
            responses[-1]["content"] += "\n" + line.strip()
            merged += 1
        else:
            responses.append({"responseAt": None, "content": line.strip(), "responderName": handler})
            decisions.append(decision("responses", FAIL, "progress.no_time", line.strip(), None,
                                      "P열 대응 경과 첫 줄에 시각 없음 — responseAt을 정해야 함"))
    if merged:
        decisions.append(decision("responses", RULE, "progress.continuation", None, merged,
                                  f"시각 없는 줄 {merged}개를 앞 대응 기록에 이어 붙임"))
    return responses, decisions


def time_order_checks(received, resolved, responses):
    """일시 선후 이상을 check로 알린다 (입력 오타 탐지)."""
    out = []
    if received and resolved and resolved < received:
        out.append(decision("resolution.resolvedAt", CHECK, "time.resolved_before_received",
                            kst(resolved), None, f"복구일자({kst(resolved)})가 접수일자보다 이름"))
    if received and resolved and resolved - received > timedelta(days=30):
        out.append(decision("resolution.resolvedAt", CHECK, "time.long_duration", kst(resolved), None,
                            f"접수부터 복구까지 {(resolved - received).days}일 — 연·월 오타 확인"))
    for i, r in enumerate(responses):
        at = parse_kst(r.get("responseAt"))
        if not at:
            continue
        if received and at < received - timedelta(days=3):
            out.append(decision(f"responses[{i}]", CHECK, "time.response_before_received",
                                r["responseAt"], None, "대응 일시가 접수 3일 이상 전 — 날짜 오타 확인"))
        if resolved and at > resolved + timedelta(days=1):
            out.append(decision(f"responses[{i}]", CHECK, "time.response_after_resolved",
                                r["responseAt"], None, "대응 일시가 복구 1일 이상 후 — 날짜 오타 확인"))
    return out


def length_checks(prefix, values):
    """도구 입력 길이 제한을 넘는 값을 fail로 알린다."""
    out = []
    for key, value in values.items():
        limit = LIMITS.get(key)
        if limit and isinstance(value, str) and len(value) > limit:
            out.append(decision(f"{prefix}.{key}", FAIL, "length.exceeded", len(value), limit,
                                f"{prefix}.{key} {len(value)}자 — 최대 {limit}자"))
    return out
