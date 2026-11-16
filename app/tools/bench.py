"""개발 때만 쓰는 실제 API 실행 도구. 비용을 누적하고 상한(ADR-158, 10달러)을 넘기 전에 멈춘다.

python tools/bench.py places    장소 추정표(data/hub/places.json)
"""
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

import agent  # noqa: E402
import config  # noqa: E402
import egress  # noqa: E402
import hub  # noqa: E402

LEDGER = APP.parent / "build" / "api_cost.json"
CAP_USD = 10.0
MARGIN_USD = 0.5  # 호출 한 번이 넘길 수 있는 여유
# 100만 토큰당 달러(Anthropic 참고 자료 11/3 기준, 프롬프트 10만 토큰 이하)
PRICE = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.0, 10.0)}


def spent():
    return json.loads(LEDGER.read_text())["usd"] if LEDGER.exists() else 0.0


def metered(purpose, body, timeout=egress.READ_TIMEOUT):
    if spent() + MARGIN_USD > CAP_USD:
        raise SystemExit(f"비용 상한 {CAP_USD}달러에 가까워 멈춘다(누적 {spent():.4f}달러)")
    msg = egress.call_llm(purpose, body, timeout)
    price_in, price_out = PRICE[body["model"]]
    usage = msg["usage"]
    tokens_in = usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
    cost = (tokens_in * price_in + usage.get("output_tokens", 0) * price_out) / 1e6
    LEDGER.parent.mkdir(exist_ok=True)
    LEDGER.write_text(json.dumps({"usd": spent() + cost}))
    print(f"  {purpose}: 입력 {tokens_in} 출력 {usage.get('output_tokens', 0)} 토큰, {cost:.4f}달러", flush=True)
    return msg


def places():
    first, last = hub.FIRST_DAY, hub.LAST_DAY
    events = [e for e in hub.load_events() if e["start"] and e["end"] and e["start"] <= last and e["end"] >= first]
    print(f"대상 행사 {len(events)}건")
    table, attempts = agent.estimate_places(events, metered)
    source = hub.DATA / "events.csv"
    out = {
        "model": config.MODEL,
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "events_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "attempts": attempts,
        "places": table,
    }
    (hub.DATA / "places.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    unknown = sum(1 for p in table.values() if p["reason"] == "추정 실패")
    print(f"저장 {len(table)}건, 묶음별 제출 횟수 {attempts}, 추정 실패 {unknown}건, 누적 비용 {spent():.4f}달러")


QA = APP.parent / "qa" / "bench"


def find_event(events, name):
    """같은 이름의 행사가 여러 해에 있으면 카드 수록 기간 안의 것을 고른다."""
    inside = [e for e in events if e["name"] == name and e["start"] and hub.FIRST_DAY <= e["start"] <= hub.LAST_DAY]
    if len(inside) != 1:
        raise SystemExit(f"{name}: 수록 기간 안의 행사 {len(inside)}건")
    return inside[0]


def judge(name, emd):
    events = hub.load_events()
    places = hub.load_places()
    event = find_event(events, name)
    ctx = agent.judge_context(event, emd, events, places)
    print(f"남은 후보 {[r['emd'] for r in ctx['ranked']]}, 규칙 제외 {[(x['emd'], x['why']) for x in ctx['rule_excluded']]}")
    print(f"방문 요약 {ctx['visit']}, 같은 시기 행사 {len(ctx['other_events'])}건")
    log = []
    result, messages = agent.judge(ctx, metered, lambda kind, text: (log.append((kind, text)), print(f"  [{kind}] {text}")))
    QA.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    record = {"event": ctx["event"], "result": result, "log": log, "context": {k: v for k, v in ctx.items() if k != "months"}}
    (QA / f"judge_{stamp}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(result.get("input", result), ensure_ascii=False, indent=1))
    print(f"제출 {result['submits']}번, 조회 {result['reads']}번, 누적 비용 {spent():.4f}달러")


def rehearsal_table():
    import card

    table = card.new_table()
    for f in sorted((APP / "data" / "dummy" / "card_rehearsal").glob("*.csv")):
        card.ingest(f.read_bytes(), f.name, table)
    return table


def plan(name, emd):
    """판단 단계에 이어 계획 단계까지. 남은 후보가 2곳 미만이어도 개발 확인용으로 계속 간다."""
    import calc

    events, places_table = hub.load_events(), hub.load_places()
    event = find_event(events, name)
    ctx = agent.judge_context(event, emd, events, places_table)
    log = []
    say = lambda kind, text: (log.append((kind, text)), print(f"  [{kind}] {text}"))  # noqa: E731
    judgement, messages = agent.judge(ctx, metered, say)
    if not judgement["ok"]:
        raise SystemExit(f"판단 단계 실패: {judgement}")
    table = rehearsal_table()
    codes = sorted(agent.BIZ_NAMES)
    seen = {}

    def rehearse(inp):
        kept = [r["emd"] for r in ctx["ranked"] if r["emd"] in {k["emd"] for k in judgement["input"]["kept"]}]
        problems, result, widened = calc.rehearse(table, emd, kept, event["start"], event["end"],
                                                  agent.BIZ_BUNDLES[inp["biz_bundle"]], codes, ctx["festival_months"])
        seen["last"] = (result, widened)
        say("리허설", f"결과 {result and result['outcome']}, 쌍별 업종 범위 크기 {({k: len(v) if v else None for k, v in widened.items()})}")
        return problems

    result, kept = agent.plan(ctx, judgement, messages, metered, say, rehearse)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    QA.mkdir(parents=True, exist_ok=True)
    record = {"event": ctx["event"], "judgement": judgement["input"], "plan": result, "rehearsal": seen.get("last"), "log": log}
    (QA / f"plan_{stamp}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(result.get("input", result), ensure_ascii=False, indent=1))
    print(f"계획 제출 {result['submits']}번, 조회 {result['reads']}번, 누적 비용 {spent():.4f}달러")


TEST_EVENTS = [("가파도청보리축제", "대정읍"), ("2025 보롬왓 튤립축제", "표선면"), ("마노르블랑 봄에 꽃향기축제", "안덕면"),
               ("수국과 공연이 꽃피는 혼인지 수국 축제", "성산읍"), ("2024 자청비 와흘메밀문화제", "조천읍")]


def measure(runs="3", model=None):
    """판정용 측정: 시험 행사마다 판단·계획 단계를 runs번 돌려 통과율, 제출·조회 횟수, 일치율, 비용, 시간을 남긴다.

    model을 주면 이 측정에서만 그 모델을 쓴다(config.py는 그대로).
    """
    import pipeline

    if model:
        config.MODEL = model

    events = hub.load_events()
    table = rehearsal_table()
    records = []
    for name, emd in TEST_EVENTS:
        event = find_event(events, name)
        for n in range(int(runs)):
            egress.unlock()
            before = spent()
            started = time.time()
            log = []
            origin, bundle, why = pipeline.public_stage(event, emd, metered, lambda k, t: log.append((k, t)), table)
            rec = {"event": name, "emd": emd, "run": n + 1, "origin": origin, "why": why,
                   "cost": round(spent() - before, 4), "seconds": round(time.time() - started, 1),
                   "reads": sum(1 for k, _ in log if k == "조회"),
                   "rejected": sum(1 for k, _ in log if k == "검사"),
                   "rejections": [t for k, t in log if k == "검사"]}
            if origin == "ai":
                rec.update({"kept": bundle["kept"], "extra": sorted(x["emd"] for x in bundle["judgement"]["extra_excluded"]),
                            "biz": sorted(bundle["plan"]["biz_codes"]), "visit": bundle["judgement"]["visit"]["judgement"],
                            "attempts": bundle["attempts"], "visit_reason": bundle["judgement"]["visit"]["reason"],
                            "biz_bundle": bundle["plan"]["biz_bundle"], "biz_reason": bundle["plan"]["biz_reason"],
                            "extra_reasons": [x["reason"] for x in bundle["judgement"]["extra_excluded"]],
                            "sentence_higher": bundle["texts"]["result_sentences"]["higher"]})
            records.append(rec)
            print(f"{name} {n + 1}: {origin} {why or ''} 조회 {rec['reads']} 돌려보냄 {rec['rejected']} {rec['cost']}달러 {rec['seconds']}초", flush=True)
    by_event = {}
    for r in records:
        by_event.setdefault(r["event"], []).append(r)
    summary = {}
    for name, rs in by_event.items():
        ai = [r for r in rs if r["origin"] == "ai"]
        same = lambda key: len(ai) == len(rs) and len({json.dumps(r[key]) for r in ai}) == 1  # noqa: E731
        summary[name] = {"passed": f"{len(ai)}/{len(rs)}", "kept_same": same("kept"), "extra_same": same("extra"),
                         "biz_same": same("biz"), "used_tool": sum(1 for r in rs if r["reads"] > 0)}
    QA.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = {"model": config.MODEL, "runs": records, "summary": summary,
           "total_cost": round(sum(r["cost"] for r in records), 4), "cost_per_run": round(sum(r["cost"] for r in records) / len(records), 4)}
    (QA / f"measure_{stamp}_{config.MODEL}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"합계 {out['total_cost']}달러, 실행당 {out['cost_per_run']}달러")


def answer_key():
    """사람 정답표 틀: 시험 행사 개최 읍면과 장소 추정표 무작위 30건(고정 씨앗). 사용자가 answer 칸을 채운다."""
    import random

    places, events = hub.load_places(), {e["event_id"]: e for e in hub.load_events()}
    sample = random.Random(20261116).sample(sorted(places), 30)
    key = {
        "test_events": [{"event": n, "assumed_emd": e, "answer": ""} for n, e in TEST_EVENTS],
        "place_sample": [{"event_id": i, "name": events[i]["name"], "ai_place": places[i]["place"],
                          "ai_spot": places[i]["spot"], "answer": ""} for i in sample],
    }
    path = APP.parent / "qa" / "answer_key.json"
    path.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{path} 시험 행사 {len(key['test_events'])}건, 장소 표본 {len(sample)}건")


def premade(event_id="363", emd="대정읍"):
    """AI를 쓸 수 없을 때의 대체 계획을 지금 코드로 한 번 실제 실행해 data/premade에 다시 만든다."""
    import pipeline

    event = next(e for e in hub.load_events() if e["event_id"] == event_id)
    egress.unlock()
    origin, bundle, why = pipeline.public_stage(event, emd, metered, lambda k, t: print(k, t), rehearsal_table())
    if origin != "ai":
        raise SystemExit(f"AI 실행 실패: {why}")
    path = pipeline.PREMADE / f"plan_{event_id}.json"
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{path.name} {bundle['plan']['biz_bundle']}, 비교 {bundle['kept']}")


def premade_all():
    """계산할 수 있는 읍면 행사마다 대체 계획을 만든다. 시험 행사는 확인한 개최 읍면, 나머지는 장소 추정표 읍면으로."""
    import calc

    known = {e["event_id"]: emd for name, emd in TEST_EVENTS for e in [find_event(hub.load_events(), name)]}
    places, made, failed = hub.load_places(), [], []
    for e in hub.load_events():
        emd = known.get(e["event_id"]) or places.get(e["event_id"], {}).get("place")
        if emd not in hub.EUP_MYEON or calc.feasibility(e["start"], e["end"])[0] == "unavailable":
            continue
        try:
            premade(e["event_id"], emd)
            made.append(e["event_id"])
        except SystemExit as why:
            failed.append((e["event_id"], e["name"], str(why)))
    print(f"만듦 {len(made)}건, 실패 {len(failed)}건 {failed}, 누적 비용 {spent():.4f}달러")


if __name__ == "__main__":
    {"places": places, "judge": judge, "plan": plan, "measure": measure, "answer_key": answer_key,
     "premade": premade, "premade_all": premade_all}[sys.argv[1]](*sys.argv[2:])
