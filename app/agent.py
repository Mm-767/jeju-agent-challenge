"""LLM 단계. 공개 자료형만 받는다. 외부 호출은 인자로 받은 call(=egress.call_llm)로만 한다."""
import json

import config

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
