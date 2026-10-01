"""검토·수정한 등록 초안을 현재 값으로 다시 판정하고 도구별 요청 본문을 만든다 (3단계).

  python history_validate.py drafts.json [--catalog 카탈로그.json] > requests.json

history_map.py 출력(또는 그 drafts 배열)을 받는다. 저장된 ready·blockers는 믿지 않고 값을 다시 본다.
매핑 단계의 checks는 에이전트가 판단을 마치고 초안에 "checksReviewed": true를 적어야 통과한다.

출력 requests는 null을 뺀 도구 입력이다. idempotency_key와 incidentCode는 등록할 때 붙인다.
대응 기록은 도구 1회 최대 건수로 나눈 목록(add_incident_responses)이다.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import history_rules as hr  # noqa: E402
import history_targets as ht  # noqa: E402

TARGET_KEYS = {"divisionName", "branchName", "tunnelCode", "deviceId", "system"}


def clean(value):
    """요청 본문에서 null을 뺀다 (선택 항목은 null 대신 생략해야 한다)."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def check_targets(targets, catalog):
    if not isinstance(targets, list) or not targets:
        return ["incident.targets 비어 있음 — 대상이 하나 이상 필요"]
    problems = []
    for i, t in enumerate(targets):
        at = f"targets[{i}]"
        if not isinstance(t, dict) or not t:
            problems.append(f"{at} 비어 있음")
            continue
        extra = sorted(set(t) - TARGET_KEYS)
        if extra:
            problems.append(f"{at} 지원하지 않는 필드 {extra} — 공개 식별자만 사용")
            continue
        if "system" in t and set(t) - {"system", "divisionName"}:
            problems.append(f"{at} 시스템 대상에는 divisionName만 함께 지정할 수 있음")
        if "divisionName" in t and t["divisionName"] not in catalog.divisions:
            problems.append(f"{at}.divisionName '{t['divisionName']}' 카탈로그에 없음")
        if "branchName" in t and t["branchName"] not in catalog.branches:
            problems.append(f"{at}.branchName '{t['branchName']}' 카탈로그에 없음")
        if "tunnelCode" in t and t["tunnelCode"] not in catalog.by_code:
            problems.append(f"{at}.tunnelCode '{t['tunnelCode']}' 카탈로그에 없음")
        if "system" in t:
            s = t["system"] if isinstance(t["system"], dict) else {}
            category, sub = s.get("category"), s.get("subcategory")
            if category not in catalog.systems:
                problems.append(f"{at}.system.category '{category}' 카탈로그에 없음 "
                                f"(가능: {', '.join(catalog.systems)})")
            elif sub is not None and sub not in catalog.systems[category]:
                problems.append(f"{at}.system.subcategory '{sub}' {category}에 없음 "
                                f"(가능: {', '.join(catalog.systems[category]) or '없음'})")
    if len(targets) > 100:
        problems.append(f"대상 {len(targets)}개 — 최대 100개")
    return problems


def _limits(prefix, values):
    return [d["message"] for d in hr.length_checks(prefix, values)]


def validate_draft(d, catalog):
    number = d.get("receiptNo")
    if "incident" not in d:
        return {"receiptNo": number, "ready": False, "blockers": [d.get("error") or "incident 없음"],
                "pendingChecks": [], "notes": [], "requests": None}
    inc, blockers, notes = d["incident"], [], []
    for key, table in (("category", hr.CATEGORY), ("location", hr.LOCATION),
                       ("deviceCategory", hr.DEVICE)):
        if inc.get(key) not in table.values():
            blockers.append(f"incident.{key} '{inc.get(key)}' 허용값 아님")
    if (inc.get("deviceCategory") == "CONTROLLER") != (inc.get("controllerSubType") is not None):
        blockers.append("incident.controllerSubType는 deviceCategory가 CONTROLLER일 때만 필수")
    elif inc.get("controllerSubType") is not None and inc["controllerSubType"] not in hr.SUBTYPE.values():
        blockers.append(f"incident.controllerSubType '{inc['controllerSubType']}' 허용값 아님")
    if not hr.text(inc.get("memo")):
        blockers.append("incident.memo 비어 있음")
    if not hr.KST_AT.match(inc.get("receivedAt") or ""):
        blockers.append(f"incident.receivedAt '{inc.get('receivedAt')}' — +09:00 KST 일시 필요")
    blockers += check_targets(inc.get("targets"), catalog)
    blockers += _limits("incident", inc)

    responses = d.get("responses") or []
    for i, r in enumerate(responses):
        if not hr.text(r.get("content")):
            blockers.append(f"responses[{i}].content 비어 있음")
        if not hr.KST_AT.match(r.get("responseAt") or ""):
            blockers.append(f"responses[{i}].responseAt '{r.get('responseAt')}' — +09:00 KST 일시 필요")
        blockers += _limits(f"responses[{i}]", r)
    resolution = d.get("resolution")
    if resolution:
        for key, table in hr.ACTION:
            if resolution.get(key) not in table.values():
                blockers.append(f"resolution.{key} '{resolution.get(key)}' 허용값 아님")
        if resolution.get("resolvedAt") is None:
            notes.append("resolution.resolvedAt 없음 — 생략하면 등록 시각이 조치일시가 됨")
        elif not hr.KST_AT.match(resolution["resolvedAt"]):
            blockers.append(f"resolution.resolvedAt '{resolution['resolvedAt']}' — +09:00 KST 일시 필요")
        blockers += _limits("resolution", resolution)

    checks = d.get("checks") or []
    pending = [] if d.get("checksReviewed") is True else checks
    batches = [clean(responses[i:i + hr.RESPONSES_PER_CALL])
               for i in range(0, len(responses), hr.RESPONSES_PER_CALL)]
    return {"receiptNo": number, "ready": not blockers and not pending,
            "blockers": blockers, "pendingChecks": pending, "notes": notes,
            "judgmentNote": d.get("judgmentNote"),
            "requests": {
                "create_incident": clean(inc),
                "add_incident_responses": [{"responses": b} for b in batches],
                "add_incident_resolution": clean(resolution) if resolution else None,
            }}


def validate(data, catalog):
    drafts = data.get("drafts", []) if isinstance(data, dict) else data
    results = [validate_draft(d, catalog) for d in drafts]
    return {"summary": {"rows": len(results),
                        "ready": [r["receiptNo"] for r in results if r["ready"]],
                        "pendingChecks": [r["receiptNo"] for r in results
                                          if not r["blockers"] and r["pendingChecks"]],
                        "blocked": [r["receiptNo"] for r in results if r["blockers"]]},
            "results": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("drafts", help="history_map.py 출력(검토·수정본) JSON")
    parser.add_argument("--catalog", help=f"카탈로그 캐시 JSON (기본 {ht.DEFAULT_CATALOG})")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    with open(args.drafts, encoding="utf-8") as f:
        data = json.load(f)
    print(json.dumps(validate(data, ht.load_catalog(args.catalog)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
