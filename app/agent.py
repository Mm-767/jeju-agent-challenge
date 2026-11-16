"""LLM 단계. 공개 자료형만 받는다. 외부 호출은 인자로 받은 call(=egress.call_llm)로만 한다."""
import datetime as dt
import json
import re

import calc
import config
import hub
from grounding import check_numbers

BATCH = 60
SUBMIT_TRIES = 3  # 첫 제출 포함(ADR-160)
PLACE_TIMEOUT = 180  # 60건을 한 번에 쓰는 개발용 호출이라 화면 흐름의 20초보다 길게 둔다
PLACE_PROMPT = (config.PROMPTS / "places.txt").read_text(encoding="utf-8")
TOOLS = json.loads((config.PROMPTS / "tools.json").read_text(encoding="utf-8"))


def tool_results(content, verdict):
    """앞 응답의 tool_use마다 tool_result를 하나씩 만든다. 하나라도 빠지면 다음 요청이 400이 된다."""
    return [
        {"type": "tool_result", "tool_use_id": b["id"], "content": text, "is_error": error}
        for b in content if b["type"] == "tool_use"
        for text, error in [verdict(b)]
    ]


def check_places(places, expected):
    ids = [p["event_id"] for p in places]
    problems = []
    missing = [i for i in expected if i not in ids]
    extra = sorted(set(ids) - set(expected))
    twice = sorted({i for i in ids if ids.count(i) > 1})
    if missing:
        problems.append(f"빠진 event_id: {', '.join(missing)}.")
    if extra:
        problems.append(f"목록에 없는 event_id: {', '.join(extra)}.")
    if twice:
        problems.append(f"두 번 넣은 event_id: {', '.join(twice)}.")
    return problems


def _unknown(event_id):
    return {"event_id": event_id, "place": "모름", "spot": "", "kind": "기타", "confidence": "낮음", "reason": "추정 실패"}


def _place_batch(batch, call):
    rows = [
        {"event_id": e["event_id"], "name": e["name"], "start": str(e["start"]), "end": str(e["end"]), "host": e["host"]}
        for e in batch
    ]
    expected = [r["event_id"] for r in rows]
    messages = [{"role": "user", "content": PLACE_PROMPT + json.dumps(rows, ensure_ascii=False)}]
    for attempt in range(1, SUBMIT_TRIES + 1):
        msg = call("places", {
            "model": config.MODEL, "max_tokens": 16000,
            "tools": [TOOLS["submit_place_table"]], "messages": messages,
        }, timeout=PLACE_TIMEOUT)
        accepted = []

        def verdict(block):
            if block["name"] != "submit_place_table":
                return "이 단계에서 쓸 수 없는 도구입니다.", True
            problems = check_places(block["input"]["places"], expected)
            if problems:
                return " ".join(problems) + " 고쳐서 목록 전체를 다시 제출하세요.", True
            accepted.append(block["input"]["places"])
            return "통과", False

        results = tool_results(msg["content"], verdict)
        if accepted:
            return accepted[0], attempt
        messages.append({"role": "assistant", "content": msg["content"]})
        messages.append({"role": "user", "content": results or "submit_place_table 도구로 제출하세요."})
    return [_unknown(i) for i in expected], SUBMIT_TRIES


def estimate_places(events, call):
    """행사마다 개최 장소 추정. {event_id: 추정}과 묶음별 제출 횟수."""
    table = {}
    attempts = []
    for i in range(0, len(events), BATCH):
        places, n = _place_batch(events[i:i + BATCH], call)
        attempts.append(n)
        for p in places:
            table[p["event_id"]] = p
    return table, attempts


# ---- 판단 단계 -------------------------------------------------------------


def conversation_tools():
    """판단·계획 단계가 같은 대화를 쓰므로 도구 목록도 같아야 한다.

    도구 목록이 바뀌면 앞 단계의 생각 블록이 무효가 되어 API가 400을 낸다(11/14 실제 확인).
    """
    return [TOOLS["get_visit_series"], TOOLS["submit_judgement"], TOOLS["submit_plan"]]


MAX_READS = 4
MAX_SERIES_DAYS = 120
JUDGE_PROMPT = (config.PROMPTS / "judge.txt").read_text(encoding="utf-8")
VISIT_BLANKS = {"visit.R_T", "visit.R_C", "visit.V"}
WEEKDAYS = "월화수목금토일"


def name_variants(name):
    """행사 이름 원문, 꺾쇠·괄호를 뺀 형태, 숫자가 든 조각(예: 9.81파크)."""
    plain = re.sub(r"[<>()\[\]「」『』]", " ", name)
    pieces = [p for p in plain.split() if re.search(r"\d", p)]
    return [name, " ".join(plain.split())] + pieces


def _festival_in(emd, months, events, places, skip_id):
    for ev in events:
        p = places.get(ev["event_id"])
        if ev["event_id"] == skip_id or not p or p["place"] != emd or p["kind"] != "축제" or not ev["start"] or not ev["end"]:
            continue
        if any(s >= calc.SHORT_SHARE and m in months for m, s in calc.overlap(ev["start"], ev["end"]).items()):
            return ev
    return None


def judge_context(event, emd, events, places):
    """판단 단계 입력. 공개 스냅샷과 장소 추정표만 쓴다."""
    start, end = event["start"], event["end"]
    months = calc.months_for(start, end)
    calc_months = set(months["pretrend"] + months["base"]) | set(calc.overlap(start, end))
    rule_excluded, remaining = [], []
    for c in hub.EUP_MYEON:
        if c == emd:
            continue
        if emd not in hub.ISLANDS and c in hub.ISLANDS:
            rule_excluded.append({"emd": c, "why": "섬 지역", "event_id": ""})
        elif hub.daily_visits(c) is None:
            rule_excluded.append({"emd": c, "why": "공개 방문 자료 없음", "event_id": ""})
        elif fest := _festival_in(c, calc_months, events, places, event["event_id"]):
            rule_excluded.append({"emd": c, "why": "계산 기간에 다른 축제", "event_id": fest["event_id"], "name": fest["name"]})
        else:
            remaining.append(c)
    target = hub.daily_visits(emd)
    t_means = hub.monthly_means(target) if target else None
    means = {c: hub.monthly_means(hub.daily_visits(c)) for c in remaining}
    ranked, skipped = calc.rank(t_means, means, calc.distance_months(start, end), top=len(remaining)) if t_means else ([], remaining)
    rule_excluded += [{"emd": c, "why": "흐름 거리 계산 불가", "event_id": ""} for c in skipped]
    summary = calc.visit_summary(target["days"] if target else None,
                                 {c: hub.daily_visits(c)["days"] for c, _ in ranked}, start, end)
    first = dt.date(start.year, start.month, 1)
    last = dt.date(end.year, end.month, 1) + dt.timedelta(days=31)
    others = []
    for ev in events:
        if ev["event_id"] == event["event_id"] or not ev["start"] or not ev["end"]:
            continue
        if ev["start"] < last.replace(day=1) and ev["end"] >= first:
            p = places.get(ev["event_id"], {})
            others.append({"event_id": ev["event_id"], "name": ev["name"], "start": str(ev["start"]), "end": str(ev["end"]),
                           "place": p.get("place", "모름"), "spot": p.get("spot", ""), "kind": p.get("kind", "기타"),
                           "confidence": p.get("confidence", "낮음")})
    festival_months = {}
    for ev in events:
        p = places.get(ev["event_id"])
        if ev["event_id"] == event["event_id"] or not p or p["kind"] != "축제" or not ev["start"] or not ev["end"]:
            continue
        hit = {m for m, s in calc.overlap(ev["start"], ev["end"]).items() if s >= calc.SHORT_SHARE}
        festival_months.setdefault(p["place"], set()).update(hit)
    return {
        "event": {"event_id": event["event_id"], "name": event["name"], "start": str(start), "end": str(end), "emd": emd},
        "months": months,
        "festival_months": festival_months,
        "visit": {k: (round(summary[k], 4) if isinstance(summary[k], float) else summary[k]) for k in ("R_T", "R_C", "V", "missing_days")},
        "ranked": [{"emd": c, "distance": round(d, 4)} for c, d in ranked],
        "rule_excluded": rule_excluded,
        "other_events": others,
    }


def judge_facts(ctx, seen=frozenset()):
    """seen: 이 단계에서 조회 도구로 본 날짜. 본 곡선의 날짜를 말하는 것은 근거가 있다."""
    ev = ctx["event"]
    start, end = dt.date.fromisoformat(ev["start"]), dt.date.fromisoformat(ev["end"])
    dates = {start + dt.timedelta(n) for n in range((end - start).days + 1)} | set(seen)
    names = name_variants(ev["name"])
    for o in ctx["other_events"]:
        dates |= {dt.date.fromisoformat(o["start"]), dt.date.fromisoformat(o["end"])}
        names += name_variants(o["name"]) + ([o["spot"]] if o["spot"] else [])
    m = ctx["months"]
    return {
        "dates": dates,
        "months": set(m["event"] + m["excluded"] + m["base"] + m["pretrend"]),
        # 남긴 비교 읍면 수는 후보 수 이하 어느 값이든 될 수 있다(「세 곳을 남겼다」)
        "counts": set(range(1, len(ctx["ranked"]) + 1)) | {len(ctx["rule_excluded"]), len(ctx["other_events"]), 2, 9, 11, 12, 42},
        "names": names,
        "codes": set(),
        "ranks": set(range(1, len(ctx["ranked"]) + 1)),
        "blanks": VISIT_BLANKS,
        "ids": {o["event_id"] for o in ctx["other_events"]},
    }


def visit_series(inp):
    """get_visit_series 처리. (돌려줄 글, 오류 여부)."""
    try:
        start = dt.date.fromisoformat(inp["start_date"])
        end = dt.date.fromisoformat(inp["end_date"])
    except ValueError:
        return "날짜는 YYYY-MM-DD로 주세요.", True
    if start < hub.FIRST_DAY or end > hub.LAST_DAY or end < start:
        return "스냅샷 범위는 2023-08-01부터 2026-08-31까지입니다.", True
    if (end - start).days + 1 > MAX_SERIES_DAYS:
        return "한 번에 120일까지 조회할 수 있습니다.", True
    visits = hub.daily_visits(inp["emd"])
    if visits is None:
        return f"{inp['emd']}은 공개 방문 자료가 없습니다.", True
    rows = []
    for n in range((end - start).days + 1):
        d = start + dt.timedelta(n)
        rows.append({"date": str(d), "weekday": WEEKDAYS[d.weekday()], "visit_pop": visits["days"].get(d)})
    return json.dumps({"emd": inp["emd"], "rows": rows, "note": "visit_pop이 null인 날은 결측일"}, ensure_ascii=False), False


def validate_judgement(inp, ctx, seen=frozenset()):
    problems = []
    remaining = [r["emd"] for r in ctx["ranked"]]
    other_ids = {o["event_id"] for o in ctx["other_events"]}
    if not inp["visit"]["evidence"]:
        problems.append("visit.evidence가 비어 있습니다.")
    named = [x["emd"] for x in inp["extra_excluded"]] + [x["emd"] for x in inp["kept"]]
    for c in remaining:
        if named.count(c) != 1:
            problems.append(f"{c}이 kept와 extra_excluded에 한 번씩 들어가야 하는데 {named.count(c)}번 있습니다.")
    for c in sorted(set(named) - set(remaining)):
        problems.append(f"{c}은 남은 후보가 아닙니다(규칙으로 이미 뺐거나 행사 읍면입니다).")
    for x in inp["extra_excluded"]:
        if x["event_id"] and x["event_id"] not in other_ids:
            problems.append(f"extra_excluded의 event_id {x['event_id']}는 같은 시기 행사 목록에 없습니다.")
    for x in inp["treated_month_other_events"]:
        if x["event_id"] not in other_ids:
            problems.append(f"treated_month_other_events의 event_id {x['event_id']}는 같은 시기 행사 목록에 없습니다.")
    facts = judge_facts(ctx, seen)
    texts = [("visit.reason", inp["visit"]["reason"]), ("visit.caution", inp["visit"]["caution"])]
    texts += [(f"kept {x['emd']}", x["reason"]) for x in inp["kept"]]
    texts += [(f"extra_excluded {x['emd']}", x["reason"]) for x in inp["extra_excluded"]]
    texts += [(f"note {x['event_id']}", x["note"]) for x in inp["treated_month_other_events"]]
    for where, text in texts:
        problems += [f"{where}: {p}" for p in check_numbers(text, "reason", facts)]
    return problems


def run_stage(purpose, messages, tools, submit_name, validate, call, log):
    """제출이 검사를 통과하거나 기회를 다 쓸 때까지 돈다. 모든 tool_use에 tool_result를 하나씩 붙인다."""
    submits = reads = 0
    seen = set()
    while True:
        msg = call(purpose, {"model": config.MODEL, "max_tokens": 16000, "tools": tools, "messages": messages})
        if msg["stop_reason"] in ("refusal", "max_tokens"):
            return {"ok": False, "why": msg["stop_reason"], "submits": submits, "reads": reads}
        messages.append({"role": "assistant", "content": msg["content"]})
        if not any(b["type"] == "tool_use" for b in msg["content"]):
            submits += 1
            if submits >= SUBMIT_TRIES:
                return {"ok": False, "why": "no_submit", "submits": submits, "reads": reads}
            messages.append({"role": "user", "content": f"{submit_name} 도구를 불러 이 단계를 끝내 주세요."})
            continue
        state = {"passed": None}

        def verdict(block):
            nonlocal submits, reads
            if block["name"] == "get_visit_series":
                reads += 1
                if reads > MAX_READS:
                    return "이 단계의 조회 한도를 다 썼습니다. 지금 가진 자료로 제출해 주세요.", True
                log("조회", block["input"]["why"])
                text, error = visit_series(block["input"])
                if not error:
                    first = dt.date.fromisoformat(block["input"]["start_date"])
                    last = dt.date.fromisoformat(block["input"]["end_date"])
                    seen.update(first + dt.timedelta(n) for n in range((last - first).days + 1))
                return text, error
            if block["name"] == submit_name and state["passed"] is None:
                submits += 1
                problems = validate(block["input"], seen)
                if problems:
                    more = f" 외 {len(problems) - 1}건" if len(problems) > 1 else ""
                    stage = {"judge": "방문 판단", "plan": "계산 계획"}[purpose]
                    log("검사", f"{stage} {submits}번째 제출을 돌려보냈습니다: {problems[0]}{more}")
                    return " ".join(problems) + f" 고쳐서 다시 제출하세요(남은 제출 기회 {SUBMIT_TRIES - submits}번).", True
                state["passed"] = block["input"]
                return "통과", False
            if block["name"] == submit_name:
                return "앞의 제출이 이미 통과해 이 제출은 쓰지 않았습니다.", False
            return "이 단계에서는 쓸 수 없는 도구입니다.", True

        results = tool_results(msg["content"], verdict)
        if state["passed"] is not None:
            return {"ok": True, "input": state["passed"], "pending": results, "submits": submits, "reads": reads}
        if submits >= SUBMIT_TRIES:
            return {"ok": False, "why": "checks_failed", "submits": submits, "reads": reads}
        messages.append({"role": "user", "content": results})


def judge(ctx, call, log):
    """판단 단계. 결과와 대화(계획 단계가 이어 쓴다)를 돌려준다."""
    public = {k: ctx[k] for k in ("event", "visit", "ranked", "rule_excluded", "other_events")}
    messages = [{"role": "user", "content": JUDGE_PROMPT + "\n입력(JSON):\n" + json.dumps(public, ensure_ascii=False)}]
    result = run_stage("judge", messages, conversation_tools(), "submit_judgement", lambda i, seen: validate_judgement(i, ctx, seen), call, log)
    return result, messages


# ---- 계획 단계 -------------------------------------------------------------

PLAN_PROMPT = (config.PROMPTS / "plan.txt").read_text(encoding="utf-8")
PLAN_BLANKS = {"행사_이름", "행사_읍면", "비교_읍면", "차이", "행사_기간", "기준_기간", "계산_못한_이유"}
REQUIRED_BLANKS = {"higher": {"차이", "비교_읍면"}, "lower": {"차이", "비교_읍면"},
                   "no_difference": {"비교_읍면"}, "not_computed": {"계산_못한_이유"}}
CAUSAL = re.compile(r"입증|증명|덕분|기여했|기여한")
MAX_LIMITS = 3
MIN_CANDIDATES = 2  # 남은 비교 후보가 이보다 적으면 계산하지 않는다(계획서 4-1)
BIZ_NAMES = json.loads((config.APP / "spec" / "card_v02.json").read_text(encoding="utf-8"))["codes"]["biz"]
# ADR-167: AI는 업종 코드 대신 이 묶음 가운데 하나를 고른다. 빈 목록은 42개 전체(10 미만 칸 처리와 같은 규칙).
_MEALS = ["I56111", "I56112", "I56113", "I56114", "I56119", "I56192"]
_DRINKS = ["I56211", "I56219", "I56220"]
_STAY = ["I55111", "I55112", "I55113"]
BIZ_BUNDLES = {
    "관광 소비 전체": _MEALS + _DRINKS + _STAY + ["G47122", "G47130", "G47215", "G47842", "H49212", "H49231",
                                                 "H50121", "L69110", "L69210", "N75211", "R91239", "R91299"],
    "먹거리·음료 중심": _MEALS + _DRINKS + ["G47122", "G47129", "G47213", "G47214", "G47215"],
    "숙박·체류 중심": _STAY + _MEALS + ["I56220", "H49212", "H49231", "L69110", "N75211"],
    "42개 전체": [],
}


def validate_plan(inp, ctx, seen, rehearse):
    problems = []
    for case, need in REQUIRED_BLANKS.items():
        text = inp["result_sentences"][case]
        missing = [b for b in sorted(need) if "{{" + b + "}}" not in text]
        if missing:
            problems.append(f"result_sentences.{case}에 {', '.join('{{' + b + '}}' for b in missing)}가 없습니다.")
    if len(inp["extra_limits"]) > MAX_LIMITS:
        problems.append(f"extra_limits가 {len(inp['extra_limits'])}개입니다. 많아야 {MAX_LIMITS}개입니다.")
    facts = dict(judge_facts(ctx, seen), blanks=PLAN_BLANKS, codes=set(BIZ_NAMES))
    texts = [(f"result_sentences.{k}", v, "result") for k, v in inp["result_sentences"].items()]
    texts += [("method", inp["method"], "method"), ("biz_reason", inp["biz_reason"], "reason")]
    texts += [(f"extra_limits {i + 1}", t, "reason") for i, t in enumerate(inp["extra_limits"])]
    for where, text, field in texts:
        if field == "result" and (m := CAUSAL.search(text)):
            problems.append(f"{where}에 인과를 단정하는 말 '{m.group(0)}'이 있습니다. 결과는 비교 읍면 대비 차이입니다.")
        problems += [f"{where}: {p}" for p in check_numbers(text, field, facts)]
    if not problems:
        problems += rehearse(inp)
    return problems


def plan(ctx, judgement, messages, call, log, rehearse):
    """계획 단계. 판단 단계 대화를 이어 쓴다. rehearse(제출)는 가상 데이터 리허설의 문제 목록을 돌려준다."""
    kept = [r["emd"] for r in ctx["ranked"] if r["emd"] in {k["emd"] for k in judgement["input"]["kept"]}]
    if len(kept) < MIN_CANDIDATES:
        return {"ok": False, "why": "too_few_candidates", "submits": 0, "reads": 0}, kept
    m = ctx["months"]
    data = {
        "comparisons_in_order": kept,
        "months": {"event": m["event"], "base": m["base"], "pretrend": m["pretrend"]},
        "biz_bundles": {name: [BIZ_NAMES[c] for c in codes] or "42개 업종 전체" for name, codes in BIZ_BUNDLES.items()},
    }
    text = PLAN_PROMPT + "\n입력(JSON):\n" + json.dumps(data, ensure_ascii=False)
    messages.append({"role": "user", "content": judgement["pending"] + [{"type": "text", "text": text}]})

    def validate(inp, seen):
        return validate_plan(inp, ctx, seen, rehearse)

    return run_stage("plan", messages, conversation_tools(), "submit_plan", validate, call, log), kept
