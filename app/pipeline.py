"""센터 단계: 잠금 뒤 카드 파일을 읽고 계획 묶음대로 계산해 결과물을 만든다. 외부 연결은 처음에 잠근다."""
import datetime as dt
from pathlib import Path

import calc
import card
import config
import egress
import hub
import report

CODES = sorted(card.SPEC["codes"]["biz"])


def _sets(festival_months):
    return {k: set(v) for k, v in festival_months.items()}


def center_stage(bundle, files, out_dir=None, example=False, target="결과보고서"):
    """bundle: 공개 단계의 계획 묶음. files: [(파일 이름, 바이트)]. 화면에 보일 요약을 돌려준다(셀 값 없음)."""
    egress.lock()
    out_dir = Path(out_dir) if out_dir else config.out_path("report", "x").parent
    out_dir.mkdir(parents=True, exist_ok=True)
    table = card.new_table()
    checked = [card.ingest(data, name, table) for name, data in files]
    ev = bundle["event"]
    emd = ev["emd"]
    start, end = dt.date.fromisoformat(ev["start"]), dt.date.fromisoformat(ev["end"])
    festival = _sets(bundle["festival_months"])
    months = calc.months_for(start, end, festival.get(emd, set()))
    need = calc.required_months(months)
    coverage = card.check_coverage(table, need["required"], [emd])
    widened = {}
    if coverage["missing_months"] or coverage["missing_rows"]:
        result = {"outcome": "not_computed", "reason": "missing_files", "tried": []}
    else:
        _, result, widened = calc.rehearse(table, emd, bundle["kept"], start, end,
                                           bundle["plan"]["biz_codes"], CODES, festival)
        result = result or {"outcome": "not_computed", "reason": "small_cells", "tried": []}

    vals = report.values({"name": ev["name"], "start": start, "end": end}, emd, result, months)
    sentence = report.fill(bundle["texts"]["result_sentences"][result["outcome"]], vals)
    sentence = (sentence + " " + report.strength(result)).strip()
    images = []
    comp = result.get("emd")
    if comp:
        biz = widened[comp]
        report.index_chart(calc.series(table, emd, biz), calc.series(table, comp, biz), months, emd, comp,
                           out_dir / "index.png", example)
        images.append(out_dir / "index.png")
    visits_t, visits_c = hub.daily_visits(emd), hub.daily_visits(comp) if comp else None
    if visits_t:
        report.visit_chart(visits_t["days"], visits_c["days"] if visits_c else None, start, end, emd, comp or "", out_dir / "visit.png")
        images.append(out_dir / "visit.png")
    rows = report.evidence_rows(result, len(widened.get(comp) or []))
    ai_rows = [("방문 판단", bundle["judgement"]["visit"]["judgement"]), ("업종 범위 이유", bundle["plan"]["biz_reason"])]
    ai_rows += [(f"추가로 뺀 비교 후보 {x['emd']}", x["reason"]) for x in bundle["judgement"]["extra_excluded"]]
    limits = report.LIMITS + bundle["texts"]["extra_limits"]
    title = f"{ev['name']} 관광객 카드 소비 비교" + (" (예시, 가상 데이터)" if example else "")
    report.pdf(out_dir / "result.pdf", title, sentence, images, rows, ai_rows, limits)
    saved, finger = report.save_bundle(bundle) if out_dir == config.OUT / "report" else (None, None)
    return {
        "files": [{k: f[k] for k in ("name", "ok", "message", "months")} for f in checked],
        "coverage": coverage, "outcome": result["outcome"], "sentence": sentence,
        "method": bundle["texts"]["method"], "evidence": rows, "ai": ai_rows, "limits": limits,
        "images": [p.name for p in images], "pdf": "result.pdf",
        "usage_reason": report.usage_reason({"name": ev["name"], "start": start, "end": end}, need["all"], target),
        "bundle_file": saved.name if saved else None, "fingerprint": finger,
    }
