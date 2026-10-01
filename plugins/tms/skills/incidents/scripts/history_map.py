"""원본 추출 JSON을 등록 초안으로 매핑하고 판정 기록을 남긴다 (2단계).

  python history_map.py source.json [--catalog 카탈로그.json] > drafts.json

초안 한 건은 create_incident·add_incident_responses·add_incident_resolution 입력에 맞춘
incident·responses·resolution과, 원문에서 무엇이 어떻게 바뀌었는지의 판정 기록(decisions)을 가진다.

  blockers : fail 판정 — 고치기 전에는 등록할 수 없다
  checks   : check 판정 — 에이전트가 원문·장애 내용과 대조해 판단해야 한다
  ready    : blockers와 checks가 모두 없음

맨 위 summary는 규칙별로 접수번호를 묶어 여러 건을 한 번에 검토할 수 있게 한다.
exact 판정은 기록에서 뺀다. 다음 단계는 검토·수정 후 history_validate.py다.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import history_rules as hr  # noqa: E402
import history_targets as ht  # noqa: E402

DONE_WORDS = {"처리", "완료", "처리완료"}


def map_row(row, catalog):
    c = row["cells"]
    t = hr.text
    decisions = []
    received = hr.parse_kst(c.get("E_접수일자"))
    if not received:
        decisions.append(hr.decision("incident.receivedAt", hr.FAIL, "time.received_missing",
                                     c.get("E_접수일자"), None, "E열 접수일자 없음 또는 해석 불가"))
    codes, found = hr.parse_incident_code(c.get("D_장애코드"))
    decisions += found
    targets, found = ht.map_targets(c.get("F_본부"), c.get("G_터널명"), catalog, c.get("O_장애내용"))
    decisions += found
    decisions += ht.consistency_checks(c.get("F_본부"), c.get("O_장애내용"), targets, catalog)
    incident = {"legacyReceiptNo": row["receiptNo"], "receivedAt": hr.kst(received),
                "receiverName": t(c.get("H_접수자")), "reporterName": t(c.get("J_신고자")),
                "reporterOrganization": t(c.get("I_신고자소속")), **codes,
                "memo": t(c.get("O_장애내용")), "targets": targets}
    if not incident["memo"]:
        decisions.append(hr.decision("incident.memo", hr.FAIL, "memo.missing", None, None,
                                     "O열 장애 내용 없음"))
    decisions += hr.length_checks("incident", incident)

    handler = t(c.get("M_처리자"))
    responses, found = hr.split_progress(c.get("P_대응경과"), received, handler)
    decisions += found
    for i, r in enumerate(responses):
        decisions += hr.length_checks(f"responses[{i}]", r)
    if len(responses) > hr.RESPONSES_PER_CALL:
        decisions.append(hr.decision("responses", hr.RULE, "responses.batched", len(responses),
                                     hr.RESPONSES_PER_CALL,
                                     f"대응 {len(responses)}건 — 도구 호출을 {hr.RESPONSES_PER_CALL}건씩 나눔"))

    resolved = hr.parse_kst(c.get("L_복구일자"))
    resolution = None
    if t(c.get("K_조치코드")) or t(c.get("R_조치")) or resolved:
        fields, found = hr.parse_action_code(c.get("K_조치코드"))
        decisions += found
        resolution = {**fields, "resolvedAt": hr.kst(resolved), "resolverName": handler,
                      "cause": t(c.get("Q_원인")), "memo": t(c.get("R_조치")),
                      "remarks": t(c.get("S_비고"))}
        if not resolved:
            decisions.append(hr.decision("resolution.resolvedAt", hr.CHECK, "time.resolved_missing",
                                         c.get("L_복구일자"), None,
                                         "L열 복구일자 없음 — 생략하면 등록 시각이 조치일시가 됨"))
        decisions += hr.length_checks("resolution", resolution)
    done = t(c.get("B_처리완료"))
    if done and done not in DONE_WORDS and resolution:
        decisions.append(hr.decision("resolution", hr.CHECK, "status.unfinished_with_resolution", done,
                                     None, f"B열 '{done}'인데 조치 정보가 있음 — 조치 등록 여부 판단"))
    if done in DONE_WORDS and not resolution:
        decisions.append(hr.decision("resolution", hr.CHECK, "status.done_without_resolution", done,
                                     None, "B열 처리완료인데 조치 정보(K·L·R열)가 없음"))
    decisions += hr.time_order_checks(received, resolved, responses)

    decisions = [d for d in decisions if d["level"] != hr.EXACT]
    blockers = [d["message"] for d in decisions if d["level"] == hr.FAIL]
    checks = [d["message"] for d in decisions if d["level"] == hr.CHECK]
    return {"receiptNo": row["receiptNo"], "excelRow": row.get("excelRow"),
            "ready": not blockers and not checks, "blockers": blockers, "checks": checks,
            "checksReviewed": False,
            "sourceText": {"F": c.get("F_본부"), "G": c.get("G_터널명"), "D": c.get("D_장애코드"),
                           "K": c.get("K_조치코드")},
            "incident": incident, "responses": responses, "resolution": resolution,
            "decisions": decisions}


def summarize(drafts):
    by_rule = {}
    for d in drafts:
        for dec in d["decisions"]:
            entry = by_rule.setdefault(dec["rule"], {"level": dec["level"], "receiptNos": []})
            if d["receiptNo"] not in entry["receiptNos"]:
                entry["receiptNos"].append(d["receiptNo"])
    # F열 본부 → 현재 소속 조합별 묶음: 조직 개편인지 사용자에게 조합마다 한 번만 묻기 위함
    mismatch = {}
    for d in drafts:
        for dec in d["decisions"]:
            if dec["rule"] == "division.mismatch":
                key = f"{dec['from']} → {dec['to']}"
                nos = mismatch.setdefault(key, [])
                if d["receiptNo"] not in nos:
                    nos.append(d["receiptNo"])
    order = {hr.FAIL: 0, hr.CHECK: 1, hr.RULE: 2}
    by_rule = dict(sorted(by_rule.items(), key=lambda kv: (order[kv[1]["level"]], kv[0])))
    return {
        "rows": len(drafts),
        "ready": [d["receiptNo"] for d in drafts if d["ready"]],
        "needsJudgment": [d["receiptNo"] for d in drafts if not d["blockers"] and d["checks"]],
        "blocked": [d["receiptNo"] for d in drafts if d["blockers"]],
        "byRule": by_rule,
        "divisionMismatch": dict(sorted(mismatch.items(), key=lambda kv: -len(kv[1]))),
    }


def map_source(source, catalog, catalog_path=None):
    drafts = [map_row(r, catalog) for r in source.get("rows", [])]
    return {"workbook": source.get("workbook"), "extractedAt": source.get("extractedAt"),
            "catalog": {"path": str(catalog_path or ht.DEFAULT_CATALOG), "version": catalog.version},
            "missing": source.get("missing", []), "summary": summarize(drafts), "drafts": drafts}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", help="history_extract.py 출력 JSON")
    parser.add_argument("--catalog", help=f"카탈로그 캐시 JSON (기본 {ht.DEFAULT_CATALOG})")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    with open(args.source, encoding="utf-8") as f:
        source = json.load(f)
    catalog = ht.load_catalog(args.catalog)
    print(json.dumps(map_source(source, catalog, args.catalog), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
