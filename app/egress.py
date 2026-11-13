"""네트워크를 쓰는 유일한 런타임 모듈. 다른 런타임 파일은 socket·urllib·http·anthropic을 불러오지 않는다.

외부로 나가는 요청은 call_llm 하나뿐이고, 보낸 본문은 모두 전송 기록(out/work/transmissions.jsonl)에 남는다.
센터 형식 CSV를 읽기 직전에 lock()을 부르면 그 뒤 call_llm은 보내지 않고 막는다.
"""
import json
import socket
import time
import urllib.request

import config

APP_MARK = "event-effect"
MAX_CALLS = 16  # 실행 1회 LLM 호출 상한(ADR-160)
RETRIES = 2
TIMEOUT = 20  # 최악 대기 약 3 x 20초 + 쉼 6초

# 127.0.0.1 확인에 윈도우 시스템 프록시가 끼지 않게 프록시 없이 연다
_local = urllib.request.build_opener(urllib.request.ProxyHandler({}))

_state = {"locked": False, "calls": 0, "client": None}


class Locked(Exception):
    pass


class CallLimit(Exception):
    pass


def port_free(port):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def local_app_running(port):
    try:
        with _local.open(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
            return json.load(r).get("app") == APP_MARK
    except (OSError, ValueError):
        return False


def _log(entry):
    with config.out_path("work", "transmissions.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def lock():
    _state["locked"] = True
    client = _state.pop("client", None)
    _state["client"] = None
    if client is not None:
        client.close()  # 열린 연결 풀을 버려 잠금 뒤 재사용을 막는다


def unlock():
    _state["locked"] = False
    _state["calls"] = 0


def is_locked():
    return _state["locked"]


def _client():
    if _state["client"] is None:
        import anthropic

        key = config.env("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("no_key")
        # SDK 자동 재시도는 끄고 여기서 정한 규칙으로만 다시 보낸다
        _state["client"] = anthropic.Anthropic(api_key=key, max_retries=0, timeout=TIMEOUT)
    return _state["client"]


def call_llm(purpose, body, timeout=TIMEOUT):
    """messages.create 본문을 그대로 보내고 응답을 사전으로 돌려준다. timeout은 한 번 시도의 대기 초."""
    if _state["locked"]:
        _log({"time": time.time(), "purpose": purpose, "status": "blocked"})
        raise Locked(purpose)
    if _state["calls"] >= MAX_CALLS:
        raise CallLimit(purpose)
    import anthropic

    _state["calls"] += 1
    started = time.time()
    for attempt in range(RETRIES + 1):
        try:
            # None 칸을 빼야 응답 블록을 다음 요청에 그대로 되돌려 보낼 수 있다
            msg = _client().with_options(timeout=timeout).messages.create(**body).model_dump(exclude_none=True)
            break
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError):
            if attempt == RETRIES:
                _log({"time": started, "purpose": purpose, "status": "failed", "request": body})
                raise
            time.sleep(2 * (attempt + 1))
    _log({"time": started, "purpose": purpose, "status": "sent", "request": body,
          "usage": msg["usage"], "stop_reason": msg["stop_reason"]})
    return msg
