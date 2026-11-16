"""센터 단계: 잠금 뒤 카드 파일을 읽고 계획 묶음대로 계산해 결과물을 만든다. 외부 연결은 처음에 잠근다."""
import copy
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
    plan = bundle["plan"]
    ai_rows = [("방문 판단", bundle["judgement"]["visit"]["judgement"]),
               ("업종 묶음", plan.get("biz_bundle") or f"{len(plan['biz_codes']) or 42}개 업종"), ("업종 범위 이유", plan["biz_reason"])]
    ai_rows += [(f"추가로 뺀 비교 후보 {x['emd']}", x["reason"]) for x in bundle["judgement"]["extra_excluded"]]
    limits = report.LIMITS + bundle["texts"]["extra_limits"]
    title = f"{ev['name']} 관광객 카드 소비 비교" + (" (연습용 가상 데이터)" if example else "")
    event = {"name": ev["name"], "start": start, "end": end}
    rep = report.build_report(event, emd, result, months, bundle, sentence, rows, ai_rows, len(widened.get(comp) or []))
    usage = report.usage_reason(event, need["all"], target)
    report.pdf(out_dir / "result.pdf", title, rep, images, usage)
    saved, finger = report.save_bundle(bundle) if out_dir == config.OUT / "report" else (None, None)
    return {
        "report": rep,
        "files": [{k: f[k] for k in ("name", "ok", "message", "months")} for f in checked],
        "coverage": coverage, "outcome": result["outcome"], "sentence": sentence,
        "method": bundle["texts"]["method"], "evidence": rows, "ai": ai_rows, "limits": limits,
        "images": [p.name for p in images], "pdf": "result.pdf",
        "usage_reason": usage,
        "bundle_file": saved.name if saved else None, "fingerprint": finger,
    }


# ---- 공개 단계 -------------------------------------------------------------

PREMADE = config.APP / "data" / "premade"


def fill_known(ctx, judgement, inp):
    """결과 문장 틀이 아닌 AI 글의 빈칸을 계획 때 아는 값으로 채운다. 이 글들은 화면과 보고서에 그대로 나간다."""
    ev, visit = ctx["event"], ctx["visit"]
    vals = {"행사_이름": ev["name"], "행사_읍면": ev["emd"],
            "행사_기간": report.period(dt.date.fromisoformat(ev["start"]), dt.date.fromisoformat(ev["end"])),
            "기준_기간": report.month_span(ctx["months"]["base"])}
    vals |= {f"visit.{k}": report.pct(visit[k]) if visit.get(k) is not None else "값 없음" for k in ("R_T", "R_C", "V")}
    j = copy.deepcopy(judgement)
    j["visit"]["reason"] = report.fill(j["visit"]["reason"], vals)
    j["visit"]["caution"] = report.fill(j["visit"]["caution"], vals)
    for x in j["kept"] + j["extra_excluded"]:
        x["reason"] = report.fill(x["reason"], vals)
    for x in j["treated_month_other_events"]:
        x["note"] = report.fill(x["note"], vals)
    p = dict(inp, biz_reason=report.fill(inp["biz_reason"], vals), method=report.fill(inp["method"], vals),
             extra_limits=[report.fill(t, vals) for t in inp["extra_limits"]])
    return j, p


def build_bundle(ctx, judgement, plan_result, kept, origin="ai"):
    import agent

    m = ctx["months"]
    judged, inp = fill_known(ctx, judgement["input"], plan_result["input"])
    return {
        "bundle_version": 1, "origin": origin, "model": config.MODEL,
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "event": ctx["event"],
        "months": {k: m[k] for k in ("event", "excluded", "base", "pretrend")},
        "festival_months": {k: sorted(v) for k, v in ctx["festival_months"].items()},
        "ranked": ctx["ranked"], "rule_excluded": ctx["rule_excluded"], "visit_summary": ctx["visit"],
        "judgement": judged, "kept": kept,
        "plan": {"biz_bundle": inp["biz_bundle"], "biz_codes": agent.BIZ_BUNDLES[inp["biz_bundle"]], "biz_reason": inp["biz_reason"]},
        "texts": {"result_sentences": inp["result_sentences"], "method": inp["method"], "extra_limits": inp["extra_limits"]},
        "attempts": {"judge": judgement["submits"], "plan": plan_result["submits"]},
        "tool_calls": judgement["reads"] + plan_result["reads"],
    }


def premade(event_id, emd=None):
    """미리 만든 계획. emd를 주면 그 읍면으로 만든 계획일 때만 돌려준다."""
    path = PREMADE / f"plan_{event_id}.json"
    if not path.exists():
        return None
    bundle = __import__("json").loads(path.read_text(encoding="utf-8"))
    if emd and bundle["event"]["emd"] != emd:
        return None
    bundle["origin"] = "premade"
    return bundle


def public_stage(event, emd, call, log, rehearsal_table):
    """판단·계획 단계. 성공하면 ("ai", 묶음), AI를 쓸 수 없거나 실패하면 ("premade", 묶음 또는 None, 이유)."""
    import agent

    events, places = hub.load_events(), hub.load_places()
    ctx = agent.judge_context(event, emd, events, places)
    try:
        judgement, messages = agent.judge(ctx, call, log)
        if not judgement["ok"]:
            return "premade", premade(event["event_id"], emd), judgement["why"]

        def rehearse(inp):
            problems, _, _ = calc.rehearse(rehearsal_table, emd, kept_now(), event["start"], event["end"],
                                           agent.BIZ_BUNDLES[inp["biz_bundle"]], CODES, ctx["festival_months"])
            return problems

        def kept_now():
            names = {k["emd"] for k in judgement["input"]["kept"]}
            return [r["emd"] for r in ctx["ranked"] if r["emd"] in names]

        plan_result, kept = agent.plan(ctx, judgement, messages, call, log, rehearse)
        if not plan_result["ok"]:
            return "premade", premade(event["event_id"], emd), plan_result["why"]
        return "ai", build_bundle(ctx, judgement, plan_result, kept), None
    except (egress.Locked, egress.CallLimit, RuntimeError) as e:
        return "premade", premade(event["event_id"], emd), type(e).__name__
    except Exception as e:  # SDK 오류(연결, 인증, 거절 등)는 모두 대체 경로로
        if type(e).__module__.startswith("anthropic"):
            return "premade", premade(event["event_id"], emd), type(e).__name__
        raise
