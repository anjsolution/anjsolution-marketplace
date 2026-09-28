"""장애 history 엑셀의 F열(본부)·G열(터널명) 원문을 create_incident 공개 식별자 targets로 바꾼다.

기준은 catalog 스킬의 캐시(get_catalog 응답 원본, ~/.anjsolution/tms/catalog.json)다.
표기 해석 규칙(복합·범위 표기, 본부·터널 별칭, 시스템 대상 별칭)은 이관 도구
(tms/error-history src/mapper)의 규칙을 따른다. 단, 이관 도구의 부분 문자열·앞 두 글자
재검색은 자동 매핑에 쓰지 않고 후보로만 알린다. 해석이 하나로 정해지지 않으면 targets를
비우고 사유를 돌려준다 — 추측해 채우지 않는다.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

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
        self.by_full = defaultdict(list)
        self.by_part = defaultdict(list)
        for t in self.tunnels:
            self.by_full[compact(t["name"])].append(t)
            for part in re.sub(r"터널$", "", t["name"]).split(","):
                if part.strip():
                    self.by_part[compact(part)].append(t)
        self.systems = data.get("시스템분류", {})

    def division(self, name):
        name = (name or "").strip()
        name = DIVISION_ALIASES.get(name, name)
        return name if name in self.divisions else None

    def find_tunnels(self, token):
        key = compact(token)
        # 정식명 일치에서 멈추면 다른 본부의 복합 터널 구성명(예: 구례 '서면5,서면4,서면3')을 놓친다
        found = self.by_full.get(key, []) + self.by_part.get(key, [])
        if not found:
            for alias, real in TUNNEL_NAME_ALIASES.items():
                if alias in key:
                    return self.find_tunnels(key.replace(alias, real))
        return _unique(found)

    def suggest(self, token):
        """자동 매핑하지 않는 느슨한 후보 (부분 문자열, 앞 두 글자)."""
        key = compact(token)
        found = [t for t in self.tunnels if key and key in compact(t["name"]).replace(",", "")]
        if not found and len(key) >= 2 and "가" <= key[0] <= "힣":
            found = self.by_part.get(key[:2], [])
        return [_label(t) for t in _unique(found)[:5]]

    def system(self, text):
        norm = re.sub(r"\s+", " ", (text or "").strip()).upper()
        pairs = [SYSTEM_ALIASES[norm]] if norm in SYSTEM_ALIASES else []
        for root, children in self.systems.items():
            if norm == root.upper():
                pairs.append((root, None))
            for child in children:
                if norm in (f"{root} {child}".upper(), f"{root}{child}".upper()):
                    pairs.append((root, child))
        for root, child in pairs:
            if root in self.systems and (child is None or child in self.systems[root]):
                return root, child
        return None


def _unique(tunnels):
    seen, out = set(), []
    for t in tunnels:
        if t["code"] not in seen:
            seen.add(t["code"])
            out.append(t)
    return out


def _label(t):
    return f"{t['name']}({t['branch']}, {t['code']})"


# ── 표기 파싱 (이관 도구 tunnel_parser.py) ─────────────────────────────

def normalize_name(name):
    result = " ".join((name or "").split())
    result = re.sub(r"터널$", "", result)
    result = re.sub(r"([가-힣])\s+(\d)", r"\1\2", result)
    return result.strip()


def split_input(text):
    """쉼표+공백, 쉼표+한글, 공백+한글, 슬래시에서 나눈다. 쉼표+숫자는 압축 표기로 둔다."""
    parts = []
    for chunk in (text or "").split("/"):
        for part in re.split(r",\s+|,(?=[가-힣])|\s+(?=[가-힣])", chunk.strip()):
            if part.strip():
                parts.append(part.strip())
    return parts


def base_and_numbers(text):
    """'기린1,2,3' → ('기린', [1,2,3]), '양북3-5' → ('양북', [3,4,5]), '삼마치' → ('삼마치', [])"""
    text = re.sub(r"터널$", "", text or "")
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"([가-힣])\s+(\d)", r"\1\2", text).strip()
    m = re.match(r"^([가-힣]+)(\d+)[-~](\d+)$", text)
    if m:
        return m.group(1), list(range(int(m.group(2)), int(m.group(3)) + 1))
    m = re.match(r"^([가-힣]+)(\d+(?:,\d+)+)$", text)
    if m:
        return m.group(1), [int(n) for n in m.group(2).split(",")]
    m = re.match(r"^([가-힣]+)(\d+)$", text)
    if m:
        return m.group(1), [int(m.group(2))]
    if re.match(r"^[가-힣]+$", text):
        return text, []
    return None, []


def expand(token):
    token = normalize_name(token)
    base, numbers = base_and_numbers(token)
    if base and numbers:
        return [f"{base}{n}" for n in numbers]
    return [base] if base else ([token] if token else [])


def parse_complex(text):
    """'강진4, 장동, 강진2,3' → ['강진4','장동','강진2','강진3'], '금사4, 5' → ['금사4','금사5']"""
    result, last_base = [], None
    for token in split_input(re.sub(r"터널$", "", text or "")):
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


def is_all_tunnels(text):
    if "본부" in text or "지사" in text:
        return False
    return text.replace(" ", "").lower() in {"전체터널", "전체ttms", "전체터널ttms"}


def division_pattern(text):
    m = re.match(r"^([가-힣]+본부)", text) if "본부" in text else None
    if m:
        return m.group(1)
    m = re.match(r"^([가-힣]{2,3})\s*전체", text)
    if m and m.group(1) in REGIONS:
        return f"{m.group(1)}본부"
    return None


def branch_pattern(text):
    m = re.match(r"^([가-힣]+지사)", text) if "지사" in text else None
    return m.group(1) if m else None


# ── 매핑 ────────────────────────────────────────────────────────────

def map_targets(division_text, tunnel_text, catalog):
    """F열·G열 원문 → (targets, problems). problems가 있으면 targets는 빈 목록이다."""
    text = (str(tunnel_text).strip() if tunnel_text is not None else "")
    if not text:
        return [], ["G열 터널명 없음"]
    hint_raw = (str(division_text).strip() if division_text is not None else "")
    hint = catalog.division(hint_raw) if hint_raw else None

    if is_all_tunnels(text):
        return [{"divisionName": d} for d in catalog.divisions], []
    name = division_pattern(text)
    if name:
        division = catalog.division(name)
        return ([{"divisionName": division}], []) if division else \
            ([], [f"G열 '{text}': 본부 '{name}'을(를) 카탈로그에서 찾지 못함"])
    if "," in text and "지사" in text:
        cleaned = re.sub(r"(전체|관내)?\s*터널$", "", text).strip()
        branches = []
        for part in (p.strip() for p in cleaned.split(",")):
            candidate = re.sub(r"\s*(전체|관내).*$", "", part if "지사" in part else f"{part}지사").strip()
            if candidate in catalog.branches and candidate not in branches:
                branches.append(candidate)
        if branches:
            return [{"branchName": b} for b in branches], []
    name = branch_pattern(text)
    if name:
        return ([{"branchName": name}], []) if name in catalog.branches else \
            ([], [f"G열 '{text}': 지사 '{name}'을(를) 카탈로그에서 찾지 못함"])
    if catalog.division(text):
        return [{"divisionName": catalog.division(text)}], []
    if text in catalog.branches:
        return [{"branchName": text}], []

    targets, problems = [], []
    for token in parse_complex(text) or [normalize_name(text)]:
        found = catalog.find_tunnels(token)
        narrowed = [t for t in found if t["division"] == hint] if hint else []
        found = narrowed or found
        if len(found) == 1:
            target = {"tunnelCode": found[0]["code"]}
            if target not in targets:
                targets.append(target)
        elif found:
            problems.append(f"G열 '{text}'의 '{token}': 같은 이름의 터널이 여러 곳 — "
                            f"{', '.join(_label(t) for t in found)}. F열 본부로 구분되지 않음")
        else:
            hint_text = catalog.suggest(token)
            problems.append(f"G열 '{text}'의 '{token}': 카탈로그에 없는 터널"
                            + (f" (후보: {', '.join(hint_text)})" if hint_text else ""))
    if not problems:
        return targets, []

    system = catalog.system(text)
    if system:
        root, child = system
        target = {"system": {"category": root, **({"subcategory": child} if child else {})}}
        if hint_raw and hint_raw not in ALL_DIVISION_WORDS:
            if not hint:
                return [], [f"F열 본부 '{hint_raw}' 해석 불가 — 시스템 대상의 적용 본부를 정할 수 없음"]
            target["divisionName"] = hint
        return [target], []
    return [], problems


def division_notes(division_text, targets, catalog):
    """F열 본부와 매핑된 터널의 현재 소속이 다르면 경고한다 (등록을 막지는 않음).

    터널코드는 하나로 확정됐으므로 대상 자체는 맞다. 조직 개편(예: 수도권→서울경기) 흔적이
    대부분이지만 입력 오류일 수도 있어 검토자에게 알린다.
    """
    hint_raw = str(division_text).strip() if division_text is not None else ""
    hint = catalog.division(hint_raw) if hint_raw else None
    if not hint:
        return []
    by_code = {t["code"]: t for t in catalog.tunnels}
    notes = []
    for target in targets:
        tunnel = by_code.get(target.get("tunnelCode"))
        if tunnel and tunnel["division"] != hint:
            notes.append(f"F열 본부 '{hint_raw}'와 {tunnel['name']}의 현재 소속({tunnel['division']})이 다름"
                         " — 조직 개편 또는 입력 오류 확인")
    return notes
