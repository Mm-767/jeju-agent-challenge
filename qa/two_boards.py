"""가상 데이터 두 판 검증: AI 추가 제외 없이 규칙 순위 그대로, 업종 묶음별로 계산. 실행: cd app && .venv/bin/python -X utf8 ../qa/two_boards.py"""
import sys
sys.path.insert(0, ".")
from pathlib import Path
import agent, calc, card, hub, pipeline
from tools.bench import TEST_EVENTS, find_event

events, places = hub.load_events(), hub.load_places()
tables = {}
for v in ("card_effect", "card_none"):
    t = card.new_table()
    for f in sorted(Path(f"data/dummy/{v}").glob("*.csv")):
        card.ingest(f.read_bytes(), f.name, t)
    tables[v] = t
for name, emd in TEST_EVENTS:
    ev = find_event(events, name)
    ctx = agent.judge_context(ev, emd, events, places)
    kept = [r["emd"] for r in ctx["ranked"]]
    months = calc.months_for(ev["start"], ev["end"], set(ctx["festival_months"].get(emd, ())))
    need = calc.required_months(months)
    print(name, emd, "후보", kept, "필수", len(need["required"]), "모두", len(need["all"]))
    for bname in ("관광 소비 전체", "먹거리·음료 중심"):
        for v, t in tables.items():
            _, r, _ = calc.rehearse(t, emd, kept, ev["start"], ev["end"], agent.BIZ_BUNDLES[bname], pipeline.CODES, ctx["festival_months"])
            r = r or {}
            E=r.get('E'); print(f"   {bname:10} {v:12} {r.get('outcome')} {r.get('reason','')} 비교={r.get('emd')} E={E and round(E,3)} p={r.get('p') and round(r['p'],3)} J={r.get('J')} 큰차이={r.get('n')} tried={[(x['emd'], round(x['L'],3), x['sigma'] and round(x['sigma'],3), x['J']) for x in r.get('tried',[])]}")
