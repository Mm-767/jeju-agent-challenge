"""판정용 측정 기록(qa/bench/measure_*.json)을 읽어 업종 범위 겹침과, 각 실행의 계획을 가상 효과 데이터로 계산한 결과를 낸다.

cd app && .venv/bin/python ../qa/analyze_measure.py ../qa/bench/measure_YYYYMMDD_HHMMSS.json
"""
import itertools
import json
import statistics
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
sys.path[:0] = [str(APP), str(APP / "tools")]

import agent  # noqa: E402
import calc  # noqa: E402
import card  # noqa: E402
import hub  # noqa: E402
import pipeline  # noqa: E402
from bench import find_event  # noqa: E402

runs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["runs"]
print("조회 평균", statistics.mean(r["reads"] for r in runs), "최소", min(r["reads"] for r in runs))
print("돌려보냄", sorted(r["rejected"] for r in runs))
table = card.new_table()
for f in sorted((APP / "data" / "dummy" / "card_effect").glob("*.csv")):
    card.ingest(f.read_bytes(), f.name, table)
events, places = hub.load_events(), hub.load_places()
for name in dict.fromkeys(r["event"] for r in runs):
    rs = [r for r in runs if r["event"] == name and r["origin"] == "ai"]
    sets = [set(r["biz"]) for r in rs]
    jaccard = [round(len(a & b) / len(a | b), 2) for a, b in itertools.combinations(sets, 2)]
    ev = find_event(events, name)
    ctx = agent.judge_context(ev, rs[0]["emd"], events, places)
    results = []
    for r in rs:
        _, res, _ = calc.rehearse(table, r["emd"], r["kept"], ev["start"], ev["end"], r["biz"], pipeline.CODES, ctx["festival_months"])
        results.append(f"{res['outcome']} E={res['E']:+.3f} p={res['p']:.3f}" if "E" in res else f"{res['outcome']}({res.get('reason')})")
    print(name, "| 방문", [r["visit"] for r in rs], "| 업종 수", [len(s) for s in sets], "겹침", jaccard)
    print("   비교", [r["kept"] for r in rs], "추가 제외", [r["extra"] for r in rs])
    print("   가상 효과 데이터 결과", results)
