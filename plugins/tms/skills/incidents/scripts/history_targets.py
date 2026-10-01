"""장애 history의 F열(본부)·G열(터널명) 원문 → create_incident 공개 식별자 targets.

다른 history_* 스크립트가 공용으로 쓰는 라이브러리다. 직접 실행하지 않는다.
기준은 catalog 스킬의 캐시(get_catalog 응답 원본, 기본 ~/.anjsolution/tms/catalog.json)다.
표기 해석 규칙(복합·범위 표기, 본부·터널 별칭, 시스템 별칭)은 이관 도구(tms/error-history)를 따른다.
이관 도구의 부분 문자열·앞 두 글자 재검색은 자동 매핑에 쓰지 않고 후보로만 알린다.

매핑마다 판정 기록을 남긴다(수준은 history_rules 참고). 대표 규칙:
  tunnel.exact              정식명 또는 복합 터널 구성명과 정확히 일치          exact
  tunnel.expanded           '금사4,5'·'양북3-5' 같은 압축·범위 표기를 전개      rule
  tunnel.alias              터널 별칭(양북→문무대왕 등)                       rule
  tunnel.narrowed           동명 터널을 F열 본부로 하나로 좁힘                 rule
  tunnel.in_branch_list     '영천지사(달전,와촌)'의 괄호 속 터널을 그 지사에서 찾음 rule
  branch.whole / division.whole  'OO지사 전체터널'·'OO본부'                   rule
  branch.partial_text / division.partial_text  지사·본부 뒤 글자를 해석 못 하고 전체로 매핑  check
  all_divisions             '전체 터널' → 모든 본부                          check
  system.exact / system.alias   시스템 대상(ATMS 등)                          exact / rule
  division.mismatch         F열 본부와 터널의 현재 소속이 다름                  check
  memo.branch_mismatch      O열 장애 내용에 적힌 지사가 매핑 결과와 다름         check
  tunnel.not_found / tunnel.ambiguous / … 등록 불가                           fail
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from history_rules import CHECK, EXACT, FAIL, RULE, decision

DEFAULT_CATALOG = Path.home() / ".anjsolution" / "tms" / "catalog.json"
UNASSIGNED = "(미지정)"

# 엑셀 표기 → 실제 명칭 (이관 도구 data_loader.py)
DIVISION_ALIASES = {
    "경남본부": "부산경남본부", "경남": "부산경남본부", "부산경남": "부산경남본부",
    "충남본부": "대전충남본부", "충남": "대전충남본부", "대전충청본부": "대전충남본부",
    "경북본부": "대구경북본부", "경북": "대구경북본부",
    "전남본부": "광주전남본부", "전남": "광주전남본부", "공주전남본부": "광주전남본부",
}
TUNNEL_NAME_ALIASES = {"양북": "문무대왕", "백두대간인제": "인제양양", "별교": "벌교"}
# 대문자·공백 1칸으로 정규화한 G열 원문 → (대분류, 중분류)
SYSTEM_ALIASES = {"ATMS#2": ("ATMS", "#2"), "통합 ATMS": ("ATMS", "통합"),
                  "ATMS 통합 웹": ("ATMS", "통합 웹"), "ATMSDB": ("ATMS", "DB")}
# F열에서 '특정 본부 없음'을 뜻하는 값 — 시스템 대상은 전체 본부(본부 생략)가 된다
ALL_DIVISION_WORDS = {"전체본부", "전체 본부", "전체", "각본부", "본부"}
REGIONS = {"경남", "충남", "경북", "전남", "강원", "전북", "충북", "수도권"}
# 지사·본부 이름 뒤에 붙어도 '전체'를 뜻하는 말
WHOLE_WORDS = re.compile(r"^(전체|관내|전\s*터널|터널|TTMS|ttms|\s)*$")


def load_catalog(path=None):
    path = Path(path) if path else DEFAULT_CATALOG
    if not path.exists():
        sys.exit(f"카탈로그 캐시가 없습니다: {path}\n"
                 "MCP get_catalog 응답을 이 경로에 그대로 저장한 뒤 다시 실행하세요 (catalog 스킬).")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "시스템분류" not in data:
        sys.exit(f"카탈로그 캐시에 시스템분류가 없습니다: {path}\n"
                 "2026-09-28 이전 형식입니다. get_catalog를 다시 호출해 캐시를 교체하세요.")
    return Catalog(data)


def compact(name):
    """비교 키: 끝의 '터널'과 모든 공백을 뺀다."""
    return re.sub(r"터널$", "", (name or "").strip()).replace(" ", "")


class Catalog:
    def __init__(self, data):
        self.version = data.get("version")
        self.divisions = [d for d in data.get("본부", {}) if d != UNASSIGNED]
        self.branches = {}
        self.tunnels = []
        for division, d in data.get("본부", {}).items():
            for branch, b in d.get("지사", {}).items():
                if branch != UNASSIGNED:
                    self.branches[branch] = division
                for name, leaf in b.get("터널", {}).items():
                    self.tunnels.append({"name": name, "code": leaf["코드"],
                                         "division": division, "branch": branch})
        self.by_code = {t["code"]: t for t in self.tunnels}
        self.by_full = defaultdict(list)
        self.by_part = defaultdict(list)
        self.by_joined = defaultdict(list)  # '수리,수암터널' → '수리수암'
        self.tunnel_count = defaultdict(int)
        for t in self.tunnels:
            self.tunnel_count[t["branch"]] += 1
            self.by_full[compact(t["name"])].append(t)
            if "," in t["name"]:
                self.by_joined[compact(t["name"]).replace(",", "")].append(t)
            for part in re.sub(r"터널$", "", t["name"]).split(","):
                if part.strip():
                    self.by_part[compact(part)].append(t)
        self.systems = data.get("시스템분류", {})

    def division(self, name):
        """본부명(별칭 포함) → (정식명 또는 None, 별칭을 썼는지)."""
        name = (name or "").strip()
        real = DIVISION_ALIASES.get(name, name)
        return (real, real != name) if real in self.divisions else (None, False)

    def find_tunnels(self, token):
        """토큰 → (터널 목록, 방법). 방법은 None(정확 일치)·'alias:양북→문무대왕'·'joined'."""
        key = compact(token)
        found = _unique(self.by_full.get(key, []) + self.by_part.get(key, []))
        if found:
            return found, None
        if key in self.by_joined:
            return _unique(self.by_joined[key]), "joined"
        for alias, real in TUNNEL_NAME_ALIASES.items():
            if alias in key:
                found, _ = self.find_tunnels(key.replace(alias, real))
                return found, (f"alias:{alias}→{real}" if found else None)
        return [], None

    def substring_matches(self, token):
        """토큰이 이름 일부로 들어 있는 터널 (쉼표 무시). 자동 확정하지 않는 후보다."""
        key = compact(token)
        if len(key) < 2:
            return []
        return _unique([t for t in self.tunnels if key in compact(t["name"]).replace(",", "")])

    def suggest(self, token):
        """자동 매핑하지 않는 느슨한 후보 (부분 문자열, 앞 두 글자)."""
        key = compact(token)
        found = self.substring_matches(token)
        if not found and len(key) >= 2 and "가" <= key[0] <= "힣":
            found = self.by_part.get(key[:2], [])
        return [label(t) for t in _unique(found)[:5]]

    def system(self, raw):
        """G열 원문 → ((대분류, 중분류), 별칭을 썼는지) 또는 (None, False)."""
        norm = re.sub(r"\s+", " ", (raw or "").strip()).upper()
        for root, children in self.systems.items():
            if norm == root.upper():
                return (root, None), False
            for child in children:
                if norm in (f"{root} {child}".upper(), f"{root}{child}".upper()):
                    return (root, child), False
        if norm in SYSTEM_ALIASES:
            root, child = SYSTEM_ALIASES[norm]
            if root in self.systems and (child is None or child in self.systems[root]):
                return (root, child), True
        return None, False


def _unique(tunnels):
    seen, out = set(), []
    for t in tunnels:
        if t["code"] not in seen:
            seen.add(t["code"])
            out.append(t)
    return out


def label(t):
    return f"{t['name']}({t['branch']}, {t['code']})"


# ── 표기 파싱 (이관 도구 tunnel_parser.py) ─────────────────────────────

def normalize_name(name):
    result = " ".join((name or "").split())
    result = re.sub(r"터널$", "", result)
    result = re.sub(r"([가-힣])\s+(\d)", r"\1\2", result)
    return result.strip()


def split_input(raw):
    """쉼표+공백, 쉼표+한글, 공백+한글, 슬래시에서 나눈다. 쉼표+숫자는 압축 표기로 둔다."""
    parts = []
    for chunk in (raw or "").split("/"):
        # 숫자 바로 뒤 한글('매현1,2탄용')과 이름 사이 하이픈('슬치-오도재')도 구분자로 본다
        chunk = re.sub(r"(?<=\d)(?=[가-힣])", ",", chunk.strip())
        chunk = re.sub(r"(?<=[가-힣\d])\s*[-~]\s*(?=[가-힣])", ",", chunk)
        for part in re.split(r",\s*(?=[가-힣])|,\s+|\s+(?=[가-힣])", chunk):
            if part.strip():
                parts.append(part.strip())
    return parts


def base_and_numbers(raw):
    """'기린1,2,3' → ('기린', [1,2,3]), '양북3-5' → ('양북', [3,4,5]), '삼마치' → ('삼마치', [])"""
    raw = re.sub(r"터널$", "", raw or "")
    raw = re.sub(r"\([^)]*\)", "", raw)
    raw = re.sub(r"([가-힣])\s+(\d)", r"\1\2", raw).strip()
    m = re.match(r"^([가-힣]+)(\d+)[-~](\d+)$", raw)
    if m:
        return m.group(1), list(range(int(m.group(2)), int(m.group(3)) + 1))
    m = re.match(r"^([가-힣]+)(\d+(?:,\d+)+)$", raw)
    if m:
        return m.group(1), [int(n) for n in m.group(2).split(",")]
    m = re.match(r"^([가-힣]+)(\d+)$", raw)
    if m:
        return m.group(1), [int(m.group(2))]
    if re.match(r"^[가-힣]+$", raw):
        return raw, []
    return None, []


def expand(token):
    token = normalize_name(token)
    base, numbers = base_and_numbers(token)
    if base and numbers:
        return [f"{base}{n}" for n in numbers]
    return [base] if base else ([token] if token else [])


def parse_complex(raw):
    """'강진4, 장동, 강진2,3' → ['강진4','장동','강진2','강진3'], '금사4, 5' → ['금사4','금사5']"""
    result, last_base = [], None
    for token in split_input(re.sub(r"터널$", "", raw or "")):
        if re.match(r"^\d", token):
            if not last_base:
                result.append(token)
                continue
            m = re.match(r"^(\d+)[-~](\d+)$", token)
            numbers = range(int(m.group(1)), int(m.group(2)) + 1) if m else \
                [int(n) for n in re.findall(r"\d+", token)]
            result.extend(f"{last_base}{n}" for n in numbers)
        else:
            result.extend(expand(token))
            base, _ = base_and_numbers(token)
            last_base = base or last_base
    return result


def is_all_tunnels(raw):
    if "본부" in raw or "지사" in raw:
        return False
    return raw.replace(" ", "").lower() in {"전체터널", "전체ttms", "전체터널ttms"}


def division_pattern(raw):
    """'충북본부 …' / '경북 전체 …' → (본부 표기, 나머지 글자)."""
    m = re.match(r"^([가-힣]+본부)(.*)$", raw) if "본부" in raw else None
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"^([가-힣]{2,3})\s*(전체.*)$", raw)
    if m and m.group(1) in REGIONS:
        return f"{m.group(1)}본부", m.group(2)
    return None, None


def branch_pattern(raw):
    """'양산지사 전체터널' → ('양산지사', ' 전체터널')."""
    m = re.match(r"^([가-힣]+지사)(.*)$", raw) if "지사" in raw else None
    return (m.group(1), m.group(2)) if m else (None, None)


# ── 매핑 ────────────────────────────────────────────────────────────

FIELD = "incident.targets"


def _source(division_text, tunnel_text):
    return {"F": division_text, "G": tunnel_text}


def map_targets(division_text, tunnel_text, catalog, memo=None):
    """F열·G열 원문(+O열 장애 내용) → (targets, [decision]). fail이 있으면 targets는 빈 목록이다."""
    raw = (str(tunnel_text).strip() if tunnel_text is not None else "")
    src = _source(division_text, tunnel_text)
    if not raw:
        return [], [decision(FIELD, FAIL, "target.empty", src, None, "G열 터널명 없음")]
    hint_raw = (str(division_text).strip() if division_text is not None else "")
    hint, _ = catalog.division(hint_raw) if hint_raw else (None, False)

    if is_all_tunnels(raw):
        targets = [{"divisionName": d} for d in catalog.divisions]
        return targets, [decision(FIELD, CHECK, "all_divisions", src, targets,
                                  f"G열 '{raw}' — 모든 본부({len(targets)}곳)를 대상으로 함")]

    name, rest = division_pattern(raw)
    if name:
        real, aliased = catalog.division(name)
        if not real:
            return [], [decision(FIELD, FAIL, "division.not_found", src, None,
                                 f"G열 '{raw}': 본부 '{name}'을(를) 카탈로그에서 찾지 못함")]
        targets = [{"divisionName": real}]
        if WHOLE_WORDS.match(rest):
            return targets, [decision(FIELD, RULE, "division.whole", src, targets,
                                      f"본부 단위 대상 {real}" + (f" (별칭 {name})" if aliased else ""))]
        return targets, [decision(FIELD, CHECK, "division.partial_text", src, targets,
                                  f"G열 '{raw}' — '{rest.strip()}'을(를) 해석하지 않고 {real} 전체로 매핑함")]

    if "," in raw and "지사" in raw and "(" not in raw:
        cleaned = re.sub(r"(전체|관내)?\s*터널$", "", raw).strip()
        branches = []
        for part in (p.strip() for p in cleaned.split(",")):
            candidate = re.sub(r"\s*(전체|관내).*$", "", part if "지사" in part else f"{part}지사").strip()
            if candidate in catalog.branches and candidate not in branches:
                branches.append(candidate)
        if branches:
            targets = [{"branchName": b} for b in branches]
            return targets, [decision(FIELD, RULE, "branch.list", src, targets,
                                      f"지사 단위 대상 {', '.join(branches)}")]

    name, rest = branch_pattern(raw)
    if name:
        if name not in catalog.branches:
            return [], [decision(FIELD, FAIL, "branch.not_found", src, None,
                                 f"G열 '{raw}': 지사 '{name}'을(를) 카탈로그에서 찾지 못함")]
        inner = re.fullmatch(r"\s*\(([^)]*)\)\s*", rest or "")
        if inner:
            targets, decisions = _map_tunnel_list(inner.group(1), catalog, src,
                                                  branch=name, hint=None, memo=None)
            if targets:
                return targets, decisions
            fallback = [{"branchName": name}]
            return fallback, [decision(
                FIELD, CHECK, "branch.partial_text", src, fallback,
                f"G열 '{raw}' — 괄호 속 터널을 {name}에서 찾지 못해 지사 전체로 매핑함: "
                + "; ".join(d["message"] for d in decisions))]
        targets = [{"branchName": name}]
        if WHOLE_WORDS.match(rest):
            return targets, [decision(FIELD, RULE, "branch.whole", src, targets, f"지사 단위 대상 {name}")]
        return targets, [decision(FIELD, CHECK, "branch.partial_text", src, targets,
                                  f"G열 '{raw}' — '{rest.strip()}'을(를) 해석하지 않고 {name} 전체로 매핑함")]

    real, aliased = catalog.division(raw)
    if real:
        targets = [{"divisionName": real}]
        return targets, [decision(FIELD, RULE, "division.whole", src, targets,
                                  f"본부 단위 대상 {real}" + (f" (별칭 {raw})" if aliased else ""))]
    if raw in catalog.branches:
        targets = [{"branchName": raw}]
        return targets, [decision(FIELD, RULE, "branch.whole", src, targets, f"지사 단위 대상 {raw}")]

    targets, decisions = _map_tunnel_list(raw, catalog, src, branch=None, hint=hint, memo=memo)
    if targets:
        return targets, decisions

    (system, sys_aliased) = catalog.system(raw)
    if system:
        root, child = system
        target = {"system": {"category": root, **({"subcategory": child} if child else {})}}
        name = f"{root}" + (f" > {child}" if child else "")
        extra, targets = [], [target]
        if hint_raw and hint_raw not in ALL_DIVISION_WORDS:
            listed = [catalog.division(p.strip())[0] or catalog.division(p.strip() + "본부")[0]
                      for p in re.split(r"[,/]", hint_raw) if p.strip()]
            if hint:
                target["divisionName"] = hint
            elif len(listed) > 1 and None not in listed:
                targets = [{**target, "divisionName": d} for d in dict.fromkeys(listed)]
                extra.append(decision(FIELD, RULE, "system.division_list", src, targets,
                                      f"F열 본부 목록 '{hint_raw}' → 본부마다 {name} 대상"))
            elif catalog.system(hint_raw)[0]:
                extra.append(decision(FIELD, CHECK, "system.division_not_division", src, targets,
                                      f"F열 '{hint_raw}'는 본부가 아니라 시스템명 — 적용 본부 없이(전체 본부) 매핑함"))
            else:
                return [], [decision(FIELD, FAIL, "system.division_unreadable", src, None,
                                     f"F열 본부 '{hint_raw}' 해석 불가 — 시스템 대상의 적용 본부를 정할 수 없음")]
        scope = ", ".join(t.get("divisionName") or "전체 본부" for t in targets)
        if sys_aliased:
            return targets, extra + [decision(FIELD, RULE, "system.alias", src, targets,
                                              f"시스템 대상 {name} (별칭 '{raw}'), 적용 {scope}")]
        return targets, extra + [decision(FIELD, EXACT, "system.exact", src, targets,
                                          f"시스템 대상 {name}, 적용 {scope}")]
    return [], decisions


def _map_tunnel_list(raw, catalog, src, branch, hint, memo=None):
    """복합·범위 표기를 토큰으로 나눠 대상으로. 하나라도 확정 못 하면 ([], 판정들).

    1차: 정확 일치·별칭·붙여 쓴 복합명·F열 본부로 좁히기. 2차: 남은 동명 토큰을 같은 칸에서
    확정된 터널의 본부나 O열 장애 내용의 지사로 좁히고, 이름 일부로 후보가 하나뿐인 토큰을
    채운다. 2차로 채운 것은 check로 남겨 에이전트가 판단하게 한다.
    """
    tokens = parse_complex(raw) or [normalize_name(raw)]
    literal = [normalize_name(p) for p in split_input(re.sub(r"터널$", "", raw))]
    expanded = tokens != literal
    resolved, notes, pending = {}, [], []   # resolved: token → tunnel 또는 {"divisionName"}
    for token in tokens:
        division, aliased = catalog.division(token)
        if not division:
            division, aliased = catalog.division(token + "본부")[0], True
        if division and not branch:
            resolved[token] = {"divisionName": division}
            notes.append(decision(FIELD, CHECK, "division.in_list", src, division,
                                  f"G열 목록 속 '{token}'을(를) 본부 {division} 전체 대상으로 봄"))
            continue
        found, how = catalog.find_tunnels(token)
        if branch:
            found = [t for t in found if t["branch"] == branch]
        if hint and len(found) > 1:
            narrowed = [t for t in found if t["division"] == hint]
            if len(narrowed) == 1:
                notes.append(decision(FIELD, RULE, "tunnel.narrowed", src, narrowed[0]["code"],
                                      f"'{token}' 동명 터널 {len(found)}곳 중 F열 본부({hint})의 "
                                      f"{label(narrowed[0])}로 좁힘"))
            found = narrowed or found
        if len(found) == 1:
            resolved[token] = found[0]
            if how and how.startswith("alias:"):
                notes.append(decision(FIELD, RULE, "tunnel.alias", src, found[0]["code"],
                                      f"'{token}' 별칭 {how[6:]} 적용 → {label(found[0])}"))
            elif how == "joined":
                notes.append(decision(FIELD, RULE, "tunnel.joined", src, found[0]["code"],
                                      f"'{token}'을(를) 붙여 쓴 복합 터널명으로 봄 → {label(found[0])}"))
        else:
            pending.append((token, found))

    # 2차: 문맥으로 좁히기
    context = {t["division"] for t in resolved.values() if "code" in t}
    memo_hits = set(memo_branches(memo, catalog)) if memo else set()
    fails = []
    for token, found in pending:
        loose = False
        if not found:
            found = [t for t in catalog.substring_matches(token) if not branch or t["branch"] == branch]
            loose = True
        pick, why = None, None
        if len(found) == 1 and loose:
            pick, why = found[0], "이름 일부가 일치하는 후보가 하나뿐"
        elif len(found) > 1:
            by_ctx = [t for t in found if t["division"] in context]
            by_memo = [t for t in found if t["branch"] in memo_hits]
            if len(by_memo) == 1:
                pick, why = by_memo[0], f"O열 장애 내용의 지사({by_memo[0]['branch']})로 좁힘"
            elif len(by_ctx) == 1:
                pick, why = by_ctx[0], f"같은 칸의 다른 터널 소속({by_ctx[0]['division']})으로 좁힘"
        if pick:
            resolved[token] = pick
            rule = "tunnel.substring_unique" if loose and len(found) == 1 else "tunnel.narrowed_by_context"
            notes.append(decision(FIELD, CHECK, rule, src, pick["code"],
                                  f"'{token}' → {label(pick)} ({why}) — 맞는지 판단 필요"
                                  + (f"; 다른 후보: {', '.join(label(t) for t in found if t is not pick)}"
                                     if len(found) > 1 else "")))
        elif found and not loose:
            fails.append(decision(FIELD, FAIL, "tunnel.ambiguous", src, [label(t) for t in found],
                                  f"G열 '{src['G']}'의 '{token}': 같은 이름의 터널이 여러 곳 — "
                                  f"{', '.join(label(t) for t in found)}. 본부·장애 내용으로도 구분되지 않음"))
        else:
            where = f" ({branch} 안)" if branch else ""
            hints = [label(t) for t in found[:5]] if found else catalog.suggest(token)
            fails.append(decision(FIELD, FAIL, "tunnel.not_found", src, hints,
                                  f"G열 '{src['G']}'의 '{token}': 카탈로그에 없는 터널{where}"
                                  + (f" (후보: {', '.join(hints)})" if hints else "")))

    targets = []
    for token in tokens:
        item = resolved.get(token)
        if item is None:
            continue
        target = {"tunnelCode": item["code"]} if "code" in item else item
        if target not in targets:
            targets.append(target)
    if fails:
        if targets:  # 일부만 찾은 경우 에이전트가 참고하도록 남긴다
            fails.append(decision(FIELD, FAIL, "tunnel.partial", src, targets,
                                  f"G열 '{src['G']}' 중 일부만 찾음 — 전체를 확정할 때까지 대상 비움"))
        return [], fails + [n for n in notes if n["level"] == CHECK]
    hyphen = re.search(r"[가-힣]+\d*\s*[-~]\s*[가-힣]+\d*", raw)
    tunnel_codes = {t["tunnelCode"] for t in targets if "tunnelCode" in t}
    if hyphen and len(tunnel_codes) > 1:  # 두 이름이 한 복합 터널이면 구간 여부를 따질 필요가 없다
        notes.append(decision(FIELD, CHECK, "tunnel.name_hyphen", src, targets,
                              f"'{hyphen.group(0)}'을(를) 두 터널로 봄 — 구간(사이 터널 포함) 표기일 수 있음"))
    if branch:
        notes.insert(0, decision(FIELD, RULE, "tunnel.in_branch_list", src, targets,
                                 f"{branch} 괄호 속 터널 {len(tokens)}개를 그 지사에서 찾음"))
    elif expanded:
        notes.insert(0, decision(FIELD, RULE, "tunnel.expanded", src, tokens,
                                 f"G열 '{src['G']}' → {', '.join(tokens)}"))
    if not notes:
        notes.append(decision(FIELD, EXACT, "tunnel.exact", src, targets, ""))
    return targets, notes


def consistency_checks(division_text, memo, targets, catalog):
    """매핑 결과를 F열 본부·O열 장애 내용과 대조한다 (등록은 막지 않고 check로 알림)."""
    out = []
    hint_raw = str(division_text).strip() if division_text is not None else ""
    hint, _ = catalog.division(hint_raw) if hint_raw else (None, False)
    tunnels = [catalog.by_code[t["tunnelCode"]] for t in targets if t.get("tunnelCode") in catalog.by_code]
    if hint:
        for t in tunnels:
            if t["division"] != hint:
                out.append(decision(FIELD, CHECK, "division.mismatch", hint_raw, t["division"],
                                    f"F열 본부 '{hint_raw}'와 {t['name']}의 현재 소속({t['division']})이 다름"
                                    " — 조직 개편 또는 입력 오류 확인"))
    mapped_branches = {t["branch"] for t in tunnels} | {t["branchName"] for t in targets if "branchName" in t}
    mentioned = memo_branches(memo, catalog)
    if mapped_branches and mentioned and not set(mentioned) & mapped_branches:
        out.append(decision(FIELD, CHECK, "memo.branch_mismatch", mentioned, sorted(mapped_branches),
                            f"O열 장애 내용의 지사({', '.join(mentioned)})와 매핑된 지사"
                            f"({', '.join(sorted(mapped_branches))})가 다름 — 대상 확인"))
    return out


def memo_branches(memo, catalog):
    """O열 장애 내용에 적힌 지사 중 현재 터널이 있는 지사 (터널 없는 옛 지사명은 뺀다)."""
    return [b for b in dict.fromkeys(re.findall(r"([가-힣]{2,4}지사)", memo or ""))
            if catalog.tunnel_count.get(b)]
