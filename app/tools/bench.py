"""개발 때만 쓰는 실제 API 실행 도구. 비용을 누적하고 상한(ADR-158, 10달러)을 넘기 전에 멈춘다.

python tools/bench.py places    장소 추정표(data/hub/places.json)
"""
import datetime as dt
import hashlib
import json
import sys
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


if __name__ == "__main__":
    {"places": places}[sys.argv[1]]()
